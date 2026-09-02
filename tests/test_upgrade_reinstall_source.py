"""Defect 2: `upgrade` must reinstall using the PEP 610 install source
already detected by install_source.py, not a bare package name -- a
git-installed (private) tool has no PyPI entry, so `uv tool install <name>`
fails with "No solution found ... no versions of service-directory".

Hermetic: subprocess and install-source detection are both stubbed/injected.
No real installs, no real network.
"""

from __future__ import annotations

import subprocess

from service_directory.install_source import InstallSource
from service_directory.service_manager import ServiceResult
from service_directory.upgrade import (
    reinstall_command_for_source,
    run_upgrade,
)


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _FakeManager:
    def __init__(self):
        self.calls: list[str] = []

    def stop(self):
        self.calls.append("stop")
        return ServiceResult(ok=True, message="stopped")

    def install(self):
        self.calls.append("install")
        return ServiceResult(ok=True, message="installed")

    def start(self):
        self.calls.append("start")
        return ServiceResult(ok=True, message="started")


# --- reinstall_command_for_source: pure argv construction ------------------


def test_reinstall_command_for_git_source_uses_url_and_ref():
    source = InstallSource(
        kind="git",
        version="0.1.0",
        url="https://github.com/example/service-directory.git",
        commit_id="abc123",
    )
    cmd = reinstall_command_for_source(source, name="service-directory")
    assert cmd == [
        "uv",
        "tool",
        "install",
        "git+https://github.com/example/service-directory.git@abc123",
        "--force",
    ]
    # Must NOT be the bare package name -- that's the defect being fixed.
    assert "service-directory" not in cmd[3:] or "git+" in cmd[3]


def test_reinstall_command_for_git_source_without_commit_id_omits_ref():
    source = InstallSource(
        kind="git",
        version="0.1.0",
        url="https://github.com/example/service-directory.git",
        commit_id=None,
    )
    cmd = reinstall_command_for_source(source, name="service-directory")
    assert cmd == [
        "uv",
        "tool",
        "install",
        "git+https://github.com/example/service-directory.git",
        "--force",
    ]


def test_reinstall_command_for_pypi_source_uses_bare_name_and_reinstall():
    source = InstallSource(kind="pypi", version="0.1.0")
    cmd = reinstall_command_for_source(source, name="service-directory")
    assert cmd == ["uv", "tool", "install", "--reinstall", "service-directory"]


def test_reinstall_command_for_git_source_missing_url_falls_back_to_name():
    """Defensive: a malformed git source with no URL must not crash or
    produce a bogus `git+None` spec -- fall back to the pypi-style form."""
    source = InstallSource(kind="git", version="0.1.0", url=None)
    cmd = reinstall_command_for_source(source, name="service-directory")
    assert cmd == ["uv", "tool", "install", "--reinstall", "service-directory"]
    assert "None" not in " ".join(cmd)


# --- run_upgrade: end-to-end dispatch with stubbed source + runner --------


def test_upgrade_git_install_reinstalls_via_git_spec_not_bare_name():
    manager = _FakeManager()
    runner_calls: list[list[str]] = []

    def runner(cmd):
        runner_calls.append(cmd)
        return _completed(returncode=0)

    def source_detector(name):
        return InstallSource(
            kind="git",
            version="0.1.0",
            url="https://github.com/example/service-directory.git",
            commit_id="deadbeef",
        )

    result = run_upgrade(
        source_detector=source_detector,
        manager_factory=lambda: manager,
        runner=runner,
        doctor_verifier=lambda: True,
    )

    assert result.ok is True
    assert runner_calls == [
        [
            "uv",
            "tool",
            "install",
            "git+https://github.com/example/service-directory.git@deadbeef",
            "--force",
        ]
    ]
    # This is the crux of the fix: the bare name must never appear as the
    # reinstall spec for a git install (that's what triggers uv's "No
    # solution found ... no versions of service-directory").
    assert runner_calls[0][3] != "service-directory"


def test_upgrade_pypi_install_still_reinstalls_by_name():
    """Existing pypi behavior must be unchanged: `uv tool install --reinstall <name>`."""
    manager = _FakeManager()
    runner_calls: list[list[str]] = []

    def runner(cmd):
        runner_calls.append(cmd)
        return _completed(returncode=0)

    result = run_upgrade(
        name="service-directory",
        source_detector=lambda name: InstallSource(kind="pypi", version="0.1.0"),
        manager_factory=lambda: manager,
        runner=runner,
        doctor_verifier=lambda: True,
    )

    assert result.ok is True
    assert runner_calls == [
        ["uv", "tool", "install", "--reinstall", "service-directory"]
    ]


def test_upgrade_editable_install_still_skips_with_clear_message():
    """Editable behavior must be unchanged by the reinstall-source dispatch."""
    manager = _FakeManager()

    result = run_upgrade(
        source_detector=lambda name: InstallSource(
            kind="editable", version="0.1.0", editable=True
        ),
        manager_factory=lambda: manager,
        runner=lambda cmd: (_ for _ in ()).throw(
            AssertionError("runner must not be invoked for an editable install")
        ),
    )

    assert result.skipped is True
    assert result.ok is True
    assert "editable" in result.message.lower()
    assert manager.calls == []


def test_upgrade_git_reinstall_failure_reports_clear_message_and_stops():
    """Negative path: a failing git reinstall (e.g. bad ref/network) must
    still surface a clear failure -- never silently treated as success."""
    manager = _FakeManager()

    def runner(cmd):
        return _completed(returncode=1, stderr="fatal: couldn't find remote ref")

    result = run_upgrade(
        source_detector=lambda name: InstallSource(
            kind="git",
            version="0.1.0",
            url="https://github.com/example/service-directory.git",
            commit_id="badref",
        ),
        manager_factory=lambda: manager,
        runner=runner,
    )

    assert result.ok is False
    assert "Reinstall failed" in result.message
    assert manager.calls == ["stop"]  # never got to regenerate_unit/restart
    assert result.steps == ["stop", "reinstall"]
