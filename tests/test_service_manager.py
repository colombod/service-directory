from __future__ import annotations

import subprocess

import pytest
from service_directory.service_manager import (
    LaunchdServiceManager,
    SystemdUserServiceManager,
    UnsupportedPlatformError,
    current_path_env,
    get_service_manager,
    render_launchd_plist,
    render_systemd_unit,
    resolve_exec_path,
)


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _RecordingRunner:
    """Injectable subprocess-runner stub: records every command invoked,
    never touches a real shell/systemctl/launchctl."""

    def __init__(self, returncode: int = 0):
        self.calls: list[list[str]] = []
        self.returncode = returncode

    def __call__(self, cmd: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(cmd)
        return _completed(returncode=self.returncode, stdout="ok")


# --- unit/plist rendering (pure string assertions) ------------------------


def test_render_systemd_unit_bakes_path_and_exec_start():
    unit = render_systemd_unit(
        "/usr/local/bin/service-directory", "/usr/bin:/bin:/custom/path"
    )
    assert 'Environment="PATH=/usr/bin:/bin:/custom/path"' in unit
    assert "ExecStart=/usr/local/bin/service-directory serve" in unit
    assert "[Unit]" in unit
    assert "[Service]" in unit
    assert "[Install]" in unit
    assert "WantedBy=default.target" in unit


def test_render_systemd_unit_restarts_on_failure():
    unit = render_systemd_unit("/bin/service-directory", "/usr/bin")
    assert "Restart=on-failure" in unit


def test_render_launchd_plist_bakes_path_and_program_arguments():
    plist = render_launchd_plist("/usr/local/bin/service-directory", "/usr/bin:/bin")
    assert "<string>/usr/local/bin/service-directory</string>" in plist
    assert "<string>serve</string>" in plist
    assert "<key>PATH</key>" in plist
    assert "<string>/usr/bin:/bin</string>" in plist
    assert "<?xml version" in plist
    assert "<key>Label</key>" in plist


def test_render_launchd_plist_includes_log_paths_when_given():
    plist = render_launchd_plist(
        "/bin/service-directory",
        "/usr/bin",
        stdout_path="/var/log/sd.out",
        stderr_path="/var/log/sd.err",
    )
    assert "<key>StandardOutPath</key>" in plist
    assert "<string>/var/log/sd.out</string>" in plist
    assert "<key>StandardErrorPath</key>" in plist
    assert "<string>/var/log/sd.err</string>" in plist


def test_render_launchd_plist_omits_log_paths_when_absent():
    plist = render_launchd_plist("/bin/service-directory", "/usr/bin")
    assert "StandardOutPath" not in plist


# --- current_path_env / resolve_exec_path ---------------------------------


def test_current_path_env_reflects_environment(monkeypatch):
    monkeypatch.setenv("PATH", "/a:/b:/c")
    assert current_path_env() == "/a:/b:/c"


def test_resolve_exec_path_uses_shutil_which(monkeypatch):
    monkeypatch.setattr(
        "service_directory.service_manager.shutil.which",
        lambda name: "/opt/bin/service-directory",
    )
    assert resolve_exec_path() == "/opt/bin/service-directory"


def test_resolve_exec_path_falls_back_when_not_found(monkeypatch):
    monkeypatch.setattr(
        "service_directory.service_manager.shutil.which", lambda name: None
    )
    monkeypatch.setattr("sys.argv", [])
    result = resolve_exec_path("service-directory")
    assert result == "service-directory"


# --- dispatch (get_service_manager) ---------------------------------------


def test_get_service_manager_dispatches_to_systemd_on_linux():
    manager = get_service_manager(system="Linux")
    assert isinstance(manager, SystemdUserServiceManager)


def test_get_service_manager_dispatches_to_launchd_on_darwin():
    manager = get_service_manager(system="Darwin")
    assert isinstance(manager, LaunchdServiceManager)


def test_get_service_manager_raises_clear_error_on_unsupported_platform():
    with pytest.raises(UnsupportedPlatformError, match="Windows"):
        get_service_manager(system="Windows")


# --- SystemdUserServiceManager: hermetic filesystem + stubbed subprocess --


def test_systemd_install_writes_unit_with_baked_path_and_calls_systemctl(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PATH", "/baked/path/bin")
    runner = _RecordingRunner()
    manager = SystemdUserServiceManager(runner=runner, unit_dir=str(tmp_path))

    result = manager.install(exec_path="/opt/bin/service-directory")

    assert result.ok is True
    unit_content = (tmp_path / "service-directory.service").read_text()
    assert 'Environment="PATH=/baked/path/bin"' in unit_content
    assert "ExecStart=/opt/bin/service-directory serve" in unit_content
    assert ["systemctl", "--user", "daemon-reload"] in runner.calls
    assert [
        "systemctl",
        "--user",
        "enable",
        "--now",
        "service-directory.service",
    ] in runner.calls


def test_systemd_install_reports_failure_when_enable_fails(tmp_path):
    runner = _RecordingRunner(returncode=1)
    manager = SystemdUserServiceManager(runner=runner, unit_dir=str(tmp_path))
    result = manager.install(exec_path="/bin/x", path_value="/usr/bin")
    assert result.ok is False


def test_systemd_uninstall_removes_unit_file(tmp_path):
    unit_dir = tmp_path
    unit_path = unit_dir / "service-directory.service"
    unit_path.write_text("[Unit]\n")
    runner = _RecordingRunner()
    manager = SystemdUserServiceManager(runner=runner, unit_dir=str(unit_dir))

    result = manager.uninstall()

    assert result.ok is True
    assert not unit_path.exists()


def test_systemd_uninstall_when_unit_absent_is_still_ok(tmp_path):
    runner = _RecordingRunner()
    manager = SystemdUserServiceManager(runner=runner, unit_dir=str(tmp_path))
    result = manager.uninstall()
    assert result.ok is True
    assert "not present" in result.message


def test_systemd_status_reports_active(tmp_path):
    def custom_runner(cmd):
        return _completed(returncode=0, stdout="active\n")

    manager = SystemdUserServiceManager(runner=custom_runner, unit_dir=str(tmp_path))
    result = manager.status()
    assert result.ok is True
    assert result.message == "active"


def test_systemd_status_reports_inactive(tmp_path):
    def custom_runner(cmd):
        return _completed(returncode=3, stdout="inactive\n")

    manager = SystemdUserServiceManager(runner=custom_runner, unit_dir=str(tmp_path))
    result = manager.status()
    assert result.ok is False
    assert result.message == "inactive"


def test_systemd_start_stop_dispatch_correct_commands(tmp_path):
    runner = _RecordingRunner()
    manager = SystemdUserServiceManager(runner=runner, unit_dir=str(tmp_path))

    manager.start()
    manager.stop()

    assert ["systemctl", "--user", "start", "service-directory.service"] in runner.calls
    assert ["systemctl", "--user", "stop", "service-directory.service"] in runner.calls


def test_systemd_logs_calls_journalctl(tmp_path):
    runner = _RecordingRunner()
    manager = SystemdUserServiceManager(runner=runner, unit_dir=str(tmp_path))
    manager.logs(lines=25)
    assert [
        "journalctl",
        "--user",
        "-u",
        "service-directory.service",
        "-n",
        "25",
        "--no-pager",
    ] in runner.calls


# --- LaunchdServiceManager: hermetic filesystem + stubbed subprocess ------


def test_launchd_install_writes_plist_with_baked_path_and_calls_launchctl(tmp_path):
    runner = _RecordingRunner()
    agent_dir = tmp_path / "agents"
    log_dir = tmp_path / "logs"
    manager = LaunchdServiceManager(
        runner=runner, agent_dir=str(agent_dir), log_dir=str(log_dir)
    )

    result = manager.install(
        exec_path="/opt/bin/service-directory", path_value="/usr/bin:/bin"
    )

    assert result.ok is True
    plist_path = agent_dir / "com.service-directory.serve.plist"
    content = plist_path.read_text()
    assert "<string>/opt/bin/service-directory</string>" in content
    assert "<string>/usr/bin:/bin</string>" in content
    assert any(call[:2] == ["launchctl", "load"] for call in runner.calls)


def test_launchd_uninstall_removes_plist(tmp_path):
    agent_dir = tmp_path / "agents"
    agent_dir.mkdir()
    plist_path = agent_dir / "com.service-directory.serve.plist"
    plist_path.write_text("<plist></plist>")
    runner = _RecordingRunner()
    manager = LaunchdServiceManager(runner=runner, agent_dir=str(agent_dir))

    result = manager.uninstall()

    assert result.ok is True
    assert not plist_path.exists()


def test_launchd_status_uses_launchctl_list(tmp_path):
    runner = _RecordingRunner()
    manager = LaunchdServiceManager(runner=runner, agent_dir=str(tmp_path))
    manager.status()
    assert ["launchctl", "list", "com.service-directory.serve"] in runner.calls


def test_launchd_start_stop_dispatch_correct_commands(tmp_path):
    runner = _RecordingRunner()
    manager = LaunchdServiceManager(runner=runner, agent_dir=str(tmp_path))
    manager.start()
    manager.stop()
    assert ["launchctl", "start", "com.service-directory.serve"] in runner.calls
    assert ["launchctl", "stop", "com.service-directory.serve"] in runner.calls


# --- idempotency: installing twice is stable -------------------------------


def test_systemd_install_twice_is_idempotent(tmp_path):
    runner = _RecordingRunner()
    manager = SystemdUserServiceManager(runner=runner, unit_dir=str(tmp_path))

    first = manager.install(exec_path="/bin/service-directory", path_value="/usr/bin")
    content_first = (tmp_path / "service-directory.service").read_text()

    second = manager.install(exec_path="/bin/service-directory", path_value="/usr/bin")
    content_second = (tmp_path / "service-directory.service").read_text()

    assert first.ok and second.ok
    assert content_first == content_second


# --- real subprocess integration test (no mocking of subprocess itself) --


def test_default_runner_real_subprocess_executes_and_captures_output():
    from service_directory.service_manager import default_runner

    result = default_runner(["python3", "-c", "print('hello-from-real-subprocess')"])
    assert result.returncode == 0
    assert "hello-from-real-subprocess" in result.stdout


def test_default_runner_real_subprocess_captures_nonzero_exit():
    from service_directory.service_manager import default_runner

    result = default_runner(["python3", "-c", "import sys; sys.exit(7)"])
    assert result.returncode == 7
