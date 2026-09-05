# service-directory

A tiny, config-driven **service registry web dashboard** for a single Linux host —
one HTML page (plus a JSON API for agents) listing the other services running on
this machine, each as clickable links for every configured host address (LAN and
Tailscale), so any device on either network can reach them.

> Security note: this dashboard exposes **internal service URLs**. Read endpoints
> (`/`, `/api/services`, `/api/health`) are open by default (opt into
> `federation.require_read_token` to lock them down); admin/federation endpoints
> always require localhost or a valid per-peer token. Intended for a trusted
> LAN + tailnet -- do not expose it publicly.

## Status

Built incrementally via the Amplifier **Resolve** platform (dot-graph resolver),
one substantial hermetic block at a time, with real-environment validation
performed locally (where Tailscale and the real services exist).

- **Block 1 — Core dashboard** (config + URL resolution + `/`, `/api/services`,
  `/api/health` + hermetic pytest). See `docs/CORE-SPEC.md`.
- **Block 2 — Federation** (per-peer device-token auth, pairing handshake,
  pull-aggregation across peer nodes). See below.
- **Block 3 — Self-management** (`doctor`, systemd/launchd service install,
  upgrade, uv-tool packaging). See below.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system shape, module map,
  config schema, and the static/dynamic/federation precedence rules.
- [`docs/API.md`](docs/API.md) — every HTTP endpoint, with auth requirements
  and a runnable `curl` example each.
- [`docs/UI.md`](docs/UI.md) — what a user sees and can do: catalogue,
  filtering, the in-app viewer's `auto`/`iframe`/`json` modes, and Settings.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — install, config, service
  install (systemd/launchd), HTTPS via Tailscale, and the full CLI reference.
- [`docs/FEDERATION.md`](docs/FEDERATION.md) — pairing two nodes end to end,
  and how to actually verify the catalogues merged (not just the handshake).

## Install

```bash
uv tool install .
```

This exposes a `service-directory` console script (see `pyproject.toml`).

## Run

```bash
SERVICE_REGISTRY_CONFIG=./config.sample.yaml service-directory serve
```

By default this binds `0.0.0.0:80`. Override with `--host`/`--port` flags or
the `SERVICE_REGISTRY_HOST`/`SERVICE_REGISTRY_PORT` env vars if port 80 is
unavailable (a preflight check produces a clear error instead of crash-looping
if the requested host/port can't be bound).

- `GET /` — HTML dashboard listing each service with a clickable link per
  configured host address.
- `GET /api/services` — JSON of the resolved services × URLs (same data the
  HTML page renders from).
- `GET /api/health` — best-effort `{service: up|down}` connectivity snapshot
  (≤1s per check); the page still renders even if every check fails.

## Federation (Block 2)

Every node keeps ONLY its own local config -- there is no static peer list.
On every read (`GET /`, `GET /api/services`) the node concurrently fetches
each *trusted peer's* `/api/services` (best-effort, <=1s per peer), merges
the results with its own local list, and tags every entry with its
originating node's name. A down/unreachable peer is silently omitted --
the local list always renders regardless.

Trust between two nodes is established with a short pairing handshake:

```bash
# On node A (the one being paired TO): mint a one-time, ~10-minute code
service-directory token issue --url http://node-a:80

# On node B (the one initiating): present the code + its own identity
service-directory pair --url http://node-a:80 --code <CODE>
```

`pair` calls `POST /api/federation/pair` on the target with the code and
node B's identity; the target validates the code (one-time, expires),
mints a long-lived per-peer token for node B, records it in its trust
store, and returns its own identity + a token for node B to store in
return -- both sides now trust each other via their OWN per-peer token
(revoking one peer never affects any other).

```bash
service-directory peers list
service-directory peers remove <name>
```

Auth model:

- Read endpoints (`/`, `/api/services`, `/api/health`) are **open by
  default**; set `federation.require_read_token: true` in config to require
  a valid peer bearer token.
- Admin endpoints (pairing-code issuance, `/api/federation/pair`) always
  require either a request from `127.0.0.1`/`::1` (the real TCP client
  address -- unforgeable via headers) **or** a valid peer bearer token.
- `GET /api/instance-info` is always unauthenticated and returns only
  `{name, device_id, version, federation_enabled}` -- no secrets, no peer
  list.
- Each peer has its own token, verified with `hmac.compare_digest`, stored
  in `peers.json` (mode `0600`) in the state dir alongside `identity.json`
  (this node's persistent `device_id`). Both are read fresh on every
  request -- no in-process caching -- so CLI changes (e.g. `peers remove`)
  take effect immediately.

Peer/rendered links keep preferring the tailnet address: `host_addresses`
stays tailnet-first exactly as in Block 1.

## Self-management (Block 3)

```bash
service-directory doctor           # colored checklist: python, config, port,
                                    # identity/trust-store, peers, install
                                    # source, service status -- never crashes
service-directory service install [--config PATH] [--host HOST] [--port PORT]
                                    # systemd --user unit (Linux) / launchd
                                    # agent (macOS); bakes current PATH plus
                                    # SERVICE_REGISTRY_CONFIG/_HOST/_PORT in
                                    # (falling back to env vars, then
                                    # defaults, when flags are omitted)
service-directory service {start,stop,status,logs,uninstall}
service-directory upgrade          # stop -> reinstall (uv tool) -> regen
                                    # unit -> restart -> doctor verify
```

`doctor` never crashes: every check is independently wrapped, and a
failure in one (e.g. an unreachable peer, a missing `systemctl`) never
prevents the rest of the checklist from running. `upgrade` detects an
editable install (PEP 610 `direct_url.json`) and skips with a clear
message instead of attempting to reinstall a checkout that has nothing to
reinstall from. A git-installed tool reinstalls from its detected
`git+<url>@<ref>` source rather than a bare package name (which has no
PyPI entry to resolve); a pypi install reinstalls by name as before.

## Develop / test

```bash
uv run pytest
```

The test suite is fully hermetic: no real network calls, no real port
binding — connectivity checks and the peer-fetch HTTP client are stubbed
via dependency injection (with additional local-fixture tests exercising
the real HTTP transport against a `127.0.0.1` server bound to an ephemeral
port).
