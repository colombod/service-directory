# API Reference

Every endpoint below is implemented in `src/service_directory/app.py`
(`create_app()`). Examples assume a node running locally on port 8085
(`SERVICE_REGISTRY_PORT=8085 SERVICE_REGISTRY_CONFIG=./config.sample.yaml
service-directory serve`). Replace the host/port with your own.

## Auth model (applies to every endpoint below)

Two independent mechanisms (`src/service_directory/auth.py`):

- **Localhost bypass**: if the TCP client address is `127.0.0.1`/`::1`
  (`request.client.host`, not a spoofable header), admin/write checks pass
  automatically.
- **Bearer token**: `Authorization: Bearer <token>`. Two different token
  types are checked depending on the endpoint:
  - the **write token** (`write_token.json`, one shared secret per node,
    minted via `service-directory token issue-write`) — required for
    registry mutations and the UI-facing federation-management endpoints;
  - a **per-peer token** (`peers.json`, one per trusted peer, minted during
    pairing) — accepted by admin endpoints as an alternative to localhost.

Three access levels are used consistently:

- **open** — no auth check at all, ever.
- **read** — open by default; becomes token/localhost-gated when
  `federation.require_read_token: true` (`require_read_access()`).
- **write** — always gated: localhost bypass (unless
  `federation.require_write_token: true`), or a valid write-token bearer
  (`require_write_access()`). There is no unauthenticated mutation path.
- **admin** — always gated: localhost bypass, or a valid *per-peer* bearer
  token (`require_admin()`). Used only by `/api/federation/pairing-code`.

A rejected request returns `401 {"detail": "unauthorized"}` (write/admin) —
verified against `auth.require_write_access()` / `auth.require_admin()`.

---

## `GET /`

HTML dashboard — the single self-contained page. Same data as
`GET /api/services`, rendered as HTML.

- **Auth**: read
- **Params**: none
- **Success**: `200`, `Content-Type: text/html`
- **Failure**: `401` (JSON body) if `require_read_token` is set and no valid
  credential is supplied

```bash
curl -s http://127.0.0.1:8085/
```

---

## `GET /api/services`

Aggregated catalogue: this node's local services (static UNION dynamic)
plus every trusted peer's local services, transitively, deduplicated. This
is the JSON the dashboard renders from.

