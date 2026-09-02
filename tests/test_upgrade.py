from __future__ import annotations

import subprocess

from service_directory.install_source import InstallSource
from service_directory.service_manager import ServiceResult
from service_directory.upgrade import run_upgrade


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _FakeManager:
    def __init__(self):
        self.calls: list[str] = []
        self.stop_ok = True
        self.install_ok = True
        self.start_ok = True

    def stop(self):
        self.calls.append("stop")
        return ServiceResult(
            ok=self.stop_ok, message="stopped" if self.stop_ok else "stop failed"
        )

    def install(self):
        self.calls.append("install")
        return ServiceResult(
            ok=self.install_ok,
            message="installed" if self.install_ok else "install failed",
        )

    def start(self):
        self.calls.append("start")
        return ServiceResult(
            ok=self.start_ok, message="started" if self.start_ok else "start failed"
        )


def test_upgrade_skips_editable_install_without_touching_service():
    manager = _FakeManager()

    def source_detector(name):
        return InstallSource(kind="editable", version="0.1.0", editable=True)

    result = run_upgrade(
        source_detector=source_detector,
        manager_factory=lambda: manager,
        runner=lambda cmd: _completed(returncode=0),
    )

    assert result.skipped is True
    assert result.ok is True
    assert "editable" in result.message.lower()
    assert (
        manager.calls == []
    )  # never stopped/installed/started for an editable install


def test_upgrade_runs_steps_in_correct_order_for_pypi_install():
    manager = _FakeManager()
    runner_calls = []

    def runner(cmd):
        runner_calls.append(cmd)
        return _completed(returncode=0)

    def source_detector(name):
        return InstallSource(kind="pypi", version="0.1.0")

    result = run_upgrade(
        source_detector=source_detector,
        manager_factory=lambda: manager,
        runner=runner,
        doctor_verifier=lambda: True,
    )

    assert result.ok is True
    assert result.skipped is False
    assert result.steps == ["stop", "reinstall", "regenerate_unit", "restart", "verify"]
    assert manager.calls == ["stop", "install", "start"]
    assert any("uv" in c[0] for c in runner_calls)
    assert any("--reinstall" in c for c in runner_calls)


def test_upgrade_stops_before_reinstalling():
    """Explicit ordering assertion: stop must precede the reinstall subprocess call."""
    manager = _FakeManager()
    order: list[str] = []

    def runner(cmd):
        order.append("reinstall")
        return _completed(returncode=0)

    orig_stop = manager.stop

    def tracking_stop():
        order.append("stop")
        return orig_stop()

    manager.stop = tracking_stop

    run_upgrade(
        source_detector=lambda name: InstallSource(kind="pypi", version="0.1.0"),
        manager_factory=lambda: manager,
        runner=runner,
        doctor_verifier=lambda: True,
    )

    assert order.index("stop") < order.index("reinstall")


def test_upgrade_reinstall_failure_stops_the_sequence():
    manager = _FakeManager()

    def runner(cmd):
        return _completed(returncode=1, stderr="network unreachable")

    result = run_upgrade(
        source_detector=lambda name: InstallSource(kind="pypi", version="0.1.0"),
        manager_factory=lambda: manager,
        runner=runner,
    )

    assert result.ok is False
    assert "Reinstall failed" in result.message
    assert manager.calls == ["stop"]  # never got to install/start
    assert result.steps == ["stop", "reinstall"]


def test_upgrade_reports_failure_when_verify_fails():
    manager = _FakeManager()

    result = run_upgrade(
        source_detector=lambda name: InstallSource(kind="git", version="0.1.0"),
        manager_factory=lambda: manager,
        runner=lambda cmd: _completed(returncode=0),
        doctor_verifier=lambda: False,
    )

    assert result.ok is False
    assert result.steps == ["stop", "reinstall", "regenerate_unit", "restart", "verify"]


def test_upgrade_git_install_is_not_skipped():
    """Only editable installs skip -- git installs go through the full
    reinstall sequence."""
    manager = _FakeManager()
    result = run_upgrade(
        source_detector=lambda name: InstallSource(kind="git", version="0.1.0"),
        manager_factory=lambda: manager,
        runner=lambda cmd: _completed(returncode=0),
        doctor_verifier=lambda: True,
    )
    assert result.skipped is False
    assert manager.calls == ["stop", "install", "start"]


def test_upgrade_uses_doctor_verifier_result_not_just_service_state():
    """Even if install/start report ok, an explicit doctor_verifier
    returning False must make the overall result not-ok."""
    manager = _FakeManager()
    manager.install_ok = True
    manager.start_ok = True

    result = run_upgrade(
        source_detector=lambda name: InstallSource(kind="pypi", version="0.1.0"),
        manager_factory=lambda: manager,
        runner=lambda cmd: _completed(returncode=0),
        doctor_verifier=lambda: False,
    )
    assert result.ok is False
