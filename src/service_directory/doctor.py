"""``service-directory doctor``: a colored, never-crashing checklist.

Every check is wrapped so a failure in ONE check (an unreadable config, a
network hiccup, a missing systemd binary) never prevents the REST of the
checklist from running -- the whole point of ``doctor`` is to always finish
and show the user a full picture. Every check accepts injectable seams so
the hermetic test suite never binds a real socket, shells out to
``systemctl``, or touches the real network.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass

from . import __version__
from .config import ConfigError, RegistryConfig, load_config, resolve_state_dir
from .install_source import (
    DEFAULT_DISTRIBUTION_NAME,
    InstallSource,
    check_for_update,
    detect_install_source,
)
from .service_manager import (
    ServiceManager,
    ServiceResult,
    UnsupportedPlatformError,
    get_service_manager,
)

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"

_SYMBOLS = {STATUS_OK: "\u2713", STATUS_WARN: "!", STATUS_FAIL: "\u2717"}
_COLORS = {STATUS_OK: "32", STATUS_WARN: "33", STATUS_FAIL: "31"}  # green/yellow/red
_RESET = "\033[0m"

MIN_PYTHON = (3, 11)


@dataclass(frozen=True)
class CheckResult:
    """One line of the checklist: a name, a status, and a human message."""

    name: str
    status: str  # "ok" | "warn" | "fail"
    message: str


def _run_check(name: str, fn: Callable[[], CheckResult]) -> CheckResult:
    """Run one check, converting ANY exception into a "fail" result rather
    than ever letting a single bad check crash the whole checklist."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a single check must never crash doctor
        return CheckResult(
            name=name, status=STATUS_FAIL, message=f"check errored: {exc}"
        )


def check_version(version: str = __version__) -> CheckResult:
    """Report the running package version -- the first thing anyone reads
    when diagnosing a node. Resolved from installed distribution metadata
    (see ``service_directory.__version__``), never hardcoded here.

    ``"unknown"`` (the honest degradation when metadata is genuinely
    absent, e.g. an uninstalled source checkout) is reported as a warning
    rather than a failure -- doctor still runs to completion.
    """
    if version == "unknown":
        return CheckResult(
            name="Version",
            status=STATUS_WARN,
            message="could not determine installed version (package metadata not found)",
        )
    return CheckResult(name="Version", status=STATUS_OK, message=version)


def check_python_version(
    version_info: tuple[int, int, int] | tuple[int, int] = sys.version_info[:2],
) -> CheckResult:
    major_minor = (version_info[0], version_info[1])
    if major_minor >= MIN_PYTHON:
        return CheckResult(
            name="Python version",
            status=STATUS_OK,
            message=f"{major_minor[0]}.{major_minor[1]} (>= {MIN_PYTHON[0]}.{MIN_PYTHON[1]} required)",
        )
    return CheckResult(
        name="Python version",
        status=STATUS_FAIL,
        message=f"{major_minor[0]}.{major_minor[1]} is below the required {MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
    )


def check_config(
    config_path: str | None,
    loader: Callable[[str | None], RegistryConfig] = load_config,
) -> tuple[CheckResult, RegistryConfig | None]:
    """Load config via the EXISTING loader. Returns the check plus the
    loaded config (or ``None`` on failure) so later checks can reuse it."""
    try:
        config = loader(config_path)
    except ConfigError as exc:
        return CheckResult(name="Config", status=STATUS_FAIL, message=str(exc)), None
    n_services = len(config.services)
    n_hosts = len(config.host_addresses)
    return (
        CheckResult(
            name="Config",
            status=STATUS_OK,
            message=f"valid ({n_services} service(s), {n_hosts} host address(es))",
        ),
        config,
    )


BindChecker = Callable[[str, int], bool]


