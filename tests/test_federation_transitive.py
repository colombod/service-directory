"""Bounded TRANSITIVE federation aggregation (visited-set + hop budget).

Goal: any node's GET /api/services reflects the ENTIRE CONNECTED federation,
not just its direct peers -- so pairing each new node to ANY ONE existing
member suffices (no full mesh). Must be loop-safe: a cycle can never recurse
infinitely (visited-set) and depth is bounded (ttl).

These tests are hermetic -- NO real network. Each node is a real in-process
FastAPI app; a `peer_fetcher_factory` transport wires one node's peer-fetch to
call the OTHER node's real `/api/services` endpoint via its TestClient, forwarding
the visited-set + ttl headers exactly as production HTTP would. That means the
transitive walk (aggregate -> fetch peer's aggregated view -> which itself
aggregates, bounded) is exercised for real across nodes, not stubbed.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from service_directory.app import create_app
from service_directory.config import (
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
)
from service_directory.federation import (
    FEDERATION_HOP_HEADER,
    FEDERATION_TTL_HEADER,
    FEDERATION_VISITED_HEADER,
)
from service_directory.trust_store import PeerRecord, upsert_peer


def _all_down(url: str) -> bool:
    return False


def _config(tmp_path, name, service_name):
    return RegistryConfig(
        host_addresses=[HostAddress(label="Tailnet", host="10.0.0.1")],
        services=[Service(name=service_name, port=8080, path="/")],
        federation=FederationConfig(
            enabled=True,
            name=name,
            base_url=f"http://{name}",
            state_dir=str(tmp_path / name),
        ),
    )


class _Fabric:
    """A set of interconnected in-process nodes. Each node's peer-fetch calls
    the target node's real /api/services TestClient with visited/ttl headers --
    a faithful in-process stand-in for the production HTTP transport."""

    def __init__(self):
        self.clients: dict[str, TestClient] = {}

    def factory_for(self, node_name):
        # Returns a peer_fetcher_factory(visited, ttl) -> (peer, timeout) fetcher.
        def factory(visited, ttl):
            def fetch(peer, timeout):
                client = self.clients[peer.name]
                headers = {
                    FEDERATION_HOP_HEADER: "1",
                    FEDERATION_VISITED_HEADER: ",".join(sorted(visited)),
                    FEDERATION_TTL_HEADER: str(ttl),
                }
                resp = client.get("/api/services", headers=headers)
                resp.raise_for_status()
                return resp.json()

            return fetch

        return factory


def _make_node(fabric, tmp_path, name, service_name):
    config = _config(tmp_path, name, service_name)
    app = create_app(
        config,
        checker=_all_down,
        peer_fetcher_factory=fabric.factory_for(name),
    )
    client = TestClient(app, client=("127.0.0.1", 12345))
    fabric.clients[name] = client
    return config, client


def _pair(config_a, config_b):
    """Make A trust B (one direction). Uses the trust store directly."""
    upsert_peer(
        config_a.federation.state_dir,
        PeerRecord(
            name=config_b.federation.name,
            device_id="dev-" + config_b.federation.name,
            base_url=config_b.federation.base_url,
            token="tok-" + config_b.federation.name,
        ),
    )


def _names(services):
    return sorted((s["name"], s.get("origin")) for s in services)


# --- the headline: a 3-node CHAIN, A not paired to C -------------------------


def test_chain_a_sees_c_without_direct_pairing(tmp_path):
    fabric = _Fabric()
    ca, _ = _make_node(fabric, tmp_path, "node-a", "svc-a")
    cb, _ = _make_node(fabric, tmp_path, "node-b", "svc-b")
    cc, _ = _make_node(fabric, tmp_path, "node-c", "svc-c")

    # Chain: A<->B<->C. A is NOT paired with C.
    _pair(ca, cb)
    _pair(cb, ca)
    _pair(cb, cc)
    _pair(cc, cb)

    got = _names(fabric.clients["node-a"].get("/api/services").json())
    assert ("svc-a", "node-a") in got
    assert ("svc-b", "node-b") in got
    assert ("svc-c", "node-c") in got, "A must see C transitively via B"

    # Symmetric: C sees A.
    got_c = _names(fabric.clients["node-c"].get("/api/services").json())
    assert ("svc-a", "node-a") in got_c
    assert ("svc-c", "node-c") in got_c


# --- loop safety: a mutual cycle terminates and does not double-count ---------


def test_cycle_terminates_no_double_count(tmp_path):
    fabric = _Fabric()
    ca, _ = _make_node(fabric, tmp_path, "node-a", "svc-a")
    cb, _ = _make_node(fabric, tmp_path, "node-b", "svc-b")
    _pair(ca, cb)
    _pair(cb, ca)

    services = fabric.clients["node-a"].get("/api/services").json()
    got = _names(services)
    assert got == [("svc-a", "node-a"), ("svc-b", "node-b")]
    # Exactly one entry per (origin, name) -- no path-driven duplication.
    assert len(services) == 2


# --- hop cap: budget smaller than the chain excludes far nodes (bounded) -----


def test_hop_cap_excludes_beyond_budget(tmp_path):
    fabric = _Fabric()
    ca, _ = _make_node(fabric, tmp_path, "node-a", "svc-a")
    cb, _ = _make_node(fabric, tmp_path, "node-b", "svc-b")
    cc, _ = _make_node(fabric, tmp_path, "node-c", "svc-c")
    _pair(ca, cb)
    _pair(cb, ca)
    _pair(cb, cc)
    _pair(cc, cb)

    # ttl=1 budget: A -> B allowed (1 hop), but B->C would need another hop.
    resp = fabric.clients["node-a"].get(
        "/api/services", headers={FEDERATION_HOP_HEADER: "1", FEDERATION_TTL_HEADER: "1"}
    )
    got = _names(resp.json())
    assert ("svc-a", "node-a") in got
    assert ("svc-b", "node-b") in got
    assert ("svc-c", "node-c") not in got  # beyond the 1-hop budget, bounded not error


# --- a down intermediate peer is omitted; the rest still renders --------------


def test_down_peer_omitted_rest_renders(tmp_path):
    fabric = _Fabric()
    ca, _ = _make_node(fabric, tmp_path, "node-a", "svc-a")
    cb, _ = _make_node(fabric, tmp_path, "node-b", "svc-b")
    _pair(ca, cb)
    _pair(cb, ca)

    # Make node-b unreachable: replace its client with one that raises.
    class _Boom:
        def get(self, *a, **k):
            raise ConnectionError("node-b down")

    fabric.clients["node-b"] = _Boom()

    got = _names(fabric.clients["node-a"].get("/api/services").json())
    assert ("svc-a", "node-a") in got  # local still renders
    assert all(origin != "node-b" for _, origin in got)  # down peer omitted


# --- /api/services/local stays a PURE local-only view (regression guard) ------


def test_local_endpoint_stays_local_only(tmp_path):
    fabric = _Fabric()
    ca, _ = _make_node(fabric, tmp_path, "node-a", "svc-a")
    cb, _ = _make_node(fabric, tmp_path, "node-b", "svc-b")
    _pair(ca, cb)
    _pair(cb, ca)

    local = fabric.clients["node-a"].get("/api/services/local").json()
    got = _names(local)
    assert got == [("svc-a", "node-a")]  # ONLY this node's own services
