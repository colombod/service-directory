"""Real-transport integration test for the federation peer-fetch HTTP path.

This deliberately does NOT mock the HTTP client library. It binds a real
stdlib http.server to an ephemeral 127.0.0.1 port, serves canned
/api/services/local responses, and exercises service_directory.federation's
*real* `default_peer_fetcher` (which uses the real httpx2 client) against
it -- the only "fake" thing is the peer's process, not the transport.

Note: `default_peer_fetcher` targets `/api/services/local` (the LOCAL-ONLY
view), never the aggregated `/api/services` -- this is what prevents
mutual-trust peer fetches from recursing into each other's aggregation.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

import pytest
from service_directory.federation import aggregate_services, default_peer_fetcher
from service_directory.trust_store import PeerRecord

SERVICES_BODY = [
    {"name": "muxplex", "description": None, "links": [{"label": "LAN", "host": "1.2.3.4", "url": "http://1.2.3.4:8088/"}]},
]


class _ServicesHandler(BaseHTTPRequestHandler):
    expected_token = "expected-secret-token"

    def log_message(self, format, *args):  # noqa: A002 - silence test server logs
        pass

    def do_GET(self):
        if self.path != "/api/services/local":
            self.send_response(404)
            self.end_headers()
            return

        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {self.expected_token}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"{}")
            return

        payload = json.dumps(SERVICES_BODY).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _HangingHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):
        import time

        time.sleep(2)  # far longer than the bounded peer timeout used below
        self.send_response(200)
        self.end_headers()


@pytest.fixture
def running_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ServicesHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.fixture
def hanging_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HangingHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_default_peer_fetcher_real_http_success(running_server):
    host, port = running_server.server_address
    peer = PeerRecord(
        name="real-peer",
        device_id="dev-real",
        base_url=f"http://{host}:{port}",
        token="expected-secret-token",
    )

    result = default_peer_fetcher(peer, timeout=2.0)
    assert result == SERVICES_BODY


def test_default_peer_fetcher_real_http_wrong_token_raises(running_server):
    host, port = running_server.server_address
    peer = PeerRecord(
        name="real-peer",
        device_id="dev-real",
        base_url=f"http://{host}:{port}",
        token="wrong-token",
    )

    with pytest.raises(Exception):
        default_peer_fetcher(peer, timeout=2.0)


def test_aggregate_services_real_http_end_to_end(running_server):
    """End-to-end: aggregate_services using the REAL default_peer_fetcher
    against a real local peer server -- exercises the actual transport
    integration surface, not a stub."""
    host, port = running_server.server_address
    peer = PeerRecord(
        name="real-peer",
        device_id="dev-real",
        base_url=f"http://{host}:{port}",
        token="expected-secret-token",
    )
    local_services = [
        {"name": "Resolve", "description": None, "links": []},
    ]

    result = aggregate_services(
        local_name="local-node",
        local_services=local_services,
        peers=[peer],
        fetcher=default_peer_fetcher,
        timeout=2.0,
    )

    names_origins = {(svc["name"], svc["origin"]) for svc in result.services}
    assert names_origins == {("Resolve", "local-node"), ("muxplex", "real-peer")}
    assert result.unreachable_peers == []


def test_aggregate_services_real_http_peer_timeout_omitted_local_still_renders(
    hanging_server,
):
    """A real peer that never responds within the bounded timeout must be
    omitted -- local data still renders, nothing raises out of aggregation."""
    host, port = hanging_server.server_address
    peer = PeerRecord(
        name="hanging-peer",
        device_id="dev-hang",
        base_url=f"http://{host}:{port}",
        token="whatever",
    )
    local_services = [{"name": "Resolve", "description": None, "links": []}]

    result = aggregate_services(
        local_name="local-node",
        local_services=local_services,
        peers=[peer],
        fetcher=default_peer_fetcher,
        timeout=0.3,
    )

    assert result.unreachable_peers == ["hanging-peer"]
    names = {svc["name"] for svc in result.services}
    assert names == {"Resolve"}
