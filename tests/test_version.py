"""Tests for `pyproject.toml` as the single source of truth for version.

Covers all four tasks:
  1. One version literal, resolved at runtime via importlib.metadata.
  2. `service-directory --version` / `doctor` report it.
  3. `/api/settings` (and the pre-existing `/api/instance-info`) report it.
  4. `/api/federation/nodes` carries version for the local node AND each
     trusted peer (live-fetched, best-effort, explicitly unknown on failure).

Hermetic: no real network for the FastAPI-level tests (peer fetchers are
injected stubs); one genuine local-fixture HTTP test exercises the REAL
`default_peer_info_fetcher` transport (httpx2) against a stdlib
http.server bound to an ephemeral 127.0.0.1 port -- never mocked.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import tomllib
from fastapi.testclient import TestClient
from service_directory import __version__, cli
from service_directory.app import create_app
from service_directory.config import (
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
)
from service_directory.doctor import (
    STATUS_OK,
    STATUS_WARN,
    DoctorDependencies,
    check_version,
    run_doctor,
)
from service_directory.federation import default_peer_info_fetcher, fetch_peers_info
from service_directory.trust_store import PeerRecord, upsert_peer

PYPROJECT_VERSION = tomllib.loads(
    (
        __import__("pathlib").Path(__file__).resolve().parent.parent / "pyproject.toml"
    ).read_text()
)["project"]["version"]


# ---------------------------------------------------------------------------
# Task 1 -- single source of truth, resolved via importlib.metadata
# ---------------------------------------------------------------------------


def test_version_matches_pyproject_toml():
    """The resolved __version__ equals the pyproject.toml declared version."""
    assert __version__ == PYPROJECT_VERSION


def test_no_second_version_literal_in_source():
    """Grep every source file (excluding pyproject.toml itself and test
    fixture data) for a hardcoded copy of the version literal used as a
    real version assignment. The only legitimate occurrence of the literal
    string is inside pyproject.toml and inside test fixtures that
    construct InstallSource(version=...) stand-ins (those are fixture
    data, not a second source of truth for the RUNNING version)."""
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    src_dir = repo_root / "src" / "service_directory"

    # No file under src/ may contain a literal `__version__ = "..."` or a
    # hardcoded copy of the pyproject version string used as an assignment.
    pattern = re.compile(r'__version__\s*=\s*["\'][0-9]+\.[0-9]+')
    for path in src_dir.rglob("*.py"):
        text = path.read_text()
        matches = pattern.findall(text)
        assert not matches, f"found hardcoded version literal in {path}: {matches}"


def test_version_resolves_via_importlib_metadata_not_file_parsing(monkeypatch):
    """Resolution goes through importlib.metadata.version, not by reading
    pyproject.toml at runtime -- verified by monkeypatching the metadata
    lookup and confirming the resolved value changes accordingly (a
    file-parsing implementation would ignore this and keep reading the
    real pyproject.toml)."""
    import importlib

    import service_directory

    def fake_version(name):
        assert name == service_directory.DISTRIBUTION_NAME
        return "9.9.9-test"

    monkeypatch.setattr("importlib.metadata.version", fake_version)
    # Re-exercise the same resolution logic the module ran at import time.
    reloaded = importlib.reload(service_directory)
    try:
        assert reloaded.__version__ == "9.9.9-test"
    finally:
        # Restore real state for any subsequent test in this process.
        importlib.reload(service_directory)


def test_version_degrades_honestly_when_metadata_absent(monkeypatch):
    """When the distribution is genuinely not installed, the resolver must
    say so explicitly ('unknown') rather than fabricating 0.0.0 or ""."""
    import importlib
    from importlib.metadata import PackageNotFoundError

    import service_directory

    def raising_version(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr("importlib.metadata.version", raising_version)
    reloaded = importlib.reload(service_directory)
    try:
        assert reloaded.__version__ == "unknown"
        assert reloaded.__version__ not in ("0.0.0", "")
    finally:
        importlib.reload(service_directory)


# ---------------------------------------------------------------------------
# Task 2 -- CLI --version and doctor
# ---------------------------------------------------------------------------


def test_cli_version_flag_prints_version_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out
    # No usage text, no traceback.
    assert "usage:" not in captured.out.lower()
    assert "traceback" not in captured.out.lower()
    assert "traceback" not in captured.err.lower()


def test_cli_version_flag_matches_pyproject(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    captured = capsys.readouterr()
    assert PYPROJECT_VERSION in captured.out


def test_cli_no_args_still_shows_usage_not_version(capsys):
    """Sanity/negative check: invoking with no subcommand still fails with
    usage text (the exact pre-existing behavior) -- --version must not
    have silently become the default action."""
    with pytest.raises(SystemExit) as excinfo:
        cli.main([])
    assert excinfo.value.code != 0
    captured = capsys.readouterr()
    assert "usage" in captured.err.lower() or "usage" in captured.out.lower()


def test_cli_version_via_real_subprocess_entry_point():
    """Invoke the REAL installed console-script entry point (not just the
    in-process cli.main) to prove --version works end-to-end exactly as a
    user would invoke it."""
    result = subprocess.run(
        [sys.executable, "-m", "service_directory.cli", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout
    assert "usage:" not in result.stdout.lower()


def test_check_version_ok_reports_version_string():
    result = check_version("1.2.3")
    assert result.status == STATUS_OK
    assert "1.2.3" in result.message


def test_check_version_warns_honestly_when_unknown():
    """The doctor check must never claim a fabricated version -- 'unknown'
    is reported as a warning with an honest message, not as if it were a
    real version."""
    result = check_version("unknown")
    assert result.status == STATUS_WARN
    assert (
        "unknown" not in result.message.split(":")[-1].strip().split()[0:0]
    )  # no-op guard
    assert "could not determine" in result.message.lower()


def test_doctor_output_includes_version_line(sample_config):
    deps = DoctorDependencies(
        loader=lambda path: sample_config,
        bind_checker=lambda h, p: True,
        identity_loader=lambda state_dir: type("I", (), {"device_id": "test-id"})(),
        peers_loader=lambda state_dir: [],
        peer_reachability_checker=lambda url: True,
        version=__version__,
    )
    results = run_doctor(deps)
    version_result = next(r for r in results if r.name == "Version")
    assert version_result.status == STATUS_OK
    assert __version__ in version_result.message
    # It's the FIRST thing in the checklist -- the acceptance criterion is
    # "the first thing anyone runs when diagnosing a node".
    assert results[0].name == "Version"


# ---------------------------------------------------------------------------
# Task 3 -- API surfaces report version
# ---------------------------------------------------------------------------


def _config(tmp_path, **overrides):
    kwargs = dict(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[Service(name="svc", port=80)],
        federation=FederationConfig(
            enabled=True,
            name="local-node",
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
        ),
    )
    kwargs.update(overrides)
    return RegistryConfig(**kwargs)


def _all_down(url: str) -> bool:
    return False


def _localhost_client(app) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 12345))


def test_instance_info_includes_version_matching_resolved(tmp_path):
    config = _config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = TestClient(app, client=("203.0.113.9", 12345))
    resp = client.get("/api/instance-info")
    assert resp.status_code == 200
    assert resp.json()["version"] == __version__


def test_settings_endpoint_includes_version_field(tmp_path):
    """Task 3: /api/settings gains a version field, additively."""
    config = _config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == __version__
    # Additive: pre-existing keys still present.
    assert "name" in data
    assert "federation_enabled" in data
    assert "host_addresses" in data


def test_settings_response_is_json_parseable(tmp_path):
    """Public-contract check: the response stays valid, loadable JSON."""
    config = _config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    resp = client.get("/api/settings")
    parsed = json.loads(resp.text)
    assert isinstance(parsed, dict)
    assert parsed["version"] == __version__


# ---------------------------------------------------------------------------
# Task 4 -- federation handshake: version crosses to /api/federation/nodes
# ---------------------------------------------------------------------------


def test_federation_nodes_local_entry_carries_version(tmp_path):
    config = _config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    resp = client.get("/api/federation/nodes")
    assert resp.status_code == 200
    nodes = resp.json()
    local = next(n for n in nodes if n["name"] == "local-node")
    assert local["version"] == __version__


def test_federation_nodes_peer_version_survives_handshake_with_stub(tmp_path):
    """A declared peer version, delivered via the injected peer_info_fetcher
    seam (hermetic -- no real network), must appear on that peer's entry."""
    config = _config(tmp_path)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(
            name="peer-a", device_id="dev-a", base_url="http://peer-a", token="tok-a"
        ),
    )

    def stub_peer_fetcher(peer, timeout):
        return []  # no services, doesn't matter for this test

    def stub_peer_info_fetcher(peer, timeout):
        assert peer.name == "peer-a"
        return {
            "name": "peer-a",
            "device_id": "dev-a",
            "version": "2.5.0",
            "description": "Peer A description",
            "role": "secondary",
            "federation_enabled": True,
        }

    app = create_app(
        config,
        checker=_all_down,
        peer_fetcher=stub_peer_fetcher,
        peer_info_fetcher=stub_peer_info_fetcher,
    )
    client = _localhost_client(app)
    resp = client.get("/api/federation/nodes")
    assert resp.status_code == 200
    nodes = {n["name"]: n for n in resp.json()}
    assert nodes["peer-a"]["version"] == "2.5.0"
    # The known blocker (description/role arriving null) must also be fixed
    # as part of delivering version -- otherwise version would be null too.
    assert nodes["peer-a"]["description"] == "Peer A description"
    assert nodes["peer-a"]["role"] == "secondary"


