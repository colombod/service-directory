"""Service (un)installation as a systemd --user unit / launchd agent.

Dispatch API: :func:`get_service_manager` picks the right implementation for
the current platform (systemd user unit on Linux, a launchd agent plist on
macOS) so ``cli.py``/``upgrade.py`` never need to branch on platform
themselves.

``install`` renders the unit/plist with the CURRENT ``PATH`` environment
variable baked in (so the service can find any tools it shells out to, the
same way the invoking shell could) and points ``ExecStart``/``ProgramArguments``
at the ``service-directory`` console script's ``serve`` subcommand.

Every external effect (writing unit files, invoking ``systemctl``/
``launchctl``) goes through injectable seams (``runner`` for subprocess,
``unit_dir``/``agent_dir`` for the filesystem location) so the hermetic test
suite can point them at a ``tmp_path`` and a stub runner instead of ever
touching the real system.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

UNIT_NAME = "service-directory.service"
LAUNCHD_LABEL = "com.service-directory.serve"

CommandRunner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def default_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Real implementation: run ``cmd``, capturing output, never raising on
    a non-zero exit (callers inspect ``returncode``)."""
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


@dataclass(frozen=True)
class ServiceResult:
    """Outcome of a service-manager operation: always structured, never an
    unhandled exception -- callers (CLI/doctor) branch on ``ok``."""

    ok: bool
    message: str
    output: str = ""


def resolve_exec_path(console_script: str = "service-directory") -> str:
    """Full path to the ``service-directory`` console script on PATH.

    Falls back to ``sys.argv[0]`` (how we were invoked) if ``shutil.which``
    can't find it (e.g. an editable/dev environment with an unusual PATH),
    and finally to the bare name so the unit is still renderable (it just
    may not resolve at runtime -- ``doctor`` surfaces that separately).
    """
    found = shutil.which(console_script)
    if found:
        return found
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0 and os.path.basename(argv0).startswith(console_script.split("-")[0]):
        return os.path.abspath(argv0)
    return console_script


def current_path_env() -> str:
    """The current process's PATH, baked verbatim into the generated unit."""
    return os.environ.get("PATH", "")


def render_systemd_unit(
    exec_path: str,
    path_value: str,
    description: str = "service-directory dashboard",
) -> str:
    """Render a systemd ``--user`` unit file as a string (no I/O).

    ``ExecStart`` invokes the console script's ``serve`` subcommand;
    ``Environment=PATH=...`` bakes in the caller's current PATH.
    """
    return (
        "[Unit]\n"
        f"Description={description}\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f'Environment="PATH={path_value}"\n'
        f"ExecStart={exec_path} serve\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def render_launchd_plist(
    exec_path: str,
    path_value: str,
    label: str = LAUNCHD_LABEL,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
) -> str:
    """Render a launchd agent plist as a string (no I/O).

    ``ProgramArguments`` invokes the console script's ``serve`` subcommand;
    the ``PATH`` environment variable is baked into ``EnvironmentVariables``.
    """
    stdout_line = (
        f"    <key>StandardOutPath</key>\n    <string>{stdout_path}</string>\n"
        if stdout_path
        else ""
    )
    stderr_line = (
        f"    <key>StandardErrorPath</key>\n    <string>{stderr_path}</string>\n"
        if stderr_path
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>{label}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"        <string>{exec_path}</string>\n"
        "        <string>serve</string>\n"
        "    </array>\n"
        "    <key>EnvironmentVariables</key>\n"
        "    <dict>\n"
        "        <key>PATH</key>\n"
        f"        <string>{path_value}</string>\n"
        "    </dict>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "    <key>KeepAlive</key>\n"
        "    <true/>\n"
        f"{stdout_line}"
        f"{stderr_line}"
        "</dict>\n"
        "</plist>\n"
    )


class SystemdUserServiceManager:
    """systemd ``--user`` unit management (Linux)."""

    platform_name = "linux"

    def __init__(
        self,
        runner: CommandRunner = default_runner,
        unit_dir: str | None = None,
        unit_name: str = UNIT_NAME,
    ) -> None:
        self.runner = runner
        self.unit_dir = unit_dir or os.path.join(
            os.path.expanduser("~"), ".config", "systemd", "user"
        )
        self.unit_name = unit_name

    @property
    def unit_path(self) -> str:
        return os.path.join(self.unit_dir, self.unit_name)

    def install(
        self, exec_path: str | None = None, path_value: str | None = None
    ) -> ServiceResult:
        exec_path = exec_path or resolve_exec_path()
        path_value = path_value if path_value is not None else current_path_env()
        content = render_systemd_unit(exec_path, path_value)
        os.makedirs(self.unit_dir, exist_ok=True)
        with open(self.unit_path, "w", encoding="utf-8") as f:
            f.write(content)
        reload_result = self.runner(["systemctl", "--user", "daemon-reload"])
        enable_result = self.runner(
            ["systemctl", "--user", "enable", "--now", self.unit_name]
        )
        ok = reload_result.returncode == 0 and enable_result.returncode == 0
        return ServiceResult(
            ok=ok,
            message="installed and started"
            if ok
            else "installed unit but enable failed",
            output=(reload_result.stdout or "") + (enable_result.stdout or ""),
        )

    def uninstall(self) -> ServiceResult:
        stop_result = self.runner(
            ["systemctl", "--user", "disable", "--now", self.unit_name]
        )
        removed = False
        if os.path.exists(self.unit_path):
            os.remove(self.unit_path)
            removed = True
        self.runner(["systemctl", "--user", "daemon-reload"])
        return ServiceResult(
            ok=True,
            message="uninstalled" if removed else "unit file was not present",
            output=stop_result.stdout or "",
        )

    def start(self) -> ServiceResult:
        result = self.runner(["systemctl", "--user", "start", self.unit_name])
        return ServiceResult(
            ok=result.returncode == 0,
            message="started" if result.returncode == 0 else "start failed",
            output=result.stdout or result.stderr or "",
        )

    def stop(self) -> ServiceResult:
        result = self.runner(["systemctl", "--user", "stop", self.unit_name])
        return ServiceResult(
            ok=result.returncode == 0,
            message="stopped" if result.returncode == 0 else "stop failed",
            output=result.stdout or result.stderr or "",
        )

    def status(self) -> ServiceResult:
        result = self.runner(["systemctl", "--user", "is-active", self.unit_name])
        state = (result.stdout or "").strip() or "unknown"
        return ServiceResult(
            ok=state == "active", message=state, output=result.stdout or ""
        )

    def logs(self, lines: int = 50) -> ServiceResult:
        result = self.runner(
            [
                "journalctl",
                "--user",
                "-u",
                self.unit_name,
                "-n",
                str(lines),
                "--no-pager",
            ]
        )
        return ServiceResult(
            ok=result.returncode == 0,
            message="ok" if result.returncode == 0 else "journalctl failed",
            output=result.stdout or "",
        )


