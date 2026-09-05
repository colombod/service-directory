# Architecture

This document explains the shape of `service-directory`: what a single node
is, how the catalogue is assembled, how the dashboard is rendered, and how
nodes federate. All claims here are verified against the source on `main`;
file/line references point at the functions that actually implement the
behaviour described.

## 1. The shape of a single node

A node is one Python process (`service-directory serve`) that:

1. Loads a YAML config file (`SERVICE_REGISTRY_CONFIG` env var, or `--config`)
   into a `RegistryConfig` dataclass — see `src/service_directory/config.py`.
2. Serves **one server-rendered HTML page** (`GET /`) plus a **JSON API**
   under `/api/...`. There is no separate frontend build, no client-side
   framework, and no CDN dependency — the entire UI is inline CSS/JS returned
   by one Python function.
3. Optionally federates with other trusted nodes over HTTP, aggregating their
   catalogues into its own view.

Request flow for `GET /`, end to end:

```
browser
  -> GET /                                (src/service_directory/app.py: index())
    -> require_read_access(...)           (src/service_directory/auth.py)
    -> _aggregated_services(request)      (app.py) -> _aggregation_result(request)
         -> _all_local_services_json()    (app.py)  [static UNION dynamic, THIS node]
         -> aggregate_services(...)       (src/service_directory/federation.py)
              -> concurrently fetch each trusted peer's /api/services/local
              -> tag every entry with its origin node name
    -> _render_html(services, node_info)  (app.py)
         -> _service_row_html(svc) per service (app.py)
    <- HTMLResponse
```

`GET /api/services` runs the exact same aggregation path and returns the raw
JSON instead of rendering HTML — the JSON is the source of truth the HTML is
rendered from, not a separate view of different data.

## 2. Where each concern lives (module map)

| Concern | Module | Key entry points |
|---|---|---|
| App factory, every HTTP endpoint, HTML render | `src/service_directory/app.py` | `create_app()`, `create_app_from_env()`, `index()`, `_render_html()`, `_service_row_html()` |
| Config parsing (YAML → dataclasses) | `src/service_directory/config.py` | `load_config()`, `parse_config()`, `RegistryConfig` |
| URL resolution (service × host address → link) | `src/service_directory/urls.py` | `resolve_all()`, `resolve_service()`, `build_url()` |
| Dynamic service registry (`registry.json`) | `src/service_directory/registry.py` | `load_registry()`, `register_service()`, `deregister_service()`, `heartbeat_service()` |
| Federation (peer aggregation, loop protection) | `src/service_directory/federation.py` | `aggregate_services()`, `default_peer_fetcher()`, `make_default_transitive_fetcher()`, `dedupe_services()` |
| Health checks | `src/service_directory/health.py` | `check_service_entries()`, `default_checker()`, `default_http_checker()` |
| Auth (localhost bypass, bearer tokens) | `src/service_directory/auth.py` | `require_read_access()`, `require_write_access()`, `require_admin()`, `is_localhost_request()` |
| Trust store (`peers.json`) | `src/service_directory/trust_store.py` | `load_peers()`, `upsert_peer()`, `remove_peer()`, `find_peer_by_token()` |
| Pairing codes | `src/service_directory/pairing.py` | `PairingCodeStore.issue()`, `PairingCodeStore.redeem()` |
| Write token (registry mutations) | `src/service_directory/write_token.py` | `issue_write_token()`, `verify_write_token()`, `load_write_token()` |
| Node identity (`device_id`) | `src/service_directory/identity.py` | `load_or_create_identity()` |
| Diagnostics checklist | `src/service_directory/doctor.py` | `run_doctor()`, `run_and_format()` |
| systemd/launchd service install | `src/service_directory/service_manager.py` | `get_service_manager()`, `render_systemd_unit()`, `render_launchd_plist()` |
| CLI entry point | `src/service_directory/cli.py` | `main()`, one `cmd_*` function per subcommand |
| Self-upgrade | `src/service_directory/upgrade.py` | `run_upgrade()` |

Where the acceptance criteria ask "which module renders the page, serves the
catalogue, handles federation":

- **Renders the page**: `_render_html()` + `_service_row_html()` in `app.py`.
- **Serves the catalogue**: `GET /` (`index()`), `GET /api/services`
  (`api_services()`), and `GET /api/services/local` (`api_services_local()`),
  all in `app.py`, all built on `_aggregated_services()` /
  `_all_local_services_json()`.
- **Handles federation**: the merge logic lives in `federation.py`
  (`aggregate_services`, `dedupe_services`); the HTTP-level plumbing (peer
  trust, pairing, per-request loop protection) lives in `app.py`'s
  `_aggregation_result()` and the `/api/federation/*` endpoints.

## 3. The catalogue: static YAML UNION dynamic registry

Every node's **local catalogue** (before any federation) is the union of two
independent sources, computed by `_all_local_services_json()` in `app.py`:

