# service-directory

A tiny, config-driven **service registry web dashboard** for a single Linux host —
one HTML page (plus a JSON API for agents) listing the other services running on
this machine, each as clickable links for every configured host address (LAN and
Tailscale), so any device on either network can reach them.

> Security note: this dashboard exposes **internal service URLs**. It ships with no
> auth by design, intended for a trusted LAN + tailnet. Do not expose it publicly.

## Status

Built incrementally via the Amplifier **Resolve** platform (dot-graph resolver),
one substantial hermetic block at a time, with real-environment validation
performed locally (where Tailscale and the real services exist).

- **Block 1 — Core dashboard** (config + URL resolution + `/`, `/api/services`,
  `/api/health` + hermetic pytest). See `docs/CORE-SPEC.md`.
- Block 2 — Federation (per-peer device-token auth, pairing handshake,
  pull-aggregation across peer nodes). *(planned)*
- Block 3 — Self-management (`doctor`, systemd/launchd service install, upgrade,
  uv-tool packaging). *(planned)*

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

## Develop / test

```bash
uv run pytest
```

The test suite is fully hermetic: no real network calls, no real port
binding — connectivity checks are stubbed via dependency injection.
