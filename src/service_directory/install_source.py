"""Install-source detection via PEP 610 ``direct_url.json``.

When a package is installed with pip/uv, the installer records *how* it was
installed in ``direct_url.json`` inside the distribution's metadata
directory (PEP 610). We use that to tell ``doctor``/``upgrade`` apart:

- an **editable** install (``pip install -e .`` / ``uv pip install -e .``) --
  there is no "reinstall" to do; the running code IS the checkout.
- a **git**/VCS install -- installed straight from a repository URL.
- a **local** (non-editable) install -- from a local path/sdist/wheel file.
- **pypi** -- no ``direct_url.json`` at all means a normal index install.

Every lookup is defensive: a missing distribution, unreadable metadata, or
malformed JSON never raises -- it degrades to ``kind="unknown"`` so
``doctor`` can report it as a warning rather than crashing.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast

DEFAULT_DISTRIBUTION_NAME = "service-directory"


class DistributionLike(Protocol):
    """The subset of :class:`importlib.metadata.Distribution` we use.

    Kept as a narrow protocol so tests can inject a trivial fake without
    touching real package metadata.
    """

    version: str

    def read_text(self, filename: str) -> str | None: ...


DistributionFactory = Callable[[str], DistributionLike]


def _default_distribution_factory(name: str) -> DistributionLike:
    from importlib import metadata

    return cast(DistributionLike, metadata.distribution(name))


@dataclass(frozen=True)
class InstallSource:
    """Where the running package came from, per PEP 610 (best-effort)."""

    kind: str  # "editable" | "git" | "<vcs>" | "local" | "pypi" | "unknown"
    version: str
    url: str | None = None
    commit_id: str | None = None
    editable: bool = False


def detect_install_source(
    name: str = DEFAULT_DISTRIBUTION_NAME,
    distribution_factory: DistributionFactory = _default_distribution_factory,
) -> InstallSource:
    """Detect how ``name`` was installed. Never raises.

    ``distribution_factory`` is the injectable seam: production resolves a
    real :class:`importlib.metadata.Distribution`; tests inject a fake
    object exposing ``version``/``read_text`` so no real package metadata
    is touched.
    """
    try:
        dist = distribution_factory(name)
    except Exception:  # noqa: BLE001 - package lookup must never crash doctor
        return InstallSource(kind="unknown", version="unknown")

    version = getattr(dist, "version", None) or "unknown"

    try:
        raw = dist.read_text("direct_url.json")
    except Exception:  # noqa: BLE001 - an abnormal read failure (e.g. permission
        # denied) is NOT the same as "file legitimately absent" (a normal
        # PyPI install) -- report it as unknown rather than guessing pypi.
        return InstallSource(kind="unknown", version=version)

    if not raw:
        # read_text() returned None/empty with no exception: no
        # direct_url.json at all == installed from an index (PyPI).
        return InstallSource(kind="pypi", version=version)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return InstallSource(kind="unknown", version=version)

    if not isinstance(data, dict):
        return InstallSource(kind="unknown", version=version)

    url = data.get("url")
    if url is not None and not isinstance(url, str):
        url = None

    dir_info = data.get("dir_info")
    if not isinstance(dir_info, dict):
        dir_info = {}

    vcs_info = data.get("vcs_info")
    if not isinstance(vcs_info, dict):
        vcs_info = {}

    if dir_info.get("editable") is True:
        return InstallSource(kind="editable", version=version, url=url, editable=True)

    if vcs_info:
        vcs = vcs_info.get("vcs")
        kind = vcs if isinstance(vcs, str) and vcs else "vcs"
        commit_id = vcs_info.get("commit_id")
        commit_id = commit_id if isinstance(commit_id, str) else None
        return InstallSource(kind=kind, version=version, url=url, commit_id=commit_id)

    if url:
        return InstallSource(kind="local", version=version, url=url)

    return InstallSource(kind="unknown", version=version)


# --- best-effort "is there a newer version" check (PyPI JSON API) ---------

UpdateChecker = Callable[[str, float], "str | None"]


def default_update_checker(
    name: str, timeout: float = 2.0, base_url: str = "https://pypi.org/pypi"
) -> str | None:
    """Best-effort lookup of the latest version published on PyPI.

    ``base_url`` defaults to the real PyPI JSON API but is overridable so
    the hermetic test suite can point this at a local HTTP fixture server
    instead of the public internet while still exercising the REAL
    ``urllib`` request/JSON-parsing code path.

    Returns ``None`` on ANY failure (network down, timeout, bad JSON,
    unknown package) -- this must never raise or block ``doctor``.
    """
    import urllib.request

    try:
        url = f"{base_url.rstrip('/')}/{name}/json"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read())
        latest = data.get("info", {}).get("version")
        return latest if isinstance(latest, str) else None
    except Exception:  # noqa: BLE001 - update check is best-effort only
        return None


def check_for_update(
    source: InstallSource,
    name: str = DEFAULT_DISTRIBUTION_NAME,
    checker: UpdateChecker = default_update_checker,
    timeout: float = 2.0,
) -> str | None:
    """Return the newer version string if one is available, else ``None``.

    Only meaningful for ``kind == "pypi"`` installs -- git/editable/local
    installs are not versioned against PyPI, so this always returns
    ``None`` for them without invoking ``checker`` (no needless network
    calls).
    """
    if source.kind != "pypi":
        return None
    try:
        latest = checker(name, timeout)
    except Exception:  # noqa: BLE001 - defensive: checker itself must never crash doctor
        return None
    if latest and latest != source.version:
        return latest
    return None


__all__ = [
    "DEFAULT_DISTRIBUTION_NAME",
    "DistributionLike",
    "InstallSource",
    "check_for_update",
    "default_update_checker",
    "detect_install_source",
]