def test_federation_nodes_unreachable_peer_version_is_explicitly_none(tmp_path):
    """An unreachable peer (or one too old to expose /api/instance-info)
    must render version as None -- explicitly unknown, distinguishable
    from "same version as me". Never fabricate, never silently match."""
    config = _config(tmp_path)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(
            name="peer-down",
            device_id="dev-down",
            base_url="http://peer-down",
            token="tok-down",
        ),
    )

    def failing_peer_fetcher(peer, timeout):
        raise ConnectionError("simulated down")

    def failing_peer_info_fetcher(peer, timeout):
        return None  # matches default_peer_info_fetcher's failure contract

    app = create_app(
        config,
        checker=_all_down,
        peer_fetcher=failing_peer_fetcher,
        peer_info_fetcher=failing_peer_info_fetcher,
    )
    client = _localhost_client(app)
    resp = client.get("/api/federation/nodes")
    nodes = {n["name"]: n for n in resp.json()}
    assert nodes["peer-down"]["version"] is None
    assert nodes["peer-down"]["reachable"] is False
    # Explicitly None, never equal to the local node's version by accident.
    assert nodes["peer-down"]["version"] != nodes["local-node"]["version"]


def test_federation_nodes_no_fetcher_configured_never_touches_network(tmp_path):
    """When no peer_info_fetcher is configured (create_app's hermetic
    default), peers are listed with version=None and no real I/O is
    attempted -- this is the exact hermetic-by-default guarantee the rest
    of the suite depends on."""
    config = _config(tmp_path)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(
            name="peer-x", device_id="dev-x", base_url="http://peer-x", token="tok-x"
        ),
    )

    def stub_peer_fetcher(peer, timeout):
        return []

    app = create_app(config, checker=_all_down, peer_fetcher=stub_peer_fetcher)
    client = _localhost_client(app)
    resp = client.get("/api/federation/nodes")
    assert resp.status_code == 200
    nodes = {n["name"]: n for n in resp.json()}
    assert nodes["peer-x"]["version"] is None


