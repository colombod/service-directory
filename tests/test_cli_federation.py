"""CLI tests for the pairing/token/peers commands.

These spin up a REAL running instance of the FastAPI app (via uvicorn, on an
ephemeral 127.0.0.1 port -- never a hardcoded port) so `token issue` and
`pair` exercise the actual CLI -> real HTTP -> real server round trip, not a
mocked one. Health/aggregation connectivity checks are stubbed as usual so
no incidental real network I/O happens elsewhere.
"""

from __future__ import annotations

import threading
import time

import pytest
import uvicorn
from service_directory import cli
from service_directory.app import create_app
from service_directory.config import FederationConfig, HostAddress, RegistryConfig, Service


def _all_down(url: str) -> bool:
    return False


class _ServerThread:
    def __init__(self, app):
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> str:
        self.thread.start()
        for _ in range(200):
            if getattr(self.server, "started", False):
                break
            time.sleep(0.01)
        # uvicorn exposes the bound sockets after startup
        sockets = self.server.servers[0].sockets
        host, port = sockets[0].getsockname()[:2]
        return f"http://{host}:{port}"

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


def _config(tmp_path, name):
    return RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[Service(name="svc", port=80)],
        federation=FederationConfig(
            enabled=True,
            name=name,
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / f"state-{name}"),
        ),
    )


@pytest.fixture
def running_node(tmp_path):
    config = _config(tmp_path, "node-under-test")
    app = create_app(config, checker=_all_down)
    server = _ServerThread(app)
    base_url = server.start()
    try:
        yield base_url, config
    finally:
        server.stop()


def test_cli_token_issue_prints_code(running_node, capsys):
    base_url, _config = running_node
    rc = cli.main(["token", "issue", "--url", base_url])
    assert rc == 0
    captured = capsys.readouterr()
    code = captured.out.strip()
    assert len(code) > 10


def test_cli_pair_records_peer_and_prints_confirmation(
    running_node, tmp_path, monkeypatch, capsys
):
    base_url, peer_config = running_node

    # this node's own local config (the "caller")
    caller_config_path = tmp_path / "caller.yaml"
    caller_config_path.write_text(
        "host_addresses:\n  - {label: LAN, host: 10.0.0.2}\n"
        "services:\n  - {name: svc2, port: 81}\n"
        "federation:\n"
        "  enabled: true\n"
        "  name: caller-node\n"
        "  base_url: http://10.0.0.2:80\n"
        f"  state_dir: {tmp_path / 'caller-state'}\n"
    )
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", str(caller_config_path))

    rc = cli.main(["token", "issue", "--url", base_url])
    assert rc == 0
    code = capsys.readouterr().out.strip()

    rc = cli.main(["pair", "--url", base_url, "--code", code])
    assert rc == 0
    out = capsys.readouterr().out
    assert "node-under-test" in out

    from service_directory.trust_store import load_peers

    peers = load_peers(str(tmp_path / "caller-state"))
    assert len(peers) == 1
    assert peers[0].name == "node-under-test"


def test_cli_pair_rejects_invalid_code(running_node, tmp_path, monkeypatch, capsys):
    base_url, _peer_config = running_node
    caller_config_path = tmp_path / "caller2.yaml"
    caller_config_path.write_text(
        "host_addresses:\n  - {label: LAN, host: 10.0.0.3}\n"
        "services:\n  - {name: svc3, port: 82}\n"
        "federation:\n"
        "  enabled: true\n"
        "  name: caller-node-2\n"
        f"  state_dir: {tmp_path / 'caller2-state'}\n"
    )
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", str(caller_config_path))

    rc = cli.main(["pair", "--url", base_url, "--code", "totally-bogus-code"])
    assert rc != 0
    captured = capsys.readouterr()
    assert "error" in captured.err.lower()


def test_cli_peers_list_and_remove(tmp_path, monkeypatch, capsys):
    from service_directory.trust_store import PeerRecord, upsert_peer

    config_path = tmp_path / "conf.yaml"
    state_dir = tmp_path / "state"
    config_path.write_text(
        "host_addresses:\n  - {label: LAN, host: 10.0.0.9}\n"
        "services:\n  - {name: svc, port: 80}\n"
        "federation:\n"
        f"  state_dir: {state_dir}\n"
    )
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", str(config_path))

    upsert_peer(
        str(state_dir),
        PeerRecord(name="peer-1", device_id="d1", base_url="http://p1", token="t1"),
    )

    rc = cli.main(["peers", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "peer-1" in out

    rc = cli.main(["peers", "remove", "peer-1"])
    assert rc == 0
    capsys.readouterr()

    rc = cli.main(["peers", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No trusted peers" in out


def test_cli_peers_remove_unknown_peer_reports_error(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "conf2.yaml"
    state_dir = tmp_path / "state2"
    config_path.write_text(
        "host_addresses:\n  - {label: LAN, host: 10.0.0.9}\n"
        "services:\n  - {name: svc, port: 80}\n"
        "federation:\n"
        f"  state_dir: {state_dir}\n"
    )
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", str(config_path))

    rc = cli.main(["peers", "remove", "ghost"])
    assert rc != 0
    captured = capsys.readouterr()
    assert "error" in captured.err.lower()
