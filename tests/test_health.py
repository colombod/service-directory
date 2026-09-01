from __future__ import annotations

import socket
import threading

from service_directory.health import check_services, default_checker
from service_directory.urls import resolve_all


class _FakeResolvedService:
    def __init__(self, name, links):
        self.name = name
        self.links = links


class _FakeLink:
    def __init__(self, url):
        self.url = url


def test_check_services_all_down_stub(sample_config):
    """With the connectivity check stubbed to fail for all, /api/health
    style aggregation must report every service down and must not raise."""
    resolved = resolve_all(sample_config)

    def always_down(url: str) -> bool:
        return False

    results = check_services(resolved, checker=always_down)

    assert set(results.keys()) == {svc.name for svc in sample_config.services}
    assert all(status == "down" for status in results.values())


def test_check_services_mixed_stub(sample_config):
    resolved = resolve_all(sample_config)

    def up_for_resolve_only(url: str) -> bool:
        return ":8080" in url

    results = check_services(resolved, checker=up_for_resolve_only)
    assert results["Resolve"] == "up"
    assert results["muxplex"] == "down"


def test_check_services_swallows_checker_exceptions():
    """A raising checker must never propagate -- it should be treated as
    'down' so a single bad check can never crash the health endpoint."""
    svc = _FakeResolvedService("flaky", [_FakeLink("http://example.invalid:1/")])

    def raises(url: str) -> bool:
        raise RuntimeError("boom")

    results = check_services([svc], checker=raises)
    assert results == {"flaky": "down"}


def test_check_services_no_links_reports_down():
    svc = _FakeResolvedService("no-links", [])
    results = check_services([svc], checker=lambda url: True)
    assert results == {"no-links": "down"}


# --- Real (non-mocked) local-fixture integration test for default_checker ---


def test_default_checker_real_tcp_against_local_fixture_server():
    """Exercise the REAL socket connectivity check (no mocking of the
    socket/networking layer) against a real local TCP listener bound to an
    ephemeral port, and confirm it correctly reports down for a closed port.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    stop = threading.Event()
    server.settimeout(0.2)

    def accept_loop():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
                conn.close()
            except OSError:
                return

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    try:
        up_url = f"http://{host}:{port}/"
        assert default_checker(up_url, timeout=1.0) is True
    finally:
        stop.set()
        server.close()
        thread.join(timeout=2)

    # Now the listener is closed -- the same real code path must report down.
    assert default_checker(up_url, timeout=0.5) is False


def test_default_checker_malformed_url_is_down_not_crash():
    assert default_checker("not a url at all", timeout=0.2) is False
    assert default_checker("http://", timeout=0.2) is False