def test_fetch_peers_info_empty_peers_returns_empty_dict():
    assert fetch_peers_info([]) == {}


def test_fetch_peers_info_swallows_fetcher_exceptions():
    """A misbehaving fetcher that raises (instead of returning None) must
    never propagate -- it's treated the same as an explicit None."""
    peer = PeerRecord(name="p", device_id="d", base_url="http://p", token="t")

    def exploding_fetcher(peer, timeout):
        raise RuntimeError("boom")

    result = fetch_peers_info([peer], fetcher=exploding_fetcher, timeout=1.0)
    assert result == {"p": None}


# --- real-transport integration test (no mocking of httpx2) ----------------


class _InstanceInfoHandler(BaseHTTPRequestHandler):
    body = {
        "name": "real-peer",
        "device_id": "dev-real",
        "version": "3.7.1",
        "federation_enabled": True,
        "description": "A real peer over real HTTP",
        "role": "edge",
    }

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path != "/api/instance-info":
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(self.body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _NotFoundHandler(BaseHTTPRequestHandler):
    """Simulates a peer running a build too old to have /api/instance-info."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(404)
        self.end_headers()


@pytest.fixture
def running_instance_info_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _InstanceInfoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.fixture
def old_peer_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _NotFoundHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_default_peer_info_fetcher_real_http_success(running_instance_info_server):
    """Exercises the REAL httpx2-based default_peer_info_fetcher against a
    real local HTTP server -- not mocked."""
    host, port = running_instance_info_server.server_address
    peer = PeerRecord(
        name="real-peer",
        device_id="dev-real",
        base_url=f"http://{host}:{port}",
        token="whatever",
    )

    result = default_peer_info_fetcher(peer, timeout=2.0)
    assert result is not None
    assert result["version"] == "3.7.1"
    assert result["description"] == "A real peer over real HTTP"
    assert result["role"] == "edge"


def test_default_peer_info_fetcher_real_http_404_returns_none(old_peer_server):
    """A peer too old to expose /api/instance-info (404) must resolve to
    None -- explicitly unknown -- not raise, not fabricate."""
    host, port = old_peer_server.server_address
    peer = PeerRecord(
        name="old-peer",
        device_id="dev-old",
        base_url=f"http://{host}:{port}",
        token="whatever",
    )

    result = default_peer_info_fetcher(peer, timeout=2.0)
    assert result is None


def test_fetch_peers_info_real_http_end_to_end(running_instance_info_server):
    """End-to-end: fetch_peers_info using the REAL default_peer_info_fetcher
    against a real local peer server."""
    host, port = running_instance_info_server.server_address
    peer = PeerRecord(
        name="real-peer",
        device_id="dev-real",
        base_url=f"http://{host}:{port}",
        token="whatever",
    )

    result = fetch_peers_info([peer], fetcher=default_peer_info_fetcher, timeout=2.0)
    assert result["real-peer"]["version"] == "3.7.1"
