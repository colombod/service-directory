"""Tests for the federation catalogue feature set:

- FederationConfig.description / .role parsing and advertising via
  GET /api/instance-info (additive, backward-compatible).
- GET /api/federation/nodes: this node + trusted peers, reachability
  reused from the SAME AggregationResult as /api/services (no second
  probe).
- Dashboard HTML (GET /): grouped by origin node, contains the
  search/filter <input>, health dots wired to /api/health.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from service_directory.app import create_app
from service_directory.config import (
    ConfigError,
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
    parse_config,
)
from service_directory.trust_store import PeerRecord, upsert_peer

BASE_YAML = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "svc", port: 80}
"""


def _all_down(url: str) -> bool:
    return False


def _make_config(tmp_path, *, enabled=True, description=None, role=None):
    return RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[Service(name="Resolve", port=8080, path="/", description="d")],
        federation=FederationConfig(
            enabled=enabled,
            name="local-node",
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
            require_read_token=False,
            description=description,
            role=role,
        ),
    )


def _localhost_client(app) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 12345))


def _remote_client(app) -> TestClient:
    return TestClient(app, client=("203.0.113.9", 12345))


# --- config.py: federation.description / federation.role ---------------------


def test_federation_description_and_role_default_to_none_when_absent():
    cfg = parse_config(BASE_YAML)
    assert cfg.federation.description is None
    assert cfg.federation.role is None


def test_federation_description_and_role_parse_when_present():
    yaml_text = BASE_YAML + (
        "federation:\n"
        "  enabled: true\n"
        "  description: My home lab node\n"
        "  role: primary\n"
    )
    cfg = parse_config(yaml_text)
    assert cfg.federation.description == "My home lab node"
    assert cfg.federation.role == "primary"


@pytest.mark.parametrize(
    "bad_field,expected_match",
    [
        ("description: 5", "description"),
        ("role: 5", "role"),
    ],
)
def test_federation_description_role_malformed_raises(bad_field, expected_match):
    yaml_text = BASE_YAML + f"federation:\n  {bad_field}\n"
    with pytest.raises(ConfigError, match=expected_match):
        parse_config(yaml_text)


def test_legacy_federation_block_without_new_fields_still_works():
    """A federation block using ONLY the pre-existing keys must parse
    identically -- new fields default to None."""
    yaml_text = BASE_YAML + (
        "federation:\n"
        "  enabled: true\n"
        "  name: my-node\n"
        "  base_url: http://10.0.0.1:80\n"
    )
    cfg = parse_config(yaml_text)
    assert cfg.federation.enabled is True
    assert cfg.federation.name == "my-node"
    assert cfg.federation.description is None
    assert cfg.federation.role is None


# --- /api/instance-info: additive fields --------------------------------------


