"""``service-directory upgrade``: stop -> reinstall -> regenerate unit ->
restart -> verify with ``doctor``.

Editable installs (``uv pip install -e .`` / ``pip install -e .``) are
skipped with a clear message -- there is nothing to "reinstall" since the
running code already IS the checkout; the user upgrades by pulling/editing
that checkout directly.

Every step is injectable (the service manager, the subprocess runner used
for ``uv tool install``, and the doctor-verify callable) so the hermetic
test suite can assert step ORDERING with everything stubbed, never
mutating a real system or shelling out for real.

The reinstall step dispatches on the PEP 610 install source detected by
``install_source.py``: a git install reinstalls from ``git+<url>@<ref>``
(the bare package name has no PyPI entry and ``uv`` would fail to find
it), while a pypi install reinstalls by name with ``--reinstall`` as
before.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

from .install_source import (
    DEFAULT_DISTRIBUTION_NAME,
    InstallSource,
    detect_install_source,
)
from .service_manager import ServiceManager, ServiceResult, get_service_manager

CommandRunner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def default_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


@dataclass(frozen=True)
class UpgradeResult:
    """Outcome of an upgrade attempt: ``ok`` plus the ordered log of steps
    actually performed (for display and for tests to assert ordering)."""

    ok: bool
    skipped: bool
    message: str
    steps: list[str] = field(default_factory=list)


def reinstall_via_uv_tool(
    name: str = DEFAULT_DISTRIBUTION_NAME,
    runner: CommandRunner = default_runner,
) -> subprocess.CompletedProcess[str]:
    """Real reinstall step: ``uv tool install --reinstall <name>``.

    Only correct for a **pypi** install. Callers should prefer
    :func:`reinstall_command_for_source` to pick the right invocation.
    """
    return runner(["uv", "tool", "install", "--reinstall", name])


def reinstall_command_for_source(
    source: InstallSource, name: str = DEFAULT_DISTRIBUTION_NAME
) -> list[str]:
    """Build the ``uv tool install`` argv appropriate for how the running
    package was installed (per PEP 610 detection in ``install_source.py``).

    - ``git``/other VCS kinds: reinstall from the install SOURCE (the git
      URL + ref), not the bare package name -- a private/git-only package
      has no PyPI entry, so ``uv tool install <name>`` fails with "No
      solution found". Uses ``--force`` (not ``--reinstall``) since the
      argument is a full install spec, not a package name.
    - ``pypi`` (and any other/unknown kind, as a reasonable fallback):
      reinstall by name with ``--reinstall``, the existing behavior.
    """
    if source.kind == "git" and source.url:
        spec = (
            f"git+{source.url}@{source.commit_id}"
            if source.commit_id
            else f"git+{source.url}"
        )
        return ["uv", "tool", "install", spec, "--force"]
    return ["uv", "tool", "install", "--reinstall", name]


def reinstall_for_source(
    source: InstallSource,
    name: str = DEFAULT_DISTRIBUTION_NAME,
    runner: CommandRunner = default_runner,
) -> subprocess.CompletedProcess[str]:
    """Run the reinstall command appropriate for ``source`` (see
    :func:`reinstall_command_for_source`)."""
    return runner(reinstall_command_for_source(source, name))


DoctorVerifier = Callable[[], bool]


def run_upgrade(
    name: str = DEFAULT_DISTRIBUTION_NAME,
    source_detector: Callable[[str], InstallSource] = detect_install_source,
    manager_factory: Callable[[], ServiceManager] = get_service_manager,
    runner: CommandRunner = default_runner,
    doctor_verifier: DoctorVerifier | None = None,
) -> UpgradeResult:
    """Run the upgrade sequence: stop -> reinstall -> regenerate unit ->
    restart -> verify.

    Returns immediately (without touching the service or reinstalling
    anything) with ``skipped=True`` for an editable install.
    """
    steps: list[str] = []

    source = source_detector(name)
    if source.kind == "editable":
        return UpgradeResult(
            ok=True,
            skipped=True,
            message=(
                "Editable install detected: upgrade skipped. Pull/edit the "
                "checkout directly and restart the service instead."
            ),
            steps=steps,
        )

    manager = manager_factory()

    steps.append("stop")
    manager.stop()

    steps.append("reinstall")
    reinstall_result = reinstall_for_source(source, name, runner)
    if reinstall_result.returncode != 0:
        return UpgradeResult(
            ok=False,
            skipped=False,
            message=(
                "Reinstall failed: "
                f"{(reinstall_result.stderr or reinstall_result.stdout or '').strip()}"
            ),
            steps=steps,
        )

    steps.append("regenerate_unit")
    install_result: ServiceResult = manager.install()

    steps.append("restart")
    # `install()` already starts the service; an explicit `start()` here is
    # a harmless idempotent no-op if it's already running, and recovers if
    # `install()`'s start failed for a transient reason.
    start_result: ServiceResult = manager.start()

    steps.append("verify")
    if doctor_verifier is not None:
        verified = doctor_verifier()
    else:
        verified = start_result.ok or install_result.ok

    ok = install_result.ok and verified
    return UpgradeResult(
        ok=ok,
        skipped=False,
        message="upgrade complete"
        if ok
        else "upgrade completed with warnings; run `doctor` for details",
        steps=steps,
    )


__all__ = [
    "CommandRunner",
    "UpgradeResult",
    "default_runner",
    "reinstall_command_for_source",
    "reinstall_for_source",
    "reinstall_via_uv_tool",
    "run_upgrade",
]
