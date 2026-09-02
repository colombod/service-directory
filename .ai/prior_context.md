# Prior Context: Block 3 (Self-management) Implementation

## Source Notes
- **Repo history (git log)**: Blocks 1 and 2 were added by Amplifier Resolve in two automated commits. Block 1 = core dashboard (config, URLs, app, health, CLI serve). Block 2 = federation (auth, identity, pairing, trust_store, federation, CLI pairing/peers/token commands).
- **CI graph**: Only current-session events found; no prior Block 3 runs.

---

## Existing Code Structure & Conventions

### Module layout
```
src/service_directory/
  __init__.py         # __version__ = "0.1.0"
  config.py           # load_config, parse_config, ConfigError, RegistryConfig, resolve_state_dir
  cli.py              # main(), _parse_args(), cmd_* functions; subparsers pattern
  app.py              # FastAPI app; create_app(), create_app_from_env()
  health.py           # check_services(), default_checker(); injectable Checker seam
  identity.py         # load_or_create_identity(), DeviceIdentity
  trust_store.py      # load_peers(), PeerRecord; always read fresh from disk
  federation.py       # aggregate_services(); injectable PeerFetcher seam
  auth.py             # require_admin(), require_read_access()
  pairing.py          # PairingCodeStore
  urls.py             # resolve_all()
```

### CLI pattern (cli.py)
- `_parse_args()` uses `argparse.ArgumentParser` with `subparsers.add_parser()`
- Each command has a `cmd_<name>()` function returning int exit code
- `main()` dispatches on `args.command` / `args.<sub>_command`
- **Additive wiring only**: add new `subparsers.add_parser()` calls + new `if args.command == ...` branches in `main()`
- Existing `_check_bindable()` in cli.py is the exact same socket pattern doctor needs for port check

### Testing conventions
- `filterwarnings = ["error::DeprecationWarning"]` in pyproject.toml — no deprecated APIs
- All tests are hermetic: no real network, no real systemctl; stub via dependency injection
- `conftest.py` provides `sample_config_path` and `sample_config` fixtures
- Pattern: injectable seam (function parameter with default) rather than monkeypatching internals
- Test style: simple functions, no classes unless needed; `monkeypatch` for env vars

### Config constraints (DO NOT CHANGE)
- `services` is a LIST of objects; `host_addresses` is a LIST — exactly as in config.sample.yaml
- Use `load_config(path)` / `parse_config(text)` from existing config.py; do not rewrite
- `resolve_state_dir(config)` for state dir

---

## Block 3 Implementation Details

### 1. `doctor.py` — Checklist runner
- **Checks** (never crash; each wrapped in try/except):
  1. Python version: `sys.version_info >= (3, 11)`
  2. Config present+valid: call `load_config(path)` — ConfigError = red, success = green
  3. Bind port available: same socket pattern as `_check_bindable()` in cli.py
  4. Device identity: `load_or_create_identity(state_dir)` — show device_id
  5. Trust store: `load_peers(state_dir)` — count peers
  6. Federation peers reachability: call `health.default_checker(peer.base_url)` for each peer (best-effort)
  7. Install source: via `importlib.metadata` `direct_url.json` (see below)
  8. Service status: run `systemctl --user is-active service-directory` (Linux) or `launchctl list com.service-directory` (macOS)
- **Colors**: plain ANSI codes (no colorama dependency — not in pyproject.toml). `GREEN='\033[32m'`, `RED='\033[31m'`, `YELLOW='\033[33m'`, `RESET='\033[0m'`. Symbols: ✓ / ✗ / !
- **Injectable seam**: accept a `checks` parameter or individual check functions for testability
- **Return**: list of `CheckResult(label, status, detail)` dataclass; `status` in `{"ok","fail","warn"}`; print then return exit 0 (always, never crash)

### 2. `install_source.py` — PEP 610 detection
```python
import importlib.metadata as m, json

def detect_install_source(package_name="service-directory"):
    try:
        dist = m.distribution(package_name)
        version = dist.metadata["Version"]
        du_text = dist.read_text("direct_url.json")
        if not du_text:
            return InstallSource(kind="pypi", version=version, url=None, editable=False)
        du = json.loads(du_text)
        if "vcs_info" in du:
            return InstallSource(kind="git", version=version, url=du["url"], editable=False)
        elif "dir_info" in du:
            editable = du["dir_info"].get("editable", False)
            return InstallSource(kind="editable" if editable else "local", version=version, url=du["url"], editable=editable)
        elif "archive_info" in du:
            return InstallSource(kind="pypi", version=version, url=du["url"], editable=False)
        return InstallSource(kind="unknown", version=version, url=None, editable=False)
    except Exception:
        return InstallSource(kind="unknown", version=None, url=None, editable=False)
```
- **Editable installs**: upgrade should skip with clear message (not error)