- **Static services** (`source: "static"`): declared in the `services:` list
  of the YAML config. Read-only at runtime — there is no HTTP mutation path
  for them. A static entry can never be deleted or shadowed by a dynamic
  registration (`POST /api/services` returns `409` if the name collides with
  a static one; `DELETE`/heartbeat on a static name returns `403`).
- **Dynamic services** (`source: "dynamic"`): registered at runtime via
  `POST /api/services` (or the CLI `register`/`deregister`/`heartbeat`
  commands, or the dashboard's "Add service" form), persisted to
  `registry.json` in the node's state directory (see §5). Entries may be
  **persistent** (no `ttl`) or **heartbeat-based** (`ttl` seconds — expires
  and is pruned from the catalogue if no heartbeat arrives within `ttl`
  seconds; see `registry.is_expired()` / `registry.load_registry()`).

**Precedence**: static always wins. A dynamic registration whose `name`
matches an existing static service name is rejected outright (`409`); the
static entry is never shadowed. Within the dynamic registry, `POST
/api/services` is an upsert by `name` — registering the same name twice
replaces the previous entry (see `registry.register_service()`).

The union (static + dynamic) is read **fresh from disk on every request** —
`registry.json` has no in-process cache — so a CLI `register`/`deregister`
takes effect on the very next `GET /` or `GET /api/services` with no restart
needed.

## 4. Federation: transitive aggregation with loop protection

Every node keeps **only its own local config** — there is no static peer
list in YAML. Trusted peers are established entirely via a pairing
handshake (see `docs/FEDERATION.md`) and persisted to `peers.json` in the
state directory.

On every read of the aggregated catalogue (`_aggregation_result()` in
`app.py`):

1. The node starts with its own local catalogue, tagged with its own
   `origin` name.
2. It loads its trusted peers (`trust_store.load_peers()`) and concurrently
   fetches each one's catalogue (via a `PeerFetcher`, see
   `federation.py`), each bounded to `DEFAULT_PEER_TIMEOUT_SECONDS` (1.0s).
3. A peer that fails to respond (timeout, connection error, non-2xx, bad
   JSON) is **silently omitted** — it never breaks rendering, and the local
   list plus any peers that DID respond still render (`aggregate_services()`
   catches every per-peer exception in `_fetch_one()`).
4. Every fetched entry is tagged with its *origin* node's name
   (`_tag_origin()`), unless it already carries an `origin` (meaning it was
   relayed transitively — see below) — credit always goes to the node that
   actually owns the service.

**Transitive aggregation** (a federates with b, b federates with c ⇒ a's
catalogue includes c's services): a *top-level* request (from a browser, or
`GET /api/services`) triggers `make_default_transitive_fetcher()`, which
targets each peer's **aggregated** `/api/services` endpoint (not the
local-only one) and passes two headers:

- `x-sd-federation-visited` — comma-separated set of node names already
  walked, so a cycle can never re-enter a node already visited.
- `x-sd-federation-ttl` — remaining hop budget, decremented at each hop
  (`DEFAULT_MAX_HOPS = 5` at the top level), so the walk is depth-bounded
  even on a graph the visited-set alone wouldn't catch in time.

