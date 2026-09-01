from __future__ import annotations

import socket

from service_directory import cli


def test_cli_reports_clear_error_when_port_unavailable(
    monkeypatch, sample_config_path, capsys
):
    """Occupy a real ephemeral port, then point the CLI at it: the CLI must
    print a clear error and return non-zero, never raise/crash-loop."""
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    host, port = blocker.getsockname()

    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", sample_config_path)
    try:
        rc = cli.main(["serve", "--host", host, "--port", str(port)])
        assert rc != 0
        captured = capsys.readouterr()
        assert "cannot bind" in captured.err.lower() or "error" in captured.err.lower()
    finally:
        blocker.close()


def test_cli_reports_clear_error_on_malformed_config(monkeypatch, tmp_path, capsys):
    bad_config = tmp_path / "bad.yaml"
    bad_config.write_text("host_addresses: not-a-list\n")
    monkeypatch.delenv("SERVICE_REGISTRY_CONFIG", raising=False)

    rc = cli.main(["serve", "--config", str(bad_config), "--port", "0"])
    assert rc != 0
    captured = capsys.readouterr()
    assert "error" in captured.err.lower()


def test_cli_default_host_and_port():
    args = cli._parse_args(["serve"])
    # defaults come from env or hardcoded fallback; ensure sane defaults exist
    assert args.host  # non-empty
    assert isinstance(args.port, int)