### 3. `service_manager.py` — systemd/launchd dispatch
- **Dispatch API**: `class ServiceManager` with `install()`, `uninstall()`, `start()`, `stop()`, `status()`, `logs()` methods
- **Platform detection**: `platform.system()` → `"Linux"` (systemd) or `"Darwin"` (launchd)
- **Unit name**: `service-directory` (systemd) / `com.service-directory` (launchd label)
- **Systemd user unit** path: `~/.config/systemd/user/service-directory.service`
- **Launchd plist** path: `~/Library/LaunchAgents/com.service-directory.plist`
- **PATH baking**: find `service-directory` console script via `shutil.which('service-directory')`, take its parent dir, prepend to `os.environ['PATH']` in the unit
- **ExecStart**: absolute path to `service-directory serve` (from `shutil.which`)
- **systemd commands**: `systemctl --user {daemon-reload,enable,start,stop,status,is-active}`, `journalctl --user -u service-directory -n 50`
- **launchd commands**: `launchctl load/unload/start/stop/list`
- **Injectable subprocess runner** for tests: accept `run_fn=subprocess.run` parameter

### 4. `upgrade.py` — upgrade flow
- **Steps**: stop → `uv tool install --reinstall service-directory` → regenerate unit (install) → restart → doctor verify
- **Editable check**: detect via `install_source.detect_install_source()` — if editable, print message and return 0 (skip)
- **Injectable**: accept `run_fn` for subprocess, `manager` for ServiceManager, `doctor_fn` for doctor

### 5. CLI wiring (cli.py — additive only)
Add these subparsers:
- `doctor` — `--config`, `--port`
- `service {install,uninstall,start,stop,status,logs}` — `--config`
- `upgrade` — `--config`

---

## Test Patterns for New Modules

### test_doctor.py
```python
def test_doctor_returns_checklist(monkeypatch):
    # stub load_config to succeed
    # stub socket bind to succeed  
    # stub load_or_create_identity
    # stub load_peers
    # stub subprocess for systemctl
    results = run_doctor(config_path="...", checks=[...injected stubs...])
    assert any(r.label == "Python version" for r in results)
    assert all(r.status in ("ok", "fail", "warn") for r in results)
```

### test_service_manager.py
```python
def test_systemd_unit_content_bakes_path_and_execstart():
    mgr = ServiceManager(exec_path="/home/user/.local/bin/service-directory",
                         path_env="/home/user/.local/bin:/usr/bin:/bin")
    unit = mgr.render_unit()
    assert "/home/user/.local/bin/service-directory serve" in unit
    assert "Environment=PATH=" in unit
    assert "/home/user/.local/bin" in unit

def test_launchd_plist_bakes_path_and_execstart():
    # similar for macOS plist
```

### test_install_source.py
```python
def test_editable_detection(monkeypatch):
    # monkeypatch importlib.metadata.distribution to return fake dist
    # with direct_url.json = '{"url":"file:///path","dir_info":{"editable":true}}'
    src = detect_install_source()
    assert src.kind == "editable"
    assert src.editable is True

def test_git_detection(monkeypatch): ...
def test_pypi_detection(monkeypatch): ...
```

### test_upgrade.py
```python
def test_upgrade_skips_editable(monkeypatch):
    # stub detect_install_source to return editable
    # assert subprocess never called
    rc = run_upgrade(install_source_fn=lambda: editable_src, run_fn=mock_run)
    assert rc == 0  # skip, not error

def test_upgrade_ordering(monkeypatch):
    calls = []
    # stub run_fn to record calls
    run_upgrade(...)
    assert calls == ["stop", "uv tool install --reinstall ...", "install unit", "start", "doctor"]
```

---

## Key Pitfalls / Constraints

1. **filterwarnings=error::DeprecationWarning**: Do NOT use `pkg_resources`, deprecated `importlib` APIs, or any other deprecated stdlib. Use `importlib.metadata.distribution()` (Python 3.10+, fine for ≥3.11).
2. **No real subprocess/systemctl in tests**: inject `run_fn` parameter everywhere subprocess is called.
3. **No real network in tests**: doctor's peer reachability check must accept injectable checker.
4. **Doctor never crashes**: every check wrapped in `try/except Exception`.
5. **Editable upgrade**: skip gracefully (print message, return 0), do NOT error.
6. **Unit file PATH baking**: use `shutil.which('service-directory')` at install time to find the console script; take `pathlib.Path(exe).parent` as the bin dir to prepend to PATH in the unit.
7. **Systemd user unit** (not system): always `systemctl --user`, not `systemctl` (no sudo).
8. **`uv tool install --reinstall service-directory`** for upgrade (not `uv tool upgrade` which may not exist in all versions).
9. **Config flag**: doctor's config check uses `--config` flag or `SERVICE_REGISTRY_CONFIG` env var, same as serve.
10. **All existing 118 tests must still pass unchanged** — do not touch any existing module signatures.
