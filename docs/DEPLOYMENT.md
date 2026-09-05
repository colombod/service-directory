# Deployment

End-to-end guide to stand up one node from scratch, install it as a
background service, put it behind HTTPS, and use the CLI against it. Every
command below is real — copy/paste and adjust host/port/paths for your
environment.

## 1. Install

```bash
git clone <this-repo-url>
cd service-directory
uv tool install .
```

This exposes a `service-directory` console script on your `PATH` (see
`pyproject.toml`).

## 2. Write a config

Copy the sample and edit it for your machine:

```bash
cp config.sample.yaml my-config.yaml
```

At minimum, set `host_addresses` (see `docs/ARCHITECTURE.md` for the full
schema) and your `services:` list. `federation:` can stay commented out for
a single, non-federated node.

## 3. Run it directly (foreground, to sanity-check the config first)

```bash
SERVICE_REGISTRY_CONFIG=./my-config.yaml SERVICE_REGISTRY_PORT=8085 \
  service-directory serve
```

The default bind is `0.0.0.0:80` (`cli.DEFAULT_PORT`); a preflight bind
check (`cli._check_bindable()`) produces a clear "cannot bind" error
instead of crash-looping if the port is unavailable. Verify:

```bash
curl -s http://127.0.0.1:8085/api/services
```

Stop it (Ctrl-C) once you've confirmed it serves before moving to the
background service in step 4.

## 4. Install the background service (systemd `--user` on Linux)

```bash
SERVICE_REGISTRY_CONFIG=$(pwd)/my-config.yaml \
  service-directory service install --port 8085
```

`service install` renders and enables a `systemd --user` unit
(`~/.config/systemd/user/service-directory.service`) that bakes in your
current `PATH` plus the resolved `SERVICE_REGISTRY_CONFIG`/`_HOST`/`_PORT`
(explicit flags win, then the matching env var, then the same defaults as
`serve`) — see `service_manager.resolve_install_env()`. It then runs
`systemctl --user daemon-reload` and `enable --now`.

### Trap 1 — the default port is 80, and a `--user` unit cannot bind it

The default port (80) is privileged; a `systemd --user` service has no
capability to bind it without extra elevation (`CAP_NET_BIND_SERVICE` or a
reverse proxy in front). If you omit `--port`, `service_manager.py` prints
`PRIVILEGED_PORT_WARNING` and installs the unit anyway — it will then fail
to bind at runtime. **Always pass an explicit high port**, e.g.:

```bash
service-directory service install --config ./my-config.yaml --port 8085
```

### Trap 2 — `loginctl enable-linger` is required, or the service dies at logout

A `systemd --user` service's manager instance is normally torn down when
your user session ends (logout, or the SSH connection dropping) — the unit
you just enabled will stop and will NOT come back at next boot unless you
log in again first. Enable lingering once, as root or via `sudo`, so your
user's systemd instance starts at boot and survives logout:

```bash
sudo loginctl enable-linger "$USER"
```

Run this **before** you consider the install "done" — it is easy to
install the unit, see it running in your current session, and only
discover the gap after the next reboot or logout.

Verify both together:

```bash
service-directory service status
curl -s http://127.0.0.1:8085/
```

### Managing the installed service

```bash
service-directory service start       # systemctl --user start
service-directory service stop        # systemctl --user stop
service-directory service status      # systemctl --user is-active
service-directory service logs        # journalctl --user -u service-directory.service
service-directory service uninstall   # disable --now, remove the unit file
```

(macOS: the same subcommands manage a `launchd` agent instead —
`~/Library/LaunchAgents/com.service-directory.serve.plist` — via
`launchctl`; see `service_manager.LaunchdServiceManager`.)

## 5. HTTPS via Tailscale, and the mixed-content rule

To serve the dashboard over HTTPS on your tailnet without touching the app
itself, put it behind `tailscale serve`:

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8085
```

**If the dashboard is reached over HTTPS, every link and `view_url` the
page renders must ALSO be HTTPS.** A browser silently blocks `http://`
content loaded from inside an HTTPS page (mixed content) — there is no
error in the UI, the iframe/link just renders nothing, and it looks like a
layout bug rather than a blocked resource. This has bitten this project
twice already (see `AGENTS.md` §4) — once for local services, once for
federated ones. Concretely: if you put the dashboard behind
`--https=443`, every `host_addresses[].scheme`, every service's `scheme`
override, and every `view_url` must be `"https"`/`https://` too. Prefer
catching this at config-load time (a mismatched scheme is a config bug) to
shipping a blank pane silently.