A node receiving a request carrying the hop header (`x-sd-federation-hop`)
knows it is being asked *by another node's peer-fetch*, not by a user, and
answers with its local-only view when it is already in the visited set or
the ttl is exhausted (see `_aggregation_result()`'s early-return branch).
This is what makes **mutual** (bidirectional) trust safe without infinite
recursion: A fetching B never causes B to recurse into fetching A back.

`dedupe_services()` then collapses any entry that arrived via more than one
path through the graph, keyed on `(origin, name)` — first occurrence wins.

Duplicate service *names* across **different** origin nodes are NOT
deduplicated and are not a bug: they are disambiguated by the origin
grouping in the rendered page (each origin gets its own
`<section class="node-group" data-origin="...">`) — see `docs/UI.md` and
`docs/FEDERATION.md`.

## 5. State directory

Federation/registry state is separate from the read-only YAML config.
Default path: `~/.local/state/service-directory`. Override with
`federation.state_dir` in config, or the `SERVICE_REGISTRY_STATE_DIR`
environment variable (see `config.resolve_state_dir()`). Contents:

| File | Contents | Written by |
|---|---|---|
| `identity.json` | This node's `device_id` (stable UUID) | `identity.load_or_create_identity()` |
| `peers.json` | Trusted peers: name, `device_id`, `base_url`, per-peer bearer token | `trust_store.py` |
| `registry.json` | Dynamic service entries | `registry.py` |
| `write_token.json` | The single shared write token | `write_token.py` |

Every file in this directory is written atomically (write to `.tmp`, then
`os.replace`) with file mode `0600`, and read fresh from disk on every
access — never cached in the process.

## 6. Config schema

Loaded by `config.parse_config()` from a YAML document. Both `host_addresses`
and `services` are **required, non-empty** top-level lists; a missing,
empty, or malformed config raises `ConfigError` with a specific message
rather than crashing.

### `host_addresses[]` (required, non-empty list)

Each entry resolves to one clickable link per service (tailnet-first is a
config-authoring convention — list the tailnet address first).

| Key | Type | Default | Notes |
|---|---|---|---|
| `label` | string | — (required) | Display label, e.g. `"Tailnet"` |
| `host` | string | — (required) | Hostname or IP |
| `scheme` | string | `"http"` | Optional; `"http"` or `"https"` only |

Example:

```yaml
host_addresses:
  - {label: "Tailnet", host: "100.111.191.22"}
  - {label: "LAN",     host: "192.168.1.86"}
  - {label: "Tailnet (TLS)", host: "100.111.191.22", scheme: "https"}
```

### `services[]` (optional list; `[]` is valid)

| Key | Type | Default | Notes |
|---|---|---|---|
| `name` | string | — (required) | Must be unique across static entries |
| `port` | int | — (required) | |
| `path` | string | `"/"` | URL path appended after `host:port` |
| `description` | string | `null` | Free text |
| `category` | string | `null` | Free text, shown as a badge |
| `tags` | list[str] | `[]` | Shown as chips, searchable |
| `icon` | string | `null` | Emoji or short text shown before the name |
| `owner` | string | `null` | Free text |
| `docs_url` | string | `null` | **Must** be `http`/`https` — enforced at load time (`is_safe_docs_url`); any other scheme raises `ConfigError` |
| `scheme` | string | `null` (inherits host address's scheme) | Per-service override; wins over the host address's own scheme |
| `view_url` | string | `null` (falls back to primary resolved link) | URL the in-app viewer opens; must be `http`/`https` |
| `view_kind` | string | `null` (behaves as `"auto"`) | One of `"auto"` / `"iframe"` / `"json"` — see `docs/UI.md` |
| `view_refresh_seconds` | int | `null` | Positive integer; JSON view auto-refresh interval; ignored for other view kinds |

Example (matches `config.sample.yaml`):

```yaml
services:
  - {name: "Resolve", port: 8080, path: "/", description: "Amplifier Resolve dot-graph pipeline runner",
     category: "pipelines", tags: ["video", "editor"], icon: "🎬", owner: "amplifier-team",
     docs_url: "https://example.invalid/docs/resolve", view_kind: "iframe"}
  - {name: "Context Intelligence", port: 8000, path: "/",
     view_url: "http://100.111.191.22:8000/status", view_kind: "json", view_refresh_seconds: 30}
  - {name: "muxplex", port: 8088}
```

`health_url` is **dynamic-registry only** — it is not a static YAML field
(there is no `health_url` key for a `services[]` entry); it is passed on
`POST /api/services` and used by `GET /api/health` to prefer an HTTP health
probe over the TCP-connect fallback (`health.check_service_entries()`).

### `federation` (optional block; entirely absent = federation off)

| Key | Type | Default | Notes |
|---|---|---|---|
| `enabled` | bool | `false` | Must be `true` to activate any federation behaviour |
| `name` | string | `""` | This node's identity/origin name; falls back to `socket.gethostname()` when empty (`app._local_name()`) |
| `base_url` | string | `""` | Advertised URL, given to peers during pairing (tailnet-first by convention) |
| `state_dir` | string | `null` | Override state directory path (else `SERVICE_REGISTRY_STATE_DIR` env var, else the per-user default) |
| `require_read_token` | bool | `false` | When `true`, read endpoints require the localhost bypass or a valid peer bearer token |
| `require_write_token` | bool | `false` | When `true`, mutation endpoints require an explicit token even from localhost |
| `description` | string | `null` | Optional, PUBLIC (unauthenticated) human description, exposed via `/api/instance-info` and `/api/federation/nodes` |
| `role` | string | `null` | Optional, PUBLIC role label, same exposure as `description` |
| `allow_private_health_targets` | bool | `false` | Opt-in: allow a *dynamic* entry's `health_url`/target to be loopback/link-local/RFC1918-private (default blocked as an SSRF guard) |

Example:

```yaml
federation:
  enabled: true
  name: "amplifier-srv-01"
  base_url: "http://100.111.191.22:80"
  description: "Home lab tailnet node"
  role: "primary"
```

`description`/`role` are intentionally public metadata (same trust tier as
`name`) — operators must not put secrets in them (see `app.instance_info()`
docstring).

## 7. Static UNION dynamic and service-source precedence, summarized

- Read path: `_all_local_services_json()` always computes `static + dynamic`
  fresh, in that order, then federation folds in each peer's own union.
- Write path: only dynamic entries are mutable via the API; static entries
  are config-only and require a config edit + restart to change.
- Collision handling: a `POST /api/services` naming an existing **static**
  service is rejected with `409` — no silent shadowing, ever. A `POST`
  naming an existing **dynamic** service is an upsert (replace).
