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

## Run (once built)

```bash
SERVICE_REGISTRY_CONFIG=./config.sample.yaml service-directory serve
```
