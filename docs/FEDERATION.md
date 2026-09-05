# Federation Guide

How to federate two `service-directory` nodes end to end: enable it, pair,
and — critically — verify the catalogues actually merged rather than just
trusting a successful handshake.

## 1. Enable federation on both nodes

In each node's config (`federation:` block; see `docs/ARCHITECTURE.md` §6
for the full schema):

```yaml
federation:
  enabled: true
  name: "amplifier-srv-01"                # this node's origin name
  base_url: "http://100.111.191.22:80"    # advertised to peers when pairing
  description: "Home lab tailnet node"    # optional, public
  role: "primary"                         # optional, public
```

Restart (or re-`install`) each node after editing config —
`federation.enabled` is read at process start, not hot-reloaded.

## 2. Issue a pairing code on node A

From node A itself (the node being paired *to*), using the localhost
bypass:

```bash
service-directory token issue --port 80
# prints a one-time code, e.g.: 9f2a1c...
```

(If node A does not run on port 80, add `--port <its-port>`. If you can
only reach node A remotely, use the write-token-gated
`POST /api/federation/ui-pairing-code` instead — see `docs/API.md`.)

The code is single-use and expires after 10 minutes
(`pairing.DEFAULT_PAIRING_TTL_SECONDS`).

## 3. Redeem the code on node B

From node B (the node initiating pairing):

```bash
service-directory pair --url http://100.111.191.22:80 --code 9f2a1c...
```

This calls `POST /api/federation/pair` on node A with node B's own identity
+ the code. Node A validates the code, mints a long-lived per-peer token
for node B, records node B in its own trust store, and returns its
identity + a token for node B. `pair` then records node A (with that
token) in node B's trust store. **Both sides now trust each other, each
using its own separately-issued per-peer token** — revoking one peer's
token later never affects any other peer.

At this point the pairing handshake has succeeded. This is NOT yet proof
the catalogues merged — see §4.

## 4. Verify — the REAL check

A successful `pair` call only proves the trust relationship was
established. It does not, by itself, prove either node's catalogue
actually contains the other's services. Verify explicitly, on **both**
nodes:

```bash
# On node A: node B's services should show up with origin == node B's name
curl -s http://127.0.0.1/api/services | python3 -c \
  'import json,sys; data=json.load(sys.stdin); print(sorted({s["origin"] for s in data}))'

# /api/federation/nodes on node A should list BOTH nodes, both reachable: true
curl -s http://127.0.0.1/api/federation/nodes | python3 -m json.tool
```

Repeat both checks on node B. The mesh is genuinely federated only when:

1. Each node's `/api/services` contains entries whose `origin` is the
   **other** node's name (not just its own), and
2. Each node's `/api/federation/nodes` lists **both** nodes with
   `"reachable": true`.

A half-configured mesh (e.g. only one side paired, a firewall blocking one
direction, a `base_url` that doesn't actually route) will pass the pairing
handshake but fail check 1 or 2 — `aggregate_services()` silently omits an
unreachable peer from `/api/services` rather than erroring, so the ONLY way
to catch this is to actually look at the aggregated data, not just trust
that `pair`/`token issue` returned `200`.

This project's own real two-node fleet (`amplifier-srv-01` +
`wintermute`, paired both ways) is the reference case: each reports the
union of both catalogues, and `/api/federation/nodes` on either shows the
other as `reachable: true`.

## 5. What actually crosses the pairing handshake

The `POST /api/federation/pair` request/response
(`PairRequest`/return body in `app.py`) carries exactly:

- `name` — the peer's origin/display name
- `device_id` — the peer's stable identity (`identity.load_or_create_identity()`)
- `base_url` — the URL to reach that peer at
- `token` — a freshly-minted per-peer bearer token (one direction; the
  reverse pairing, if done, mints its own separate token)

**Known defect: `description` and `role` do NOT cross the handshake.**
`GET /api/federation/nodes` hardcodes `"description": None, "role": None`
for every PEER entry (see `app.federation_nodes()`) — these two fields are
only ever populated for the LOCAL node (read straight from its own live
config). Even if a peer has both configured in its own `federation:` block,
it will show up as `description: null, role: null` on the other node,
because the pairing payload and the peer record it produces
(`trust_store.PeerRecord`) simply don't carry those fields at all. Do not
expect to see a peer's description/role reflected remotely — treat it as a
per-node-local piece of self-description, visible only via that node's own
`/api/instance-info` or `/api/settings`, not via a peer's view of it.

## 6. Identical service names across nodes are expected, not a bug

If two federated nodes both run, say, a service literally named
`"muxplex"`, both entries will appear in the merged `/api/services` output
— once per origin. This is by design: entries are only ever deduplicated
by `(origin, name)` (`federation.dedupe_services()`), never by name alone,
and the dashboard disambiguates them visually by rendering one
`<section class="node-group" data-origin="...">` per origin node (see
`docs/UI.md` §1). Seeing the same service name twice, once under each
node's section, is the mesh working correctly — it is not a duplication
defect and does not need `dedupe_services` (or config) changes to "fix".

## 7. Loop protection (why a cyclic or dense mesh is safe)

Federation is pull-based and transitive: fetching a peer's *aggregated*
catalogue (rather than only its local-only view) lets a 3+ node mesh merge
fully, while two mechanisms keep it from recursing forever
(`federation.py`, `app._aggregation_result()`):

- **Visited set** (`x-sd-federation-visited` header): each hop appends the
  current node to the set of names already walked; a node already in that
  set answers with its local-only view instead of continuing the walk.
- **Hop budget** (`x-sd-federation-ttl` header, default `DEFAULT_MAX_HOPS =
  5`): decremented at every hop; once exhausted, a node answers
  local-only regardless of the visited set.

Either guard alone would be sufficient for a strict tree; both together
mean a fully-meshed federation (every node paired with every other) is
safe and terminates in bounded time regardless of how it's wired.
