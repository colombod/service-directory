"""Best-effort connectivity checks behind an injectable seam.

The default implementation makes a real (short-timeout) TCP connection
attempt. Tests inject a stub checker so the suite never touches the network.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from urllib.parse import urlparse

from .config import is_safe_health_target

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


# A HttpChecker takes a URL and returns True if an HTTP GET against it comes
# back 2xx, False otherwise. Kept as its OWN injectable seam (distinct from
# the TCP-only ``Checker``) so tests can stub HTTP health-endpoint checks
# without ever touching the network, exactly like ``Checker``.
HttpChecker = Callable[[str], bool]


def default_http_checker(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> bool:
    """Real implementation: GET ``url``, treat any 2xx response as "up".

    Never raises -- any failure (DNS, refused, timeout, non-2xx, malformed
    URL) is treated as "down".
    """
    try:
        import httpx2 as httpx

        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
        return 200 <= resp.status_code < 300
    except Exception:  # noqa: BLE001 - never let a bad URL/host crash the health check
        return False


def check_service_entries(
    entries: list[dict],
    checker: Checker = default_checker,
    http_checker: HttpChecker = default_http_checker,
    allow_private_health_targets: bool = False,
) -> dict[str, str]:
    """Return {service_name: "up"|"down"} for dict-shaped service entries
    (the JSON shape produced by ``app._local_services_json`` /
    ``app._dynamic_services_json``), applying the health PRIORITY order:

    1. Heartbeat-fresh: if the entry carries a ``ttl``, it is only ever
       seen here if it survived pruning on read (see
       ``registry.load_registry``) -- i.e. it already has a fresh
       heartbeat -- so it is reported "up" directly, with no further
       HTTP/TCP probe.
    2. HTTP GET ``health_url`` (if set): any 2xx response is "up".
    3. TCP connect fallback (the pre-existing ``checker`` behavior) against
       the entry's first resolved link, exactly like static entries.

    Both ``checker`` and ``http_checker`` are injectable seams so tests
    never perform real network I/O.

    SSRF hardening: for DYNAMIC entries (``source == "dynamic"``), both
    the ``health_url`` and the TCP-fallback link URL are caller-supplied
    (any write-access caller can set them), so each is validated with
    ``config.is_safe_health_target`` before ever being handed to the
    checker seam -- an unsafe target (bad scheme, or loopback/link-local/
    private/reserved IP-literal host) is treated as "down" without ever
    invoking ``checker``/``http_checker``. Static entries are always
    admin-controlled config and are never subject to this check. Set
    ``allow_private_health_targets=True`` (from
    ``federation.allow_private_health_targets``) to opt out for
    deployments that intentionally target private/LAN addresses.
    """
    results: dict[str, str] = {}
    for svc in entries:
        name = svc["name"]
        is_dynamic = svc.get("source") == "dynamic"
        if svc.get("ttl") is not None:
            results[name] = "up"
            continue

        health_url = svc.get("health_url")
        if health_url:
            if is_dynamic and not is_safe_health_target(
                health_url, allow_private=allow_private_health_targets
            ):
                results[name] = "down"
                continue
            try:
                reachable = http_checker(health_url)
            except Exception:  # noqa: BLE001 - a single bad checker must never crash
                reachable = False
            results[name] = "up" if reachable else "down"
            continue

        links = svc.get("links") or []
        if not links:
            results[name] = "down"
            continue
        link = links[0]
        url = link["url"]
        # A port-based dynamic link (built against a configured, trusted
        # host_address -- see app._dynamic_service_json) carries a
        # non-empty "host"; only a raw caller-supplied `url` field
        # (host == "") is genuinely attacker-controlled and needs the
        # SSRF target check. Port-based links reuse the SAME trusted
        # host_addresses static services already resolve against, so
        # they are not a new attack surface and must keep working
        # exactly as before (including against private/LAN addresses).
        if (
            is_dynamic
            and not link.get("host")
            and not is_safe_health_target(
                url, allow_private=allow_private_health_targets
            )
        ):
            results[name] = "down"
            continue
        try:
            reachable = checker(url)
        except Exception:  # noqa: BLE001 - a single bad checker must never crash
            reachable = False
        results[name] = "up" if reachable else "down"
    return results
