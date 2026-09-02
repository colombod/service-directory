"""Tests for the registry-aware health-check additions in health.py:
``check_service_entries`` (priority: heartbeat-fresh -> HTTP health_url ->
TCP fallback) and ``default_http_checker`` (real HTTP, no mocking of the
transport -- exercised against a local stdlib http.server fixture, exactly
like test_federation_real_http.py does for the peer-fetch path).
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from service_directory.health import (
    check_service_entries,
    default_http_checker,
)


def _all_down(url: str) -> bool:
    return False


def _all_up(url: str) -> bool:
    return True


def _http_up(url: str) -> bool:
    return True


def _http_down(url: str) -> bool:
    return False


# --- check_service_entries: priority order -----------------------------------


def test_ttl_entry_reports_up_without_probing_when_survives_prune():
    """A ttl entry that survived pruning-on-read already has a fresh
    heartbeat -- it must be reported 'up' directly, with NO health_url or
    TCP probe at all (both checkers must never be called)."""

    def exploding_http(url):
        raise AssertionError("must not be called for a heartbeat-fresh ttl entry")

    def exploding_tcp(url):
        raise AssertionError("must not be called for a heartbeat-fresh ttl entry")

    entries = [
        {"name": "ttl-svc", "ttl": 30.0, "health_url": "http://x", "links": []},
    ]
    results = check_service_entries(
        entries, checker=exploding_tcp, http_checker=exploding_http
    )
    assert results == {"ttl-svc": "up"}


def test_health_url_checked_via_http_checker_up():
    entries = [
        {
            "name": "http-svc",
            "ttl": None,
            "health_url": "http://example.invalid/health",
            "links": [],
        },
    ]
    results = check_service_entries(entries, checker=_all_down, http_checker=_http_up)
    assert results == {"http-svc": "up"}


def test_health_url_checked_via_http_checker_down():
    entries = [
        {
            "name": "http-svc",
            "ttl": None,
            "health_url": "http://example.invalid/health",
            "links": [],
        },
    ]
    results = check_service_entries(entries, checker=_all_up, http_checker=_http_down)
    assert results == {"http-svc": "down"}


def test_falls_back_to_tcp_checker_when_no_health_url():
    entries = [
        {
            "name": "tcp-svc",
            "ttl": None,
            "health_url": None,
            "links": [
                {"label": "LAN", "host": "10.0.0.1", "url": "http://10.0.0.1:80/"}
            ],
        },
    ]
    results = check_service_entries(entries, checker=_all_up, http_checker=_http_down)
    assert results == {"tcp-svc": "up"}

    results_down = check_service_entries(
        entries, checker=_all_down, http_checker=_http_up
    )
    assert results_down == {"tcp-svc": "down"}


def test_no_links_and_no_health_url_reports_down():
    entries = [{"name": "nothing", "ttl": None, "health_url": None, "links": []}]
    results = check_service_entries(entries, checker=_all_up, http_checker=_http_up)
    assert results == {"nothing": "down"}


def test_http_checker_exception_swallowed_as_down():
    def raising_http(url):
        raise RuntimeError("boom")

    entries = [{"name": "svc", "ttl": None, "health_url": "http://x", "links": []}]
    results = check_service_entries(entries, checker=_all_up, http_checker=raising_http)
    assert results == {"svc": "down"}


def test_mixed_static_and_dynamic_entries():
    entries = [
        {
            "name": "static-svc",
            "ttl": None,
            "health_url": None,
            "source": "static",
            "links": [{"label": "LAN", "host": "h", "url": "http://h:1/"}],
        },
        {
            "name": "dynamic-http",
            "ttl": None,
            "health_url": "http://x/health",
            "source": "dynamic",
            "links": [],
        },
        {
            "name": "dynamic-ttl",
            "ttl": 60.0,
            "health_url": None,
            "source": "dynamic",
            "links": [],
        },
    ]
    results = check_service_entries(entries, checker=_all_down, http_checker=_http_up)
    assert results == {"static-svc": "down", "dynamic-http": "up", "dynamic-ttl": "up"}


# --- default_http_checker: REAL HTTP against a local fixture server ----------


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/healthy":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        elif self.path == "/unhealthy":
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"nope")
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture
def running_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_default_http_checker_real_2xx_is_up(running_server):
    host, port = running_server.server_address
    url = f"http://{host}:{port}/healthy"
    assert default_http_checker(url, timeout=2.0) is True


def test_default_http_checker_real_non_2xx_is_down(running_server):
    host, port = running_server.server_address
    url = f"http://{host}:{port}/unhealthy"
    assert default_http_checker(url, timeout=2.0) is False


def test_default_http_checker_real_404_is_down(running_server):
    host, port = running_server.server_address
    url = f"http://{host}:{port}/nope"
    assert default_http_checker(url, timeout=2.0) is False


def test_default_http_checker_connection_refused_is_down():
    # Nothing listens here (port 1 is a reserved/unlikely-bound port); the
    # real client must treat a connection failure as "down", never raise.
    assert default_http_checker("http://127.0.0.1:1/", timeout=0.5) is False


def test_default_http_checker_malformed_url_is_down_not_crash():
    assert default_http_checker("not a url at all", timeout=0.2) is False