def test_instance_info_omits_description_role_when_unset(tmp_path):
    """Existing contract preserved EXACTLY: when description/role are not
    configured, the response must contain only the original 4 keys."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)

    resp = client.get("/api/instance-info")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"name", "device_id", "version", "federation_enabled"}


def test_instance_info_includes_description_and_role_when_set(tmp_path):
    config = _make_config(tmp_path, description="Home lab tailnet node", role="primary")
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)

    resp = client.get("/api/instance-info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "Home lab tailnet node"
    assert data["role"] == "primary"
    assert data["name"] == "local-node"


def test_instance_info_includes_only_description_when_role_unset(tmp_path):
    config = _make_config(tmp_path, description="just a description")
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)
    data = client.get("/api/instance-info").json()
    assert data["description"] == "just a description"
    assert "role" not in data


# --- /api/federation/nodes ----------------------------------------------------


def test_federation_nodes_returns_this_node_always_reachable(tmp_path):
    config = _make_config(tmp_path, description="my description", role="primary")
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    resp = client.get("/api/federation/nodes")
    assert resp.status_code == 200
    nodes = resp.json()
    assert len(nodes) == 1
    this = nodes[0]
    assert this["name"] == "local-node"
    assert this["description"] == "my description"
    assert this["role"] == "primary"
    assert this["base_url"] == "http://10.0.0.1:80"
    assert this["reachable"] is True
    assert len(this["device_id"]) == 36


def test_federation_nodes_includes_reachable_and_unreachable_peers(tmp_path):
    config = _make_config(tmp_path)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(name="peer-up", device_id="d-up", base_url="http://peer-up", token="t-up"),
    )
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(name="peer-down", device_id="d-down", base_url="http://peer-down", token="t-down"),
    )

    def stub_fetcher(peer, timeout):
        if peer.name == "peer-down":
            raise ConnectionError("simulated peer down")
        return [{"name": "some-svc", "description": None, "links": []}]

    app = create_app(config, checker=_all_down, peer_fetcher=stub_fetcher)
    client = _localhost_client(app)

    resp = client.get("/api/federation/nodes")
    assert resp.status_code == 200
    nodes = resp.json()
    by_name = {n["name"]: n for n in nodes}

    assert set(by_name.keys()) == {"local-node", "peer-up", "peer-down"}
    assert by_name["local-node"]["reachable"] is True
    assert by_name["peer-up"]["reachable"] is True
    assert by_name["peer-down"]["reachable"] is False
    assert by_name["peer-up"]["device_id"] == "d-up"
    assert by_name["peer-up"]["base_url"] == "http://peer-up"
    assert by_name["peer-down"]["device_id"] == "d-down"


def test_federation_nodes_reuses_same_aggregation_no_second_probe(tmp_path):
    """The reachable flag must come from the SAME AggregationResult used by
    /api/services -- verified by counting fetcher invocations: exactly one
    call per peer, not two (which would happen with a duplicate probe)."""
    config = _make_config(tmp_path)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(name="peer-x", device_id="dx", base_url="http://peer-x", token="tok-x"),
    )

    call_count = {"n": 0}

    def counting_fetcher(peer, timeout):
        call_count["n"] += 1
        return [{"name": "svc", "description": None, "links": []}]

    app = create_app(config, checker=_all_down, peer_fetcher=counting_fetcher)
    client = _localhost_client(app)

    resp = client.get("/api/federation/nodes")
    assert resp.status_code == 200
    assert call_count["n"] == 1


def test_federation_nodes_respects_read_access_rules(tmp_path):
    config = RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[Service(name="Resolve", port=8080)],
        federation=FederationConfig(
            enabled=True,
            name="local-node",
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
            require_read_token=True,
        ),
    )
    app = create_app(config, checker=_all_down)
    remote = _remote_client(app)
    resp = remote.get("/api/federation/nodes")
    assert resp.status_code == 401

    local = _localhost_client(app)
    resp2 = local.get("/api/federation/nodes")
    assert resp2.status_code == 200


def test_federation_nodes_federation_disabled_no_peer_io(tmp_path):
    config = _make_config(tmp_path, enabled=False)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(name="peer-x", device_id="dx", base_url="http://peer-x", token="tok-x"),
    )

    def exploding_fetcher(peer, timeout):
        raise AssertionError("must not be called when federation is disabled")

    app = create_app(config, checker=_all_down, peer_fetcher=exploding_fetcher)
    client = _localhost_client(app)
    resp = client.get("/api/federation/nodes")
    assert resp.status_code == 200
    nodes = resp.json()
    # Only "this node" -- peers are not probed and not listed as reachable
    # via aggregation, but they ARE still trust-store entries; either way
    # the exploding fetcher must never be invoked.
    assert nodes[0]["name"] == "local-node"
    assert nodes[0]["reachable"] is True


# --- dashboard HTML: grouping by origin + search input ------------------------


def test_index_html_groups_services_by_origin_node(tmp_path):
    config = _make_config(tmp_path, description="Local description")
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(name="peer-x", device_id="dx", base_url="http://peer-x", token="tok-x"),
    )

    def stub_fetcher(peer, timeout):
        return [{"name": "remote-svc", "description": "remote desc", "links": []}]

    app = create_app(config, checker=_all_down, peer_fetcher=stub_fetcher)
    client = _localhost_client(app)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text

    # Both origin node names appear as section headers/groupings.
    assert "local-node" in html
    assert "peer-x" in html
    assert "Local description" in html

    # Origin sections exist and are distinguishable (data-origin attrs).
    assert 'data-origin="local-node"' in html
    assert 'data-origin="peer-x"' in html

    # Each service still shows under its own group.
    assert "Resolve" in html
    assert "remote-svc" in html


def test_index_html_contains_filter_input(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert '<input' in resp.text
    assert 'id="service-filter"' in resp.text
    # No CDN / external script tags -- inline only.
    assert "<script src=" not in resp.text
    assert "cdn." not in resp.text.lower()


def test_index_html_still_renders_for_legacy_config_no_new_fields(sample_config):
    """The dashboard must render fine for a config with no federation
    metadata at all (single implicit local group)."""
    app = create_app(sample_config, checker=_all_down)
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<html" in resp.text.lower()
    assert 'id="service-filter"' in resp.text


def test_index_html_includes_health_dot_markup(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    resp = client.get("/")
    assert "health-dot" in resp.text
