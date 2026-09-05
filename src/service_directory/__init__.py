"""service-directory: a tiny config-driven service registry dashboard."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

#: Distribution name used to resolve the running version -- kept in sync
#: with ``pyproject.toml``'s ``[project].name``. This is NOT a version
#: literal; it is the lookup key passed to ``importlib.metadata.version``.
DISTRIBUTION_NAME = "service-directory"

#: The single source of truth for the version is ``pyproject.toml``. At
#: runtime we resolve it from the INSTALLED distribution's metadata (never
#: by parsing pyproject.toml, which would break once installed from a
#: wheel/uv-tool install with no source tree present). If the distribution
#: metadata is genuinely absent (e.g. running from a source checkout that
#: was never installed), we degrade honestly to "unknown" rather than
#: fabricating a version number.
try:
    __version__ = _pkg_version(DISTRIBUTION_NAME)
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = ["DISTRIBUTION_NAME", "__version__"]