## 6. Targeting an upstream that already speaks TLS

If a service in your catalogue already terminates TLS itself (self-signed
or otherwise), `tailscale serve`'s own target argument must use its
`https+insecure://` pseudo-scheme so it accepts that certificate:

```bash
tailscale serve --bg --https=443 https+insecure://127.0.0.1:9090
```

Pointing plain `http://` at an upstream that only speaks TLS does not work
— the TCP connection succeeds but the HTTP parser chokes on the TLS
handshake bytes, so requests through the proxy fail. The same rule applies
to this app's own `GET /api/view-proxy` and `GET /api/embed-probe`: both do
a plain `urllib` fetch of whatever scheme you configured in `view_url`; if
the target scheme is `http` but the service actually speaks TLS, the fetch
fails and `/api/view-proxy` returns `502 upstream fetch failed: ...`. Set
the service's `scheme`/`view_url` to `https://` to match reality.

## 7. Nodes bound to a non-loopback address

If a node's `serve` process is bound to a specific interface address
(`--host 100.111.191.22`, say) rather than `0.0.0.0`/`127.0.0.1`, any proxy
target (health checks, `view_url`, the view-proxy/embed-probe SSRF
allow-list) that expects to reach *that* process must target the address it
is actually bound to — not `127.0.0.1`. `127.0.0.1` only resolves to a
process that is listening on loopback; a process bound only to a real
interface is not reachable there.

## 8. CLI reference

Every verb below is implemented in `src/service_directory/cli.py`. All
commands that load config need `SERVICE_REGISTRY_CONFIG` set (or an
explicit `--config PATH`); commands that talk to an already-running node
default to `http://127.0.0.1:80` — **override `--url`/`--port-server` (or
`--port` for `token issue`) when the node runs on a non-default port**, or
these commands will try port 80 and fail.

| Verb | Purpose | Example |
|---|---|---|
| `serve` | Start the web server | `SERVICE_REGISTRY_CONFIG=./my-config.yaml service-directory serve --port 8085` |
| `token issue` | Mint a one-time pairing code by calling a running node's admin endpoint (localhost bypass) | `service-directory token issue --port 8085` |
| `token issue-write` | Mint/rotate the write token directly against the state dir (no running server needed) | `SERVICE_REGISTRY_CONFIG=./my-config.yaml service-directory token issue-write` |
| `register` | Register a dynamic service (`POST /api/services`) | `service-directory register --name my-agent --port 9001 --port-server 8085` |
| `deregister` | Remove a dynamic service (`DELETE /api/services/{name}`) | `service-directory deregister my-agent --port-server 8085` |
| `heartbeat` | Refresh a ttl'd dynamic entry's liveness | `service-directory heartbeat my-agent --port-server 8085` |
| `pair` | Pair with a peer using a code it issued | `service-directory pair --url http://100.111.191.22:80 --code <CODE>` |
| `peers list` | List trusted peers | `service-directory peers list` |
| `peers remove` | Remove a trusted peer by name | `service-directory peers remove wintermute` |
| `doctor` | Diagnostic checklist; never crashes, each check is independent | `service-directory doctor --port 8085` |
| `service install/start/stop/status/logs/uninstall` | Manage the systemd `--user` unit / launchd agent | `service-directory service install --port 8085` |
| `upgrade` | Stop → reinstall via `uv tool` → regen unit → restart → `doctor` verify | `service-directory upgrade` |

`--config` is accepted (or `SERVICE_REGISTRY_CONFIG` is read) by every
command that needs to resolve the state directory (`register`,
`deregister`, `heartbeat`, `pair`, `peers`, `doctor`, `token issue-write`).
`register`/`deregister`/`heartbeat`/`pair`/`token issue` all talk HTTP to a
running node and need `--url`/`--url-base` (or `--port-server`/`--port`) to
match how that node was actually started — the flag defaults assume port
80, which is wrong for any node installed per Trap 1 above.

## 9. Verifying a fresh install end-to-end

```bash
service-directory doctor --port 8085
```

`doctor` never crashes — every check (Python version, config validity,
port bind availability, device identity/trust store, peer reachability,
install source, service status) is independently wrapped, so one bad check
(e.g. an unreachable peer) never hides the rest of the picture. Exit code
is non-zero only if any check is a hard `fail` (warnings don't fail it).