def _default_bind_checker(host: str, port: int) -> bool:
    import socket

    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def check_bind_port(
    host: str,
    port: int,
    bind_checker: BindChecker = _default_bind_checker,
) -> CheckResult:
    if bind_checker(host, port):
        return CheckResult(
            name="Bind port", status=STATUS_OK, message=f"{host}:{port} is available"
        )
    return CheckResult(
        name="Bind port",
        status=STATUS_WARN,
        message=f"{host}:{port} is already in use (server may already be running)",
    )


def check_identity_and_trust_store(
    state_dir: str,
    identity_loader: Callable[[str], object] | None = None,
    peers_loader: Callable[[str], list] | None = None,
) -> CheckResult:
    from .identity import load_or_create_identity
    from .trust_store import load_peers

    identity_loader = identity_loader or load_or_create_identity
    peers_loader = peers_loader or load_peers

    identity = identity_loader(state_dir)
    peers = peers_loader(state_dir)
    device_id = getattr(identity, "device_id", "unknown")
    return CheckResult(
        name="Device identity",
        status=STATUS_OK,
        message=f"device_id={device_id}, {len(peers)} trusted peer(s)",
    )


PeerReachabilityChecker = Callable[[str], bool]


def check_peer_reachability(
    peers: list,
    checker: PeerReachabilityChecker | None = None,
) -> CheckResult:
    from .health import default_checker

    checker = checker or default_checker

    if not peers:
        return CheckResult(
            name="Federation peers",
            status=STATUS_OK,
            message="no trusted peers configured",
        )

    reachable = 0
    unreachable_names = []
    for peer in peers:
        try:
            if checker(peer.base_url):
                reachable += 1
            else:
                unreachable_names.append(peer.name)
        except Exception:  # noqa: BLE001 - a single peer failure must never crash doctor
            unreachable_names.append(peer.name)

    if not unreachable_names:
        return CheckResult(
            name="Federation peers",
            status=STATUS_OK,
            message=f"{reachable}/{len(peers)} peer(s) reachable",
        )
    return CheckResult(
        name="Federation peers",
        status=STATUS_WARN,
        message=f"{reachable}/{len(peers)} peer(s) reachable (unreachable: {', '.join(unreachable_names)})",
    )


def check_install_source(
    name: str = DEFAULT_DISTRIBUTION_NAME,
    detector: Callable[[], InstallSource] | None = None,
    update_checker_fn: Callable[[InstallSource], str | None] | None = None,
) -> CheckResult:
    if detector is None:
        source = detect_install_source(name)
    else:
        source = detector()

    if update_checker_fn is None:
        latest = check_for_update(source, name)
    else:
        latest = update_checker_fn(source)

    if source.kind == "editable":
        return CheckResult(
            name="Install source",
            status=STATUS_OK,
            message=f"editable install, version {source.version} (upgrade unnecessary: edit the checkout directly)",
        )
    if source.kind == "unknown":
        return CheckResult(
            name="Install source",
            status=STATUS_WARN,
            message=f"could not determine install source (version {source.version})",
        )
    if latest:
        return CheckResult(
            name="Install source",
            status=STATUS_WARN,
            message=f"{source.kind} install, version {source.version} (update available: {latest})",
        )
    return CheckResult(
        name="Install source",
        status=STATUS_OK,
        message=f"{source.kind} install, version {source.version} (up to date)",
    )


def check_service_status(
    manager_factory: Callable[[], ServiceManager] | None = None,
) -> CheckResult:
    try:
        manager = manager_factory() if manager_factory else get_service_manager()
    except UnsupportedPlatformError as exc:
        return CheckResult(name="Service status", status=STATUS_WARN, message=str(exc))

    result: ServiceResult = manager.status()
    status = STATUS_OK if result.ok else STATUS_WARN
    return CheckResult(name="Service status", status=status, message=result.message)


