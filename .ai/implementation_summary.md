# Block 3 — Self-management: implementation summary

## New files

- `src/service_directory/install_source.py` — Detects how the running
  package was installed (editable / git / local / pypi / unknown) via PEP
  610 `direct_url.json` read through `importlib.metadata`, fully injectable
  via a `distribution_factory` seam. Also provides a best-effort PyPI
  "is there a newer version" checker (`default_update_checker`,
  `check_for_update`) that never raises and never checks for updates on
  non-pypi installs.
- `src/service_directory/service_manager.py` — `get_service_manager()`
  dispatch API returning a `SystemdUserServiceManager` (Linux, systemd
  `--user` unit) or `LaunchdServiceManager` (macOS, launchd agent plist).
  `install()` bakes the current `PATH` into the generated unit/plist and
  points `ExecStart`/`ProgramArguments` at the `service-directory` console
  script's `serve` subcommand. All subprocess calls (`systemctl`,
  `launchctl`, `journalctl`) go through an injectable `runner` seam.
- `src/service_directory/doctor.py` — `run_doctor()` runs a checklist
  (Python version, config via the existing loader, bind-port availability,
  device identity + trust-store, federation peer reachability, install
  source + available update, service status) with every check independently
  wrapped so one failing check never stops the rest. `format_checklist()`
  renders green check / red x / yellow ! per line (ANSI, optional).
- `src/service_directory/upgrade.py` — `run_upgrade()` implements
  stop -> reinstall (`uv tool install --reinstall`) -> regenerate unit ->
  restart -> verify, in that order; editable installs are detected via
  `install_source` and skipped with a clear message instead of attempting a
  no-op reinstall.

## Modified files (additive only)

- `src/service_directory/cli.py` — added `doctor`, `service
  {install,uninstall,start,stop,status,logs}`, and `upgrade` subparsers and
  their `cmd_*` handlers, wired into `main()`. No existing subcommand,
  function signature, or behavior was changed.
- `README.md` — replaced the stale "Block 3 ... (planned)" status line with
  a real Block 3 section documenting the new `doctor`/`service`/`upgrade`
  commands (reconciliation of now-outdated doc text; no code behavior
  affected).

## New tests

- `tests/test_install_source.py` — editable/git/local/pypi/unknown
  detection (stubbed `Distribution`), malformed/missing/exception-raising
  metadata degrades to `unknown` without raising, `check_for_update`
  branch coverage, plus **real-transport integration tests** against a
  local `http.server.HTTPServer` bound to an ephemeral port (127.0.0.1:0)
  exercising the real `urllib` request/JSON-parse path for success,
  malformed JSON, and 404 responses.
- `tests/test_service_manager.py` — unit/plist rendering asserts baked
  `PATH` and `ExecStart`/`ProgramArguments`; platform dispatch for
  Linux/Darwin/unsupported; systemd/launchd install/uninstall/start/stop/
  status/logs against a stubbed subprocess runner and `tmp_path` unit/agent
  directories (no real system mutation); an idempotent-install test; and a
  real (non-mocked) subprocess integration test via `default_runner`.
- `tests/test_doctor.py` — each check function exercised in isolation
  (ok/warn/fail branches) with stubbed seams; `run_doctor` checklist shape
  and never-crashes-on-bad-config / never-crashes-on-raising-check tests;
  `format_checklist` symbol/message assertions; `run_and_format` exit-code
  semantics.
- `tests/test_upgrade.py` — editable install skips without touching the
  service manager; full stop->reinstall->regenerate->restart->verify
  ordering for pypi/git installs; reinstall failure halts the sequence;
  doctor-verifier failure marks the overall result not-ok even when the
  service reports healthy.

All 192 tests pass (118 pre-existing + 74 new), suite remains
warning-clean under `filterwarnings = ["error::DeprecationWarning"]`.
`config.sample.yaml` and `config.py`'s schema/loader are unchanged; no
existing test was modified.