- **Auth**: read
- **Params**: none
- **Success**: `200`, JSON array of service objects. Each object includes at
  minimum: `name`, `description`, `links` (array of `{label, host, url}`),
  `category`, `tags`, `icon`, `owner`, `docs_url`, `source`
  (`"static"`/`"dynamic"`), `origin` (owning node's name), and the viewer
  fields `view_url`, `view_kind`, `view_refresh_seconds` when configured.
- **Failure**: `401` if read-gated and unauthenticated

```bash
curl -s http://127.0.0.1:8085/api/services | python3 -m json.tool
```

---

## `GET /api/services/local`

This node's OWN services only — never peer-aggregated. This is the exact
endpoint peers hit when fetching this node during federation, so a
federation loop can never form regardless of which endpoint a misconfigured
fetcher targets.

- **Auth**: read
- **Params**: none
- **Success**: `200`, JSON array (same shape as `/api/services`, but every
  entry's `origin` is this node)
- **Failure**: `401` if read-gated and unauthenticated

```bash
curl -s http://127.0.0.1:8085/api/services/local
```

---

## `GET /api/health`

Best-effort `{name: "up"|"down"}` snapshot for this node's own catalogue
(static UNION dynamic). Priority per entry: heartbeat-fresh dynamic ttl
entry → HTTP GET `health_url` (2xx = up) → TCP-connect fallback against the
first resolved link.

- **Auth**: read
- **Params**: none
- **Success**: `200`, e.g. `{"Resolve": "up", "muxplex": "down"}`
- **Failure**: `401` if read-gated and unauthenticated. The page/endpoint
  itself never fails even if every check fails — a down service reports
  `"down"`, it does not raise.

```bash
curl -s http://127.0.0.1:8085/api/health
```

---

## `POST /api/services`

Register or upsert a dynamic service.

- **Auth**: write
- **Body** (JSON): `name` (required, string), one of `port` (int) or `url`
  (string) required, `path`, `description`, `category`, `tags` (list[str]),
  `icon`, `owner`, `docs_url`, `health_url`, `ttl` (float seconds — omit for
  a persistent entry) — all optional.
- **Success**: `200`, JSON of the stored entry (same shape as a catalogue
  entry, `source: "dynamic"`)
- **Failure**:
  - `400` if `name` is missing, or neither `port` nor `url` is given
  - `409` if `name` collides with an existing **static** service name
    (`{"detail": "'<name>' is a static service name and cannot be shadowed by a dynamic registration"}`)
  - `401` if unauthorized

```bash
curl -s -X POST http://127.0.0.1:8085/api/services \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $WRITE_TOKEN" \
  -d '{"name": "my-agent", "port": 9001, "description": "ad-hoc agent"}'
```

---

## `DELETE /api/services/{name}`

Deregister a dynamic service. Static entries are read-only via this path.

- **Auth**: write
- **Params**: `name` (path)
- **Success**: `200`, `{"removed": "<name>"}`
- **Failure**:
  - `403` if `name` is a static service (`{"detail": "static services are read-only"}`)
  - `404` if no dynamic entry with that name exists
  - `401` if unauthorized

```bash
curl -s -X DELETE http://127.0.0.1:8085/api/services/my-agent \
  -H "Authorization: Bearer $WRITE_TOKEN"
```

---

## `POST /api/services/{name}/heartbeat`

Refresh the liveness of a `ttl`-based dynamic entry (resets its expiry
clock). No-op body.

- **Auth**: write
- **Params**: `name` (path)
- **Success**: `200`, JSON of the updated entry
- **Failure**:
  - `403` if `name` is a static service
  - `404` if no live dynamic entry with that name exists (never registered,
    or already pruned as stale)
  - `401` if unauthorized

```bash
curl -s -X POST http://127.0.0.1:8085/api/services/my-agent/heartbeat \
  -H "Authorization: Bearer $WRITE_TOKEN"
```

---

## `GET /api/instance-info`

Unauthenticated node self-description, used during discovery/probing.
Deliberately excludes anything secret (no tokens, no peer list, no config
paths).

- **Auth**: open (no auth check at all)
- **Params**: none
- **Success**: `200`, e.g.
  `{"name": "amplifier-srv-01", "device_id": "…", "version": "0.1.0",
  "federation_enabled": true, "description": "Home lab tailnet node",
  "role": "primary"}` — `description`/`role` keys are present ONLY when
  configured (never emitted as `null`).
- **Failure**: none (never gated)

```bash
curl -s http://127.0.0.1:8085/api/instance-info
```

---

## `GET /api/settings`

Read-only identity + federation status for this node, sourced live from
config (never hardcoded/cached).

- **Auth**: read
- **Params**: none
- **Success**: `200`, e.g.
  `{"name": "...", "description": "...", "role": "...", "base_url": "...",
  "federation_enabled": true, "host_addresses": [{"label": "Tailnet", "host": "..."}]}`
- **Failure**: `401` if read-gated and unauthenticated

```bash
curl -s http://127.0.0.1:8085/api/settings
```

---

## `GET /api/federation/nodes`

All nodes as seen from here: this node, plus every trusted peer, with
reachability reused from the SAME aggregation pass `/api/services` uses
(never a second, separate probe).

- **Auth**: read
- **Params**: none
- **Success**: `200`, JSON array; each element:
  `{"name": "...", "description": "..."|null, "role": "..."|null,
  "device_id": "...", "base_url": "...", "reachable": true|false}`. The
  local node's own entry always has `reachable: true`.
- **Failure**: `401` if read-gated and unauthenticated
- **Known defect**: for PEER entries, `description` and `role` are always
  `null` — the pairing handshake does not exchange these fields, so even a
  peer with both configured will show `null` here. See
  `docs/FEDERATION.md`.

```bash
curl -s http://127.0.0.1:8085/api/federation/nodes | python3 -m json.tool
```

---

## `GET /api/federation/peers`

Trusted peers only (no local-node entry), with reachability.

- **Auth**: read
- **Params**: none
- **Success**: `200`, JSON array:
  `[{"name": "...", "base_url": "...", "device_id": "...", "reachable": true|false}, ...]`
- **Failure**: `401` if read-gated and unauthenticated

```bash
curl -s http://127.0.0.1:8085/api/federation/peers
```

---

## `DELETE /api/federation/peers/{name}`

Remove a trusted peer (revokes that one peer's token; does not affect
others).

- **Auth**: write
- **Params**: `name` (path)
- **Success**: `200`, `{"removed": "<name>"}`
- **Failure**: `404` if no trusted peer with that name; `401` if
  unauthorized

```bash
curl -s -X DELETE http://127.0.0.1:8085/api/federation/peers/wintermute \
  -H "Authorization: Bearer $WRITE_TOKEN"
```

---

## `POST /api/federation/pairing-code`

Mint a short-lived (10 minutes), one-time pairing code. This is the
endpoint the CLI's `token issue` calls.

- **Auth**: admin (localhost bypass, or a valid per-peer bearer token)
- **Body**: none
- **Success**: `200`, `{"code": "...", "ttl_seconds": 600}`
- **Failure**: `401` if not localhost and no valid peer token

```bash
# From the node itself (localhost bypass applies):
curl -s -X POST http://127.0.0.1:8085/api/federation/pairing-code
```

---

## `POST /api/federation/pair`

Redeem a one-time pairing code presented by another node. Validates the
code, mints a long-lived per-peer token for the caller, records the caller
in the trust store, and returns this node's own identity plus that token.
This is the endpoint the CLI's `pair` command calls on the *target* node.

- **Auth**: none (the one-time code itself is the credential — it is
  single-use and short-lived)
- **Body** (JSON): `device_id`, `name`, `base_url`, `code` (all required
  strings)
- **Success**: `200`,
  `{"name": "...", "device_id": "...", "base_url": "...", "token": "..."}`
  — the caller must persist this token to trust the responder.
- **Failure**: `400 {"detail": "invalid or expired pairing code"}` if the
  code is unknown, already used, or expired

```bash
curl -s -X POST http://100.111.191.22:80/api/federation/pair \
  -H "Content-Type: application/json" \
  -d '{"device_id": "my-device-id", "name": "wintermute", "base_url": "http://100.111.191.9:80", "code": "<CODE>"}'
```

---

## `POST /api/federation/ui-pairing-code`

Same effect as `/api/federation/pairing-code`, but gated by the **write
token** instead of the admin/localhost rule, so a browser session with the
write token entered can mint a code without being on localhost.

- **Auth**: write
- **Body**: none
- **Success**: `200`, `{"code": "...", "ttl_seconds": 600}`
- **Failure**: `401` if unauthorized

```bash
curl -s -X POST http://127.0.0.1:8085/api/federation/ui-pairing-code \
  -H "Authorization: Bearer $WRITE_TOKEN"
```

---

## `POST /api/federation/pair-with-peer`

Initiate pairing FROM this node's UI: presents this node's identity + a
code to a remote peer's `/api/federation/pair`, receives that peer's
identity + a per-peer token, and records the peer in this node's trust
store. Equivalent to `service-directory pair --url <URL> --code <CODE>`,
but callable from the browser.

- **Auth**: write
- **Body** (JSON): `url` (peer's base URL), `code` (pairing code issued BY
  that peer)
- **Success**: `200`, `{"name": "...", "device_id": "...", "base_url": "..."}`
  (the token is stored locally, never returned to the caller)
- **Failure**: `502 {"detail": "pairing failed: ..."}` if the remote call
  fails or the peer rejects the code; `401` if unauthorized

```bash
curl -s -X POST http://127.0.0.1:8085/api/federation/pair-with-peer \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $WRITE_TOKEN" \
  -d '{"url": "http://100.111.191.22:80", "code": "<CODE>"}'
```

---

## `GET /api/embed-probe`

Probe whether a catalogue target can be embedded in an iframe: issues an
HTTP `HEAD` and inspects `X-Frame-Options`/`Content-Security-Policy`. Used
by the dashboard's `view_kind: "auto"` viewer before deciding how to render
a service. SSRF-guarded: `url` must resolve to a host:port that already
appears somewhere in this node's own resolved catalogue.

- **Auth**: read
- **Params**: `url` (query string, required) — must match a catalogue
  host:port
- **Success**: `200`,
  `{"reachable": true, "embeddable": true|false, "content_type": "text/html"|null}`
- **Failure**: `403 {"detail": "URL not in catalogue -- SSRF guard"}` if
  `url` is not a catalogue target

```bash
curl -s "http://127.0.0.1:8085/api/embed-probe?url=http://100.111.191.22:8080/"
```

**Known limitation**: the probe uses a plain `urllib` `HEAD` request with no
redirect handling beyond what `urllib` does automatically for the same
host; a `3xx` response (e.g. an app redirecting an unauthenticated request
to `/login`) that ultimately fails to resolve (or any other exception during
the request) is reported as `{"reachable": false, "embeddable": false,
"content_type": null}` — i.e. an auth-gated app looks "unreachable" to the
prober even though a human's browser, already logged in, could embed it
fine. **Because of this, any service that sits behind a login must have
`view_kind: "iframe"` pinned explicitly in config** — leaving it on `"auto"`
means the probe will always report it unreachable and the viewer will show
the fallback ("Service is unreachable") instead of the iframe.

---

## `GET /api/view-proxy`

CORS-avoiding proxy: fetches `url` server-side and returns the body
verbatim as `application/json`. Used by the `view_kind: "json"` viewer (and
by `"auto"` when the probe detects a JSON content type). Same SSRF guard as
`/api/embed-probe`.

- **Auth**: read
- **Params**: `url` (query string, required) — must match a catalogue
  host:port
- **Success**: `200`, the upstream response body, `Content-Type:
  application/json`
- **Failure**:
  - `403 {"detail": "URL not in catalogue -- SSRF guard"}` if `url` is not a
    catalogue target
  - `502 {"detail": "upstream fetch failed: ..."}` on any upstream error
    (connection refused, timeout, non-JSON, TLS mismatch — including
    pointing plain `http://` at an upstream that only speaks TLS)

```bash
curl -s "http://127.0.0.1:8085/api/view-proxy?url=http://100.111.191.22:8000/status"
```
