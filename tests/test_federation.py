from __future__ import annotations

import time

from service_directory.federation import aggregate_services
from service_directory.trust_store import PeerRecord

LOCAL_SERVICES = [
    {"name": "Resolve", "description": None, "links": [{"label": "LAN", "host": "1.2.3.4", "url": "http://1.2.3.4:8080/"}]},
]

PEER_A = PeerRecord(name="node-a", device_id="dev-a", base_url="http://node-a", token="tok-a")
PEER_B = PeerRecord(name="node-b", device_id="dev-b", base_url="http://node-b", token="tok-b")


def test_aggregate_merges_local_and_stubbed_peer_tagged_by_origin():
    peer_services = [
        {"name": "muxplex", "description": None, "links": []},
    ]

    def stub_fetcher(peer, timeout):
        assert peer.name == "node-a"
        return peer_services

    result = aggregate_services(
        local_name="local-node",
        local_services=LOCAL_SERVICES,
        peers=[PEER_A],
        fetcher=stub_fetcher,
    )

    by_name = {svc["name"]: svc for svc in result.services}
    assert by_name["Resolve"]["origin"] == "local-node"
    assert by_name["muxplex"]["origin"] == "node-a"
    assert result.reachable_peers == ["local-node", "node-a"]
    assert result.unreachable_peers == []


def test_aggregate_local_always_renders_even_with_no_peers():
    result = aggregate_services("local-node", LOCAL_SERVICES, peers=[])
    assert len(result.services) == 1
    assert result.services[0]["origin"] == "local-node"


def test_aggregate_degrades_gracefully_when_peer_raises():
    def raising_fetcher(peer, timeout):
        raise ConnectionError("peer is down")

    result = aggregate_services(
        local_name="local-node",
        local_services=LOCAL_SERVICES,
        peers=[PEER_A],
        fetcher=raising_fetcher,
    )

    # local list still renders in full
    names = {svc["name"] for svc in result.services}
    assert names == {"Resolve"}
    assert result.unreachable_peers == ["node-a"]
    assert result.reachable_peers == ["local-node"]


def test_aggregate_degrades_gracefully_when_peer_times_out():
    def slow_fetcher(peer, timeout):
        # simulate the fetcher itself enforcing the timeout and raising
        raise TimeoutError(f"peer {peer.name} timed out after {timeout}s")

    result = aggregate_services(
        local_name="local-node",
        local_services=LOCAL_SERVICES,
        peers=[PEER_A],
        fetcher=slow_fetcher,
        timeout=0.01,
    )
    assert result.unreachable_peers == ["node-a"]
    names = {svc["name"] for svc in result.services}
    assert names == {"Resolve"}


def test_aggregate_one_peer_down_does_not_omit_other_reachable_peers():
    def selective_fetcher(peer, timeout):
        if peer.name == "node-a":
            raise ConnectionError("down")
        return [{"name": "from-b", "description": None, "links": []}]

    result = aggregate_services(
        local_name="local-node",
        local_services=LOCAL_SERVICES,
        peers=[PEER_A, PEER_B],
        fetcher=selective_fetcher,
    )

    names = {svc["name"] for svc in result.services}
    assert names == {"Resolve", "from-b"}
    assert result.unreachable_peers == ["node-a"]
    assert "node-b" in result.reachable_peers


def test_aggregate_preserves_upstream_origin_when_already_tagged():
    """A peer relaying an already-federated list (its own aggregation
    result) must not have its origin fields overwritten -- credit stays
    with the node that actually owns the service."""

    def relaying_fetcher(peer, timeout):
        return [
            {"name": "deep", "description": None, "links": [], "origin": "far-node"}
        ]

    result = aggregate_services(
        local_name="local-node",
        local_services=LOCAL_SERVICES,
        peers=[PEER_A],
        fetcher=relaying_fetcher,
    )
    by_name = {svc["name"]: svc for svc in result.services}
    assert by_name["deep"]["origin"] == "far-node"


def test_aggregate_peer_timeout_is_bounded_real_elapsed_time():
    """A fetcher that actually sleeps past the timeout must still return
    promptly because aggregate_services runs peers concurrently -- this
    guards against an accidental sequential/blocking merge implementation."""

    def slow_but_eventually_succeeds(peer, timeout):
        time.sleep(0.05)
        return [{"name": f"svc-{peer.name}", "description": None, "links": []}]

    peers = [
        PeerRecord(name=f"p{i}", device_id=f"d{i}", base_url=f"http://p{i}", token=f"t{i}")
        for i in range(5)
    ]
    start = time.monotonic()
    result = aggregate_services(
        local_name="local-node",
        local_services=LOCAL_SERVICES,
        peers=peers,
        fetcher=slow_but_eventually_succeeds,
    )
    elapsed = time.monotonic() - start
    # if run sequentially this would take ~0.25s; concurrently it's ~0.05s
    assert elapsed < 0.2
    assert len(result.reachable_peers) == 6  # local + 5 peers
