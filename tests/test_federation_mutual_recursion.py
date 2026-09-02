"""Regression test for the mutual-federation recursion bug.

Federation is bidirectional: two mutually-trusted nodes each treat the
other as a peer. Before the fix, ``default_peer_fetcher`` hit the peer's
*aggregated* ``/api/services`` endpoint -- so when A aggregated and fetched
B's ``/api/services``, B in turn aggregated and fetched A's
``/api/services``, recursing. With the ~1s peer timeout, each nested hop
burned the budget of the one above it, so the OUTER fetch always timed out
and the peer was silently dropped (``_fetch_one`` swallows exceptions). Net
effect: in any mutual-trust graph, every node only ever saw its OWN
services -- never its peer's.

This test stands up TWO real, independently-running FastAPI apps (via
uvicorn, on ephemeral 127.0.0.1 ports -- never a hardcoded port, following
the pattern already established in ``test_cli_federation.py``), mutually
trusts them, and wires each one's ``peer_fetcher`` to the REAL
``default_peer_fetcher`` -- a real HTTP client hitting the other app's real
endpoint over a real socket. It does NOT stub the fetcher with a canned
list, so it actually exercises the aggregate -> fetch -> peer-endpoint path
and would have caught the recursion: on the buggy code this test times out
(or produces a response missing the peer's services) rather than merely
failing an assertion instantly, so a generous timeout wrapper is used to
turn "still recursing" into a clean failure instead of hanging the suite.
"""

from __future__ import annotations

import threading
import time

import pytest
from service_directory.app import create_app
from service_directory.config import (
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
)
from service_directory.federation import default_peer_fetcher
from service_directory.trust_store import PeerRecord, upsert_peer


def _all_down(url: str) -> bool:
    return False


class _ServerThread:
    """Runs a real FastAPI app on a real, ephemeral 127.0.0.1 port."""

    def __init__(self, app):
        import uvicorn

        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> str:
        self.thread.start()
        for _ in range(300):
            if getattr(self.server, "started", False):
                break
            time.sleep(0.01)
        sockets = self.server.servers[0].sockets
        host, port = sockets[0].getsockname()[:2]
        return f"http://{host}:{port}"

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


def _config(tmp_path, *, name: str, service_name: str) -> RegistryConfig:
    return RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[Service(name=service_name, port=8080, path="/", description=None)],
        federation=FederationConfig(
            enabled=True,
            name=name,
            base_url="http://ignored:80",
            state_dir=str(tmp_path / f"state-{name}"),
            require_read_token=False,
        ),
    )


@pytest.fixture
def mutual_nodes(tmp_path):
    """Two REAL, mutually-trusted nodes, each wired to the REAL
    default_peer_fetcher pointed at the OTHER node's real running server --
    no stubbed fetcher, no canned peer response.
    """
    config_a = _config(tmp_path, name="node-a", service_name="svc-on-a")
    config_b = _config(tmp_path, name="node-b", service_name="svc-on-b")

    app_a = create_app(config_a, checker=_all_down, peer_fetcher=default_peer_fetcher)
    app_b = create_app(config_b, checker=_all_down, peer_fetcher=default_peer_fetcher)

    server_a = _ServerThread(app_a)
    server_b = _ServerThread(app_b)
    base_url_a = server_a.start()
    base_url_b = server_b.start()

    # Mutual trust: A trusts B (reachable at base_url_b) and vice versa.
    upsert_peer(
        config_a.federation.state_dir,
        PeerRecord(
            name="node-b", device_id="dev-b", base_url=base_url_b, token="shared-tok"
        ),
    )
    upsert_peer(
        config_b.federation.state_dir,
        PeerRecord(
            name="node-a", device_id="dev-a", base_url=base_url_a, token="shared-tok"
        ),
    )

    try:
        yield base_url_a, base_url_b
    finally:
        server_a.stop()
        server_b.stop()


def _get_with_deadline(url: str, *, deadline_seconds: float):
    """A plain, real HTTP GET bounded by a hard wall-clock deadline so a
    still-recursing/hanging server produces a clean test failure instead of
    hanging the whole suite.
    """
    import httpx2 as httpx

    with httpx.Client(timeout=deadline_seconds) as client:
        return client.get(url)


def test_mutual_federation_no_recursion_both_nodes_see_each_other(mutual_nodes):
    base_url_a, base_url_b = mutual_nodes

    start = time.monotonic()
    resp_a = _get_with_deadline(f"{base_url_a}/api/services", deadline_seconds=10.0)
    elapsed_a = time.monotonic() - start
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    by_name_a = {svc["name"]: svc["origin"] for svc in data_a}
    assert by_name_a.get("svc-on-a") == "node-a"
    assert by_name_a.get("svc-on-b") == "node-b"
    # generous bound: real aggregation across one real peer completes well
    # under a second; anything close to the recursive-timeout regime (each
    # nested hop burns ~1s) would blow well past this.
    assert elapsed_a < 5.0

    start = time.monotonic()
    resp_b = _get_with_deadline(f"{base_url_b}/api/services", deadline_seconds=10.0)
    elapsed_b = time.monotonic() - start
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    by_name_b = {svc["name"]: svc["origin"] for svc in data_b}
    assert by_name_b.get("svc-on-b") == "node-b"
    assert by_name_b.get("svc-on-a") == "node-a"
    assert elapsed_b < 5.0


def test_local_only_endpoint_never_includes_peer_services(mutual_nodes):
    """The dedicated local-only view must return ONLY the node's own
    services, tagged with the local origin, regardless of any configured
    peers -- this is the endpoint default_peer_fetcher targets, and it must
    never itself aggregate."""
    base_url_a, _base_url_b = mutual_nodes

    resp = _get_with_deadline(f"{base_url_a}/api/services/local", deadline_seconds=5.0)
    assert resp.status_code == 200
    data = resp.json()
    names = {svc["name"] for svc in data}
    assert names == {"svc-on-a"}
    assert all(svc["origin"] == "node-a" for svc in data)
