"""Source-aware maintenance and independent, durable self-update jobs.

Remote updates are deliberately limited to uv tool installs managed by a
systemd user unit. A transient systemd unit runs the worker outside the web
service's cgroup, so stopping the web service cannot kill its own updater.
No HTTP request can supply an install URL, ref, executable, or command.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from packaging.version import InvalidVersion, Version

from . import __version__
from .install_source import InstallSource, detect_install_source, default_update_checker
from .service_manager import SystemdUserServiceManager
from .upgrade import run_upgrade

ACTIVE = {"queued", "running"}


class MaintenanceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".maintenance-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def default_capability(source: InstallSource) -> str | None:
    if source.kind not in {"pypi", "git"}:
        return "This install is not an updatable uv tool; use its checkout or installer."
    if source.kind == "git" and not safe_git_source(source):
        return "Git install metadata is missing a supported repository URL."
    if platform.system() != "Linux":
        return "Remote self-update currently requires a Linux systemd user service; use the CLI here."
    if any(not shutil.which(tool) for tool in ("uv", "systemd-run", "systemctl")):
        return "uv, systemd-run, and systemctl must be available on the service PATH."
    try:
        version = subprocess.run(["systemd-run", "--version"], capture_output=True,
                                 text=True, timeout=2, check=False)
        match = re.match(r"systemd\s+(\d+)", version.stdout)
        if version.returncode or not match or int(match.group(1)) < 254:
            return "Remote self-update requires systemd 254 or later."
    except (OSError, subprocess.SubprocessError):
        return "Could not verify the systemd-run version."
    # A pip/venv install must never accidentally upgrade an unrelated uv tool.
    if not (Path(sys.prefix) / "uv-receipt.toml").is_file():
        return "The running service is not installed in a uv tool environment."
    if not Path(SystemdUserServiceManager().unit_path).is_file():
        return "Install the service-directory systemd user service first."
    return None


def safe_git_source(source: InstallSource) -> bool:
    if not source.url or source.url.startswith("-"):
        return False
    parsed = urlparse(source.url)
    return parsed.scheme in {"https", "ssh", "git"} and bool(parsed.hostname)


def git_revision(source: InstallSource, runner=subprocess.run) -> str | None:
    """Bounded lookup of the configured revision, not an arbitrary HTTP URL."""
    if not safe_git_source(source):
        return None
    revision = source.requested_revision or source.commit_id or "HEAD"
    if re.fullmatch(r"[a-fA-F0-9]{40}", revision):
        return revision.lower()  # an intentional immutable pin
    if revision.startswith("-") or any(c.isspace() for c in revision):
        return None
    refs = ["HEAD"] if revision == "HEAD" else [
        f"refs/heads/{revision}", f"refs/tags/{revision}", f"refs/tags/{revision}^{{}}"
    ]
    try:
        result = runner(
            ["git", "ls-remote", "--", source.url, *refs],
            capture_output=True, text=True, timeout=5, check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=5 -o ConnectionAttempts=1"},
        )
        if result.returncode:
            return None
        candidates = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2 and re.fullmatch(r"[a-fA-F0-9]{40}", parts[0]):
                candidates[parts[1]] = parts[0].lower()
        # Dereference annotated tags; prefer the branch if both exist.
        for ref in ([refs[0]] if revision == "HEAD" else [refs[0], refs[2], refs[1]]):
            if ref in candidates:
                return candidates[ref]
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def check_source(source: InstallSource, pypi_checker=default_update_checker, git_checker=git_revision) -> dict:
    result = {"update_available": None, "latest_revision": None, "latest_version": None}
    if source.kind == "git":
        revision = git_checker(source)
        result["latest_revision"] = revision
        if revision and source.commit_id:
            result["update_available"] = revision.lower() != source.commit_id.lower()
    elif source.kind == "pypi":
        latest = pypi_checker("service-directory", 2.0)
        result["latest_version"] = latest
        if latest:
            try:
                result["update_available"] = Version(latest) > Version(source.version)
            except InvalidVersion:
                pass
    return result


def launch_worker(state_dir: str, job_id: str) -> None:
    """Run outside the directory, with recovery owned by the systemd manager.

    In-process exception handling cannot recover after SIGKILL or RuntimeMaxSec.
    ExecStopPost runs after systemd has terminated the worker's entire cgroup,
    including a stuck installer, and attempts to start the original directory
    unit even if the Python environment has been replaced or broken. The fixed
    systemctl command uses systemd's standard executable search path, not the
    uv environment being upgraded. This is a recovery attempt, not a rollback.
    """
    command = ["systemd-run", "--user", "--collect", "--quiet",
               f"--unit=service-directory-update-{job_id}",
               "--property=Type=exec", "--property=RuntimeMaxSec=900",
               "--property=KillMode=control-group", "--property=TimeoutStopSec=20",
               "--property=ExecStopPost=systemctl --user start service-directory.service",
               "--expand-environment=no"]
    # User-manager units do not inherit the web service's environment. Preserve
    # its install/bind configuration and tool/cache environment deliberately.
    for key in os.environ:
        if key in {"PATH", "HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"} or key.startswith(("SERVICE_REGISTRY_", "UV_")):
            # Omit the value: systemd-run copies it from its environment,
            # keeping private index credentials out of process argv.
            command.append(f"--setenv={key}")
    command.extend([sys.executable, "-m", "service_directory.maintenance", "worker",
                    "--state-dir", state_dir, "--job-id", job_id])
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise RuntimeError("Could not start the independent updater; check the systemd user manager.")


class Maintenance:
    def __init__(self, state_dir: str, *, source_detector=detect_install_source,
                 capability=default_capability, checker=check_source,
                 launcher=launch_worker, time_fn=time.time):
        self.directory = Path(state_dir).resolve() / "maintenance"
        self.source_detector = source_detector
        self.capability = capability
        self.checker = checker
        self.launcher = launcher
        self.time_fn = time_fn

    @contextmanager
    def locked(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.directory / "lock", os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def job(self, job_id: str) -> dict | None:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            return None
        return read_json(self.directory / f"{job_id}.json")

    def latest_job(self) -> dict | None:
        pointer = read_json(self.directory / "latest-job.json")
        job = self.job(pointer.get("id", "")) if pointer else None
        if job and job.get("status") in ACTIVE and self.time_fn() - job.get("started_at", 0) > 960:
            job.update(status="failed", message="Updater exceeded its deadline or was interrupted; inspect this node before retrying.", finished_at=self.time_fn())
            atomic_json(self.directory / f"{job['id']}.json", job)
        return job

    def status(self) -> dict:
        source = self.source_detector()
        reason = self.capability(source)
        checked = read_json(self.directory / "check.json") or {}
        # Checks from the previous installed revision are no longer current.
        if checked.get("current_revision") != source.commit_id or checked.get("version") != source.version:
            checked = {}
        return {
            "version": __version__, "install_kind": source.kind,
            "update_supported": reason is None, "unsupported_reason": reason,
            "current_revision": source.commit_id,
            "update_available": checked.get("update_available"),
            "latest_revision": checked.get("latest_revision"),
            "latest_version": checked.get("latest_version"),
            "checked_at": checked.get("checked_at"), "job": self.latest_job(),
        }

    def check(self) -> dict:
        source = self.source_detector()
        checked = self.checker(source)
        atomic_json(self.directory / "check.json", {
            **checked, "version": source.version, "current_revision": source.commit_id,
            "checked_at": self.time_fn(),
        })
        return self.status()

    def start(self) -> dict:
        with self.locked():
            latest = self.latest_job()
            if latest and latest.get("status") in ACTIVE:
                raise MaintenanceError(409, "An update job is already active.")
            source = self.source_detector()
            reason = self.capability(source)
            if reason:
                raise MaintenanceError(422, reason)
            job_id = uuid.uuid4().hex
            job = {"id": job_id, "status": "queued", "message": "Independent updater queued.",
                   "steps": [], "started_at": self.time_fn(), "finished_at": None}
            atomic_json(self.directory / f"{job_id}.json", job)
            atomic_json(self.directory / "latest-job.json", {"id": job_id})
            try:
                self.launcher(str(self.directory.parent), job_id)
            except Exception:
                job.update(status="failed", message="Could not start the independent updater; no service changes were made.", finished_at=self.time_fn())
                atomic_json(self.directory / f"{job_id}.json", job)
                raise MaintenanceError(503, job["message"])
            return job


def verify_restarted_service() -> bool:
    """Require a running unit AND a fresh HTTP response, not a launch result."""
    manager = SystemdUserServiceManager()
    port = int(os.environ.get("SERVICE_REGISTRY_PORT", "80"))
    for _ in range(15):
        try:
            if manager.status().ok:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/instance-info", timeout=1) as response:
                    info = json.loads(response.read())
                if isinstance(info.get("version"), str):
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def run_worker(state_dir: str, job_id: str, upgrader=run_upgrade, verifier=verify_restarted_service) -> None:
    maintenance = Maintenance(state_dir)
    job = maintenance.job(job_id)
    if not job or job.get("status") != "queued":
        return
    path = maintenance.directory / f"{job_id}.json"
    job.update(status="running", message="Updating; the directory may disconnect while its service restarts.")
    atomic_json(path, job)
    try:
        result = upgrader(recover_on_failure=True, doctor_verifier=verifier)
        # Do not return installer stdout/stderr: source URLs can contain secrets.
        succeeded = result.ok and not result.skipped
        job.update(status="succeeded" if succeeded else "failed", steps=result.steps,
                   message="Update completed and the restarted directory responded." if succeeded else
                   "Update did not complete. Check service-directory logs/doctor on this node.")
    except Exception:
        job.update(status="failed", message="Updater failed. Check the directory service on this node.")
    job["finished_at"] = time.time()
    atomic_json(path, job)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["worker"])
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    run_worker(args.state_dir, args.job_id)


if __name__ == "__main__":
    main()