@dataclass
class DoctorDependencies:
    """All injectable seams for :func:`run_doctor`, bundled so tests can
    override only what they care about and defaults cover the rest."""

    config_path: str | None = None
    host: str = "0.0.0.0"
    port: int = 80
    loader: Callable[[str | None], RegistryConfig] = load_config
    bind_checker: BindChecker = _default_bind_checker
    identity_loader: Callable[[str], object] | None = None
    peers_loader: Callable[[str], list] | None = None
    peer_reachability_checker: PeerReachabilityChecker | None = None
    install_source_detector: Callable[[], InstallSource] | None = None
    update_checker_fn: Callable[[InstallSource], str | None] | None = None
    service_manager_factory: Callable[[], ServiceManager] | None = None
    python_version_info: tuple[int, int, int] | tuple[int, int] = sys.version_info[:2]
    version: str = __version__


def run_doctor(deps: DoctorDependencies | None = None) -> list[CheckResult]:
    """Run every check and return the full checklist. Never raises."""
    deps = deps or DoctorDependencies()

    results: list[CheckResult] = []

    results.append(_run_check("Version", lambda: check_version(deps.version)))

    results.append(
        _run_check(
            "Python version", lambda: check_python_version(deps.python_version_info)
        )
    )

    config_result, config = _run_check_with_value(
        "Config", lambda: check_config(deps.config_path, deps.loader)
    )
    results.append(config_result)

    results.append(
        _run_check(
            "Bind port",
            lambda: check_bind_port(deps.host, deps.port, deps.bind_checker),
        )
    )

    peers: list = []
    if config is not None:
        state_dir = resolve_state_dir(config)

        def _identity_check() -> CheckResult:
            return check_identity_and_trust_store(
                state_dir, deps.identity_loader, deps.peers_loader
            )

        results.append(_run_check("Device identity", _identity_check))

        from .trust_store import load_peers

        peers_loader = deps.peers_loader or load_peers
        try:
            peers = peers_loader(state_dir)
        except Exception:  # noqa: BLE001 - defensive
            peers = []
    else:
        results.append(
            CheckResult(
                name="Device identity",
                status=STATUS_WARN,
                message="skipped (config invalid)",
            )
        )

    results.append(
        _run_check(
            "Federation peers",
            lambda: check_peer_reachability(peers, deps.peer_reachability_checker),
        )
    )

    results.append(
        _run_check(
            "Install source",
            lambda: check_install_source(
                detector=deps.install_source_detector,
                update_checker_fn=deps.update_checker_fn,
            ),
        )
    )

    results.append(
        _run_check(
            "Service status",
            lambda: check_service_status(deps.service_manager_factory),
        )
    )

    return results


def _run_check_with_value(name, fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a single check must never crash doctor
        return CheckResult(
            name=name, status=STATUS_FAIL, message=f"check errored: {exc}"
        ), None


def format_checklist(results: list[CheckResult], color: bool = True) -> str:
    """Render the checklist as text: green check / red x / yellow ! per line."""
    lines = []
    for r in results:
        symbol = _SYMBOLS.get(r.status, "?")
        if color:
            code = _COLORS.get(r.status, "0")
            symbol_rendered = f"\033[{code}m{symbol}{_RESET}"
        else:
            symbol_rendered = symbol
        lines.append(f"{symbol_rendered} {r.name}: {r.message}")
    return "\n".join(lines)


def run_and_format(
    deps: DoctorDependencies | None = None, color: bool = True
) -> tuple[str, bool]:
    """Convenience for the CLI: run the checklist, format it, and report
    whether everything passed (no ``fail`` status) for the exit code."""
    results = run_doctor(deps)
    text = format_checklist(results, color=color)
    all_ok = all(r.status != STATUS_FAIL for r in results)
    return text, all_ok


__all__ = [
    "STATUS_FAIL",
    "STATUS_OK",
    "STATUS_WARN",
    "CheckResult",
    "DoctorDependencies",
    "check_bind_port",
    "check_config",
    "check_identity_and_trust_store",
    "check_install_source",
    "check_peer_reachability",
    "check_python_version",
    "check_service_status",
    "check_version",
    "format_checklist",
    "run_and_format",
    "run_doctor",
]
