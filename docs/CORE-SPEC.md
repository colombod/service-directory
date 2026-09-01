# Block 1 — Core dashboard (specification)

Python/FastAPI. **Fully hermetic**: everything here must build and test WITHOUT the
real environment — connectivity is stubbed in tests, no real ports, no Tailscale.
Real-`:80` bind and real service health are a *local* validation tail, out of scope
for this block's automated tests.

## Config (source of truth — not OS-discovered at runtime)

Path via `SERVICE_REGISTRY_CONFIG`. YAML shape:

```yaml
host_addresses:
  - {label: "Tailnet", host: "100.111.191.22"}   # tailnet-first (precedence)
  - {label: "LAN",     host: "192.168.1.86"}
services:
  - {name: "Resolve",              port: 8080, path: "/", description: "..."}
  - {name: "Context Intelligence", port: 8000, path: "/"}
  - {name: "muxplex",              port: 8088}
  - {name: "muxterm",              port: 8311}
  - {name: "browser-bridge hub",   port: 8900}
```

A malformed config must yield a **clear error**, not a stack-trace crash.

## Endpoints

- `GET /` — one HTML page; each service row shows name, optional description, and
  one clickable link per host address.
- `GET /api/services` — JSON of the resolved services × URLs (the same data the
  HTML renders from — JSON is the source of truth).
- `GET /api/health` — JSON `{service: up|down}`; best-effort, **≤1s per check**,
  connectivity behind an **injectable seam** (stubbed in tests). The page must
  render fine even when every check fails.

## URL construction

For each service, one link per host address: `http://{host}:{port}{path}`
(`path` defaults to `/`). Host addresses are ordered **Tailscale/tailnet-first**.

## Runtime / packaging

- Bind `0.0.0.0:80` by default; host/port configurable via env/flags. A clear,
  non-crash-loop error if `:80` is unavailable so it can be pointed elsewhere.
- Ship `config.sample.yaml` populated with the addresses/services above.
- `README.md` (note it exposes internal service URLs).
- `pyproject.toml` — uv-tool installable, `service-directory` console_script.

## Acceptance (hermetic pytest — no real network)

1. Given a config, `GET /` contains the exact `http://{host}:{port}{path}` for
   every service × address pair.
2. Given the same config, `GET /api/services` returns those exact URLs per service.
3. With the connectivity check stubbed to fail for all, `GET /api/health` returns
   `{service: down}` for each AND `GET /` still renders without error.
4. A malformed config file produces a clear error (no crash).
5. `host_addresses` are applied tailnet-first in rendered links.