class LaunchdServiceManager:
    """launchd user-agent management (macOS)."""

    platform_name = "darwin"

    def __init__(
        self,
        runner: CommandRunner = default_runner,
        agent_dir: str | None = None,
        label: str = LAUNCHD_LABEL,
        log_dir: str | None = None,
    ) -> None:
        self.runner = runner
        self.agent_dir = agent_dir or os.path.join(
            os.path.expanduser("~"), "Library", "LaunchAgents"
        )
        self.label = label
        self.log_dir = log_dir or os.path.join(
            os.path.expanduser("~"), ".local", "state", "service-directory", "logs"
        )

    @property
    def plist_path(self) -> str:
        return os.path.join(self.agent_dir, f"{self.label}.plist")

    @property
    def stdout_path(self) -> str:
        return os.path.join(self.log_dir, "service-directory.out.log")

    @property
    def stderr_path(self) -> str:
        return os.path.join(self.log_dir, "service-directory.err.log")

    def install(
        self, exec_path: str | None = None, path_value: str | None = None
    ) -> ServiceResult:
        exec_path = exec_path or resolve_exec_path()
        path_value = path_value if path_value is not None else current_path_env()
        content = render_launchd_plist(
            exec_path,
            path_value,
            label=self.label,
            stdout_path=self.stdout_path,
            stderr_path=self.stderr_path,
        )
        os.makedirs(self.agent_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        with open(self.plist_path, "w", encoding="utf-8") as f:
            f.write(content)
        load_result = self.runner(["launchctl", "load", "-w", self.plist_path])
        ok = load_result.returncode == 0
        return ServiceResult(
            ok=ok,
            message="installed and loaded" if ok else "installed plist but load failed",
            output=load_result.stdout or load_result.stderr or "",
        )

    def uninstall(self) -> ServiceResult:
        unload_result = self.runner(["launchctl", "unload", self.plist_path])
        removed = False
        if os.path.exists(self.plist_path):
            os.remove(self.plist_path)
            removed = True
        return ServiceResult(
            ok=True,
            message="uninstalled" if removed else "plist was not present",
            output=unload_result.stdout or "",
        )

    def start(self) -> ServiceResult:
        result = self.runner(["launchctl", "start", self.label])
        return ServiceResult(
            ok=result.returncode == 0,
            message="started" if result.returncode == 0 else "start failed",
            output=result.stdout or result.stderr or "",
        )

    def stop(self) -> ServiceResult:
        result = self.runner(["launchctl", "stop", self.label])
        return ServiceResult(
            ok=result.returncode == 0,
            message="stopped" if result.returncode == 0 else "stop failed",
            output=result.stdout or result.stderr or "",
        )

    def status(self) -> ServiceResult:
        result = self.runner(["launchctl", "list", self.label])
        ok = result.returncode == 0
        return ServiceResult(
            ok=ok, message="loaded" if ok else "not loaded", output=result.stdout or ""
        )

    def logs(self, lines: int = 50) -> ServiceResult:
        result = self.runner(["tail", "-n", str(lines), self.stdout_path])
        return ServiceResult(
            ok=result.returncode == 0,
            message="ok" if result.returncode == 0 else "log read failed",
            output=result.stdout or "",
        )


ServiceManager = SystemdUserServiceManager | LaunchdServiceManager


class UnsupportedPlatformError(RuntimeError):
    """Raised when the current platform has no service manager implementation."""


def get_service_manager(
    system: str | None = None,
    runner: CommandRunner = default_runner,
) -> ServiceManager:
    """Dispatch to the right :class:`ServiceManager` for the current platform.

    ``system`` defaults to :func:`platform.system` (``"Linux"``/``"Darwin"``/
    ``"Windows"``) but is injectable so tests can exercise both branches on
    any host.
    """
    system = system if system is not None else platform.system()
    normalized = system.lower()
    if normalized == "linux":
        return SystemdUserServiceManager(runner=runner)
    if normalized == "darwin":
        return LaunchdServiceManager(runner=runner)
    raise UnsupportedPlatformError(
        f"service management is not supported on platform {system!r} "
        f"(supported: Linux via systemd --user, macOS via launchd)"
    )


__all__ = [
    "LAUNCHD_LABEL",
    "UNIT_NAME",
    "LaunchdServiceManager",
    "ServiceManager",
    "ServiceResult",
    "SystemdUserServiceManager",
    "UnsupportedPlatformError",
    "current_path_env",
    "default_runner",
    "get_service_manager",
    "render_launchd_plist",
    "render_systemd_unit",
    "resolve_exec_path",
]
