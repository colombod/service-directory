"""Defect 1: `service install` must be able to target a config/host/port
and bake them into the generated systemd unit / launchd plist as
environment entries, so an installed service runs correctly without any
manual drop-in. Falls back to SERVICE_REGISTRY_* env vars, then defaults,
when flags are omitted. A privileged (<1024) port on the systemd --user
path must warn, not crash.

Hermetic: no real systemctl/launchctl, no real installs -- everything goes
through the injectable runner + tmp_path, same pattern as
test_service_manager.py.
"""

from __future__ import annotations

import subprocess

from service_directory import cli
from service_directory.service_manager import (
    LaunchdServiceManager,
    SystemdUserServiceManager,
    render_launchd_plist,
    render_systemd_unit,
    resolve_install_env,
)


def _completed(returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="ok")


class _RecordingRunner:
    def __init__(self, returncode: int = 0):
        self.calls: list[list[str]] = []
        self.returncode = returncode

    def __call__(self, cmd: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(cmd)
        return _completed(returncode=self.returncode)


# --- pure rendering: extra_env baked into unit/plist text ------------------


def test_render_systemd_unit_bakes_extra_env():
    unit = render_systemd_unit(
        "/bin/service-directory",
        "/usr/bin",
        extra_env={
            "SERVICE_REGISTRY_CONFIG": "/etc/sd/config.yaml",
            "SERVICE_REGISTRY_HOST": "127.0.0.1",
            "SERVICE_REGISTRY_PORT": "8080",
        },
    )
    assert 'Environment="SERVICE_REGISTRY_CONFIG=/etc/sd/config.yaml"' in unit
    assert 'Environment="SERVICE_REGISTRY_HOST=127.0.0.1"' in unit
    assert 'Environment="SERVICE_REGISTRY_PORT=8080"' in unit
    # PATH and ExecStart/serve invocation must remain untouched.
    assert 'Environment="PATH=/usr/bin"' in unit
    assert "ExecStart=/bin/service-directory serve\n" in unit


def test_render_systemd_unit_extra_env_defaults_to_no_extra_lines():
    """Backward compatibility: omitting extra_env renders exactly as before."""
    unit = render_systemd_unit("/bin/service-directory", "/usr/bin")
    assert "SERVICE_REGISTRY_CONFIG" not in unit
    assert "SERVICE_REGISTRY_HOST" not in unit
    assert "SERVICE_REGISTRY_PORT" not in unit


def test_render_launchd_plist_bakes_extra_env():
    plist = render_launchd_plist(
        "/bin/service-directory",
        "/usr/bin",
        extra_env={
            "SERVICE_REGISTRY_CONFIG": "/etc/sd/config.yaml",
            "SERVICE_REGISTRY_HOST": "127.0.0.1",
            "SERVICE_REGISTRY_PORT": "8080",
        },
    )
    assert "<key>SERVICE_REGISTRY_CONFIG</key>" in plist
    assert "<string>/etc/sd/config.yaml</string>" in plist
    assert "<key>SERVICE_REGISTRY_HOST</key>" in plist
    assert "<string>127.0.0.1</string>" in plist
    assert "<key>SERVICE_REGISTRY_PORT</key>" in plist
    assert "<string>8080</string>" in plist
    # ProgramArguments still just invokes `serve` -- no extra CLI flags.
    assert "<string>serve</string>" in plist
    # Still valid-looking plist structure and still bakes PATH.
    assert "<key>PATH</key>" in plist
    assert "<string>/usr/bin</string>" in plist


def test_render_launchd_plist_extra_env_defaults_to_absent():
    plist = render_launchd_plist("/bin/service-directory", "/usr/bin")
    assert "SERVICE_REGISTRY_CONFIG" not in plist
    assert "SERVICE_REGISTRY_HOST" not in plist
    assert "SERVICE_REGISTRY_PORT" not in plist


# --- resolve_install_env: flag > env var > default -------------------------


def test_resolve_install_env_prefers_explicit_args():
    env = resolve_install_env(config="/a.yaml", host="1.2.3.4", port=9090)
    assert env == {
        "SERVICE_REGISTRY_CONFIG": "/a.yaml",
        "SERVICE_REGISTRY_HOST": "1.2.3.4",
        "SERVICE_REGISTRY_PORT": "9090",
    }


def test_resolve_install_env_falls_back_to_env_vars(monkeypatch):
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", "/env-config.yaml")
    monkeypatch.setenv("SERVICE_REGISTRY_HOST", "10.0.0.1")
    monkeypatch.setenv("SERVICE_REGISTRY_PORT", "9999")
    env = resolve_install_env()
    assert env == {
        "SERVICE_REGISTRY_CONFIG": "/env-config.yaml",
        "SERVICE_REGISTRY_HOST": "10.0.0.1",
        "SERVICE_REGISTRY_PORT": "9999",
    }


def test_resolve_install_env_falls_back_to_defaults_when_nothing_set(monkeypatch):
    monkeypatch.delenv("SERVICE_REGISTRY_CONFIG", raising=False)
    monkeypatch.delenv("SERVICE_REGISTRY_HOST", raising=False)
    monkeypatch.delenv("SERVICE_REGISTRY_PORT", raising=False)
    env = resolve_install_env()
    # No config default exists -- omitted entirely rather than "None".
    assert "SERVICE_REGISTRY_CONFIG" not in env
    assert env["SERVICE_REGISTRY_HOST"] == "0.0.0.0"
    assert env["SERVICE_REGISTRY_PORT"] == "80"


# --- SystemdUserServiceManager.install(config=, host=, port=) --------------


def test_systemd_install_bakes_config_host_port_into_unit(tmp_path):
    runner = _RecordingRunner()
    manager = SystemdUserServiceManager(runner=runner, unit_dir=str(tmp_path))

    result = manager.install(
        exec_path="/bin/service-directory",
        path_value="/usr/bin",
        config="/etc/sd/config.yaml",
        host="127.0.0.1",
        port=8080,
    )

    assert result.ok is True
    content = (tmp_path / "service-directory.service").read_text()
    assert 'Environment="SERVICE_REGISTRY_CONFIG=/etc/sd/config.yaml"' in content
    assert 'Environment="SERVICE_REGISTRY_HOST=127.0.0.1"' in content
    assert 'Environment="SERVICE_REGISTRY_PORT=8080"' in content
    assert "ExecStart=/bin/service-directory serve\n" in content


def test_systemd_install_falls_back_to_env_vars_when_flags_omitted(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SERVICE_REGISTRY_CONFIG", "/env.yaml")
    monkeypatch.setenv("SERVICE_REGISTRY_HOST", "192.168.1.1")
    monkeypatch.setenv("SERVICE_REGISTRY_PORT", "8090")
    runner = _RecordingRunner()
    manager = SystemdUserServiceManager(runner=runner, unit_dir=str(tmp_path))

    manager.install(exec_path="/bin/service-directory", path_value="/usr/bin")

    content = (tmp_path / "service-directory.service").read_text()
    assert 'Environment="SERVICE_REGISTRY_CONFIG=/env.yaml"' in content
    assert 'Environment="SERVICE_REGISTRY_HOST=192.168.1.1"' in content
    assert 'Environment="SERVICE_REGISTRY_PORT=8090"' in content


def test_systemd_install_privileged_port_warns_but_does_not_crash(tmp_path, capsys):
    runner = _RecordingRunner()
    manager = SystemdUserServiceManager(runner=runner, unit_dir=str(tmp_path))

    result = manager.install(
        exec_path="/bin/service-directory",
        path_value="/usr/bin",
        port=80,
    )

    assert result.ok is True  # never crashes
    captured = capsys.readouterr()
    assert "80" in captured.out
    assert "privileged" in captured.out.lower() or "elevat" in captured.out.lower()


def test_systemd_install_non_privileged_port_does_not_warn(tmp_path, capsys):
    runner = _RecordingRunner()
    manager = SystemdUserServiceManager(runner=runner, unit_dir=str(tmp_path))

    manager.install(
        exec_path="/bin/service-directory",
        path_value="/usr/bin",
        port=8080,
    )

    captured = capsys.readouterr()
    assert "privileged" not in captured.out.lower()


# --- LaunchdServiceManager.install(config=, host=, port=) ------------------


def test_launchd_install_bakes_config_host_port_into_plist(tmp_path):
    runner = _RecordingRunner()
    manager = LaunchdServiceManager(
        runner=runner,
        agent_dir=str(tmp_path / "agents"),
        log_dir=str(tmp_path / "logs"),
    )

    result = manager.install(
        exec_path="/bin/service-directory",
        path_value="/usr/bin",
        config="/etc/sd/config.yaml",
        host="127.0.0.1",
        port=8080,
    )

    assert result.ok is True
    content = (tmp_path / "agents" / "com.service-directory.serve.plist").read_text()
    assert "<key>SERVICE_REGISTRY_CONFIG</key>" in content
    assert "<string>/etc/sd/config.yaml</string>" in content
    assert "<key>SERVICE_REGISTRY_HOST</key>" in content
    assert "<string>127.0.0.1</string>" in content
    assert "<key>SERVICE_REGISTRY_PORT</key>" in content
    assert "<string>8080</string>" in content


# --- CLI wiring: `service install --config --host --port` -----------------


def test_cli_service_install_passes_flags_through_to_manager(monkeypatch, tmp_path):
    """End-to-end through cli.main() with the real SystemdUserServiceManager
    but a stubbed runner + tmp_path -- no real systemctl invoked."""
    monkeypatch.setattr(
        "service_directory.service_manager.get_service_manager",
        lambda: SystemdUserServiceManager(
            runner=_RecordingRunner(), unit_dir=str(tmp_path)
        ),
    )

    rc = cli.main(
        [
            "service",
            "install",
            "--config",
            "/my/config.yaml",
            "--host",
            "127.0.0.1",
            "--port",
            "8080",
        ]
    )

    assert rc == 0
    content = (tmp_path / "service-directory.service").read_text()
    assert 'Environment="SERVICE_REGISTRY_CONFIG=/my/config.yaml"' in content
    assert 'Environment="SERVICE_REGISTRY_HOST=127.0.0.1"' in content
    assert 'Environment="SERVICE_REGISTRY_PORT=8080"' in content


def test_cli_service_install_without_flags_uses_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("SERVICE_REGISTRY_CONFIG", raising=False)
    monkeypatch.delenv("SERVICE_REGISTRY_HOST", raising=False)
    monkeypatch.delenv("SERVICE_REGISTRY_PORT", raising=False)
    monkeypatch.setattr(
        "service_directory.service_manager.get_service_manager",
        lambda: SystemdUserServiceManager(
            runner=_RecordingRunner(), unit_dir=str(tmp_path)
        ),
    )

    rc = cli.main(["service", "install"])

    assert rc == 0
    content = (tmp_path / "service-directory.service").read_text()
    assert 'Environment="SERVICE_REGISTRY_HOST=0.0.0.0"' in content
    assert 'Environment="SERVICE_REGISTRY_PORT=80"' in content
    assert "SERVICE_REGISTRY_CONFIG" not in content
