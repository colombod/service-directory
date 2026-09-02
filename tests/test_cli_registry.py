"""CLI tests for the registry commands: register, deregister, heartbeat,
and `token issue-write`.

Like test_cli_federation.py, these spin up a REAL running instance of the
FastAPI app (via uvicorn, on an ephemeral 127.0.0.1 port -- never a
hardcoded port) so the commands exercise the actual CLI -> real HTTP ->
real server round trip, not a mocked one.
"""

from __future__ import annotations

import threading
import time

import pytest
import uvicorn
from service_directory import cli
from service_directory.app import create_app


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
        sockets = self.server.servers[0].sockets
        host, port = sockets[0].getsockname()[:2]
        return f"http://{host}:{port}"

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


def _config_path(tmp_path, name):
    config_path = tmp_path / f"{name}.yaml"
    state_dir = tmp_path / f"state-{name}"
    config_path.write_text(
        "host_addresses:\n  - {label: LAN, host: 10.0.0.1}\n"
        "services:\n  - {name: svc, port: 80}\n"
        "federation:\n"
        "  enabled: true\n"
        f"  name: {name}\n"
        "  base_url: http://10.0.0.1:80\n"
        f"  state_dir: {state_dir}\n"
    )
    return str(config_path), str(state_dir)


@pytest.fixture
def running_node(tmp_path):
    config_path, state_dir = _config_path(tmp_path, "cli-registry-node")
    from service_directory.config import load_config

    config = load_config(config_path)
    app = create_app(config, checker=_all_down)
    server = _ServerThread(app)
    base_url = server.start()
    try:
        yield base_url, config_path, state_dir
    finally:
        server.stop()


def test_cli_register_and_deregister_round_trip(running_node, monkeypatch, capsys):
    base_url, config_path, _state_dir = running_node
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", config_path)

    server_port = int(base_url.rsplit(":", 1)[1])
    rc = cli.main(
        [
            "register",
            "--name",
            "cli-agent",
            "--port",
            "9100",
            "--description",
            "registered via cli",
            "--port-server",
            str(server_port),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "cli-agent" in out

    import httpx2 as httpx

    with httpx.Client() as client:
        resp = client.get(f"{base_url}/api/services")
        resp.raise_for_status()
        names = {svc["name"] for svc in resp.json()}
    assert "cli-agent" in names

    rc = cli.main(["deregister", "cli-agent", "--port-server", str(server_port)])
    assert rc == 0
    capsys.readouterr()

    with httpx.Client() as client:
        resp = client.get(f"{base_url}/api/services")
        names = {svc["name"] for svc in resp.json()}
    assert "cli-agent" not in names


def test_cli_register_rejects_static_name_collision(running_node, monkeypatch, capsys):
    base_url, config_path, _state_dir = running_node
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", config_path)
    server_port = int(base_url.rsplit(":", 1)[1])

    rc = cli.main(
        ["register", "--name", "svc", "--port", "1", "--port-server", str(server_port)]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "error" in captured.err.lower()


def test_cli_heartbeat_round_trip(running_node, monkeypatch, capsys):
    base_url, config_path, _state_dir = running_node
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", config_path)
    server_port = int(base_url.rsplit(":", 1)[1])

    rc = cli.main(
        [
            "register",
            "--name",
            "ttl-agent",
            "--port",
            "9200",
            "--ttl",
            "60",
            "--port-server",
            str(server_port),
        ]
    )
    assert rc == 0
    capsys.readouterr()

    rc = cli.main(["heartbeat", "ttl-agent", "--port-server", str(server_port)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ttl-agent" in out


def test_cli_deregister_unknown_service_reports_error(
    running_node, monkeypatch, capsys
):
    base_url, config_path, _state_dir = running_node
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", config_path)
    server_port = int(base_url.rsplit(":", 1)[1])

    rc = cli.main(["deregister", "never-existed", "--port-server", str(server_port)])
    assert rc != 0
    captured = capsys.readouterr()
    assert "error" in captured.err.lower()


def test_cli_token_issue_write_mints_usable_token(tmp_path, monkeypatch, capsys):
    config_path, state_dir = _config_path(tmp_path, "issue-write-node")
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", config_path)

    rc = cli.main(["token", "issue-write"])
    assert rc == 0
    token = capsys.readouterr().out.strip()
    assert len(token) > 10

    from service_directory.write_token import verify_write_token

    assert verify_write_token(state_dir, token) is True


def test_cli_token_issue_write_rotates(tmp_path, monkeypatch, capsys):
    config_path, state_dir = _config_path(tmp_path, "rotate-node")
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", config_path)

    cli.main(["token", "issue-write"])
    first = capsys.readouterr().out.strip()
    cli.main(["token", "issue-write"])
    second = capsys.readouterr().out.strip()

    assert first != second

    from service_directory.write_token import verify_write_token

    assert verify_write_token(state_dir, first) is False
    assert verify_write_token(state_dir, second) is True


def test_cli_register_uses_write_token_for_remote_scenario(
    running_node, monkeypatch, capsys
):
    """Exercise the --token flag explicitly (simulating a non-localhost
    write-token-gated registration path end to end over real HTTP)."""
    base_url, config_path, state_dir = running_node
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", config_path)
    server_port = int(base_url.rsplit(":", 1)[1])

    from service_directory.write_token import issue_write_token

    token = issue_write_token(state_dir)

    rc = cli.main(
        [
            "register",
            "--name",
            "token-agent",
            "--port",
            "9300",
            "--port-server",
            str(server_port),
            "--token",
            token,
        ]
    )
    assert rc == 0

    import httpx2 as httpx

    with httpx.Client() as client:
        resp = client.get(f"{base_url}/api/services")
        names = {svc["name"] for svc in resp.json()}
    assert "token-agent" in names
