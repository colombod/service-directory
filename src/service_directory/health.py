"""Best-effort connectivity checks behind an injectable seam.

The default implementation makes a real (short-timeout) TCP connection
attempt. Tests inject a stub checker so the suite never touches the network.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from urllib.parse import urlparse

DEFAULT_TIMEOUT_SECONDS = 1.0

# A checker takes a URL and returns True if reachable, False otherwise.
Checker = Callable[[str], bool]


def default_checker(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> bool:
    """Best-effort TCP connect check to the host:port encoded in ``url``.

    Never raises -- any failure (DNS, refused, timeout, malformed URL) is
    treated as "down". Bounded to ``timeout`` seconds (<=1s per the spec).
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not host:
            return False
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
    except Exception:  # noqa: BLE001 - never let a bad URL/host crash the health check
        return False


def check_services(
    resolved_services: list,
    checker: Checker = default_checker,
) -> dict[str, str]:
    """Return {service_name: "up"|"down"} using the first link per service.

    ``checker`` is the injectable seam: production uses ``default_checker``,
    tests inject a stub that never touches the network. A service with no
    configured links (impossible per validated config, but defensive) is
    reported "down". Any exception from the checker itself is swallowed and
    treated as "down" so a single bad check can never crash the endpoint.
    """
    results: dict[str, str] = {}
    for svc in resolved_services:
        if not svc.links:
            results[svc.name] = "down"
            continue
        url = svc.links[0].url
        try:
            reachable = checker(url)
        except Exception:  # noqa: BLE001 - a single bad checker must never crash the endpoint
            reachable = False
        results[svc.name] = "up" if reachable else "down"
    return results
