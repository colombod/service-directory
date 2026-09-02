from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from service_directory.app import create_app
from service_directory.config import (
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
)
from service_directory.trust_store import PeerRecord, load_peers, upsert_peer


def _all_down(url: str) -> bool:
    return False


def _make_config(tmp_path, *, enabled=True, require_read_token=False, name="local-node"):
    return RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[Service(name="Resolve", port=8080, path="/", description="d")],
        federation=FederationConfig(
            enabled=enabled,
            name=name,
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
            require_read_token=require_read_token,
        ),
    )


def _localhost_client(app) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 12345))


def _remote_client(app) -> TestClient:
    return TestClient(app, client=("203.0.113.9", 12345))


# --- pull-aggregation via /api/services and / -------------------------------


def test_api_services_tags_local_entries_with_origin(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    resp = client.get("/api/services")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["origin"] == "local-node"

    # JSON round-trips (contract check)
    assert json.loads(resp.text) == data


def test_api_services_merges_stubbed_peer_tagged_by_origin(tmp_path):
    config = _make_config(tmp_path)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(name="peer-x", device_id="dx", base_url="http://peer-x", token="tok-x"),
    )

    def stub_fetcher(peer, timeout):
        return [{"name": "muxplex", "description": None, "links": []}]

    app = create_app(config, checker=_all_down, peer_fetcher=stub_fetcher)
    client = _localhost_client(app)

    resp = client.get("/api/services")
    data = resp.json()
    by_name = {svc["name"]: svc for svc in data}
    assert by_name["Resolve"]["origin"] == "local-node"
    assert by_name["muxplex"]["origin"] == "peer-x"


def test_api_services_degrades_gracefully_when_peer_raises(tmp_path):
    """A down/unreachable peer must be omitted, never break the response --
    the local list still renders."""
    config = _make_config(tmp_path)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(name="peer-x", device_id="dx", base_url="http://peer-x", token="tok-x"),
    )

    def raising_fetcher(peer, timeout):
        raise ConnectionError("simulated peer down")

    app = create_app(config, checker=_all_down, peer_fetcher=raising_fetcher)
    client = _localhost_client(app)

    resp = client.get("/api/services")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Resolve"
    assert data[0]["origin"] == "local-node"


def test_index_html_renders_and_includes_origin_when_peer_down(tmp_path):
    config = _make_config(tmp_path)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(name="peer-x", device_id="dx", base_url="http://peer-x", token="tok-x"),
    )

    def raising_fetcher(peer, timeout):
        raise ConnectionError("down")

    app = create_app(config, checker=_all_down, peer_fetcher=raising_fetcher)
    client = _localhost_client(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Resolve" in resp.text
    assert "local-node" in resp.text


def test_api_services_federation_disabled_never_calls_peer_fetcher(tmp_path):
    config = _make_config(tmp_path, enabled=False)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(name="peer-x", device_id="dx", base_url="http://peer-x", token="tok-x"),
    )

    def exploding_fetcher(peer, timeout):
        raise AssertionError("must not be called when federation is disabled")

    app = create_app(config, checker=_all_down, peer_fetcher=exploding_fetcher)
    client = _localhost_client(app)
    resp = client.get("/api/services")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["origin"] == "local-node"


# --- instance-info -----------------------------------------------------------


def test_instance_info_unauthenticated_and_no_secrets(tmp_path):
    config = _make_config(tmp_path)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(name="peer-x", device_id="dx", base_url="http://peer-x", token="super-secret-token"),
    )
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)  # no auth header, remote IP -- still works

    resp = client.get("/api/instance-info")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"name", "device_id", "version", "federation_enabled"}
    assert data["name"] == "local-node"
    assert data["federation_enabled"] is True
    assert len(data["device_id"]) == 36

    # No secrets/tokens/peer info anywhere in the response body.
    assert "super-secret-token" not in resp.text
    assert "peer-x" not in resp.text
    assert "token" not in resp.text.lower()


# --- read-token gating --------------------------------------------------------


def test_read_endpoints_open_by_default_for_remote(tmp_path):
    config = _make_config(tmp_path, require_read_token=False)
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)
    assert client.get("/").status_code == 200
    assert client.get("/api/services").status_code == 200
    assert client.get("/api/health").status_code == 200


def test_read_endpoints_require_token_when_flag_set(tmp_path):
    config = _make_config(tmp_path, require_read_token=True)
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)

    assert client.get("/").status_code == 401
    assert client.get("/api/services").status_code == 401
    assert client.get("/api/health").status_code == 401


def test_read_endpoints_localhost_bypass_when_token_required(tmp_path):
    config = _make_config(tmp_path, require_read_token=True)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    assert client.get("/").status_code == 200
    assert client.get("/api/services").status_code == 200
    assert client.get("/api/health").status_code == 200


def test_read_endpoints_valid_peer_token_when_required(tmp_path):
    config = _make_config(tmp_path, require_read_token=True)
    upsert_peer(
        config.federation.state_dir,
        PeerRecord(name="peer-x", device_id="dx", base_url="http://peer-x", token="valid-token"),
    )

    def stub_fetcher(peer, timeout):
        return []

    app = create_app(config, checker=_all_down, peer_fetcher=stub_fetcher)
    client = _remote_client(app)

    resp = client.get("/api/services", headers={"Authorization": "Bearer valid-token"})
    assert resp.status_code == 200

    resp_wrong = client.get("/api/services", headers={"Authorization": "Bearer wrong"})
    assert resp_wrong.status_code == 401


# --- pairing handshake ---------------------------------------------------------


def test_pairing_code_issue_localhost_only(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)

    remote = _remote_client(app)
    assert remote.post("/api/federation/pairing-code").status_code == 401

    local = _localhost_client(app)
    resp = local.post("/api/federation/pairing-code")
    assert resp.status_code == 200
    data = resp.json()
    assert "code" in data
    assert data["ttl_seconds"] > 0


def test_pair_endpoint_mutual_trust_established(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    local = _localhost_client(app)
    remote = _remote_client(app)

    code_resp = local.post("/api/federation/pairing-code")
    code = code_resp.json()["code"]

    pair_resp = remote.post(
        "/api/federation/pair",
        json={
            "device_id": "caller-device-id",
            "name": "caller-node",
            "base_url": "http://caller:80",
            "code": code,
        },
    )
    assert pair_resp.status_code == 200
    body = pair_resp.json()
    assert body["name"] == "local-node"
    assert "token" in body
    assert len(body["device_id"]) == 36

    # the caller is now in the local trust store
    peers = load_peers(config.federation.state_dir)
    assert len(peers) == 1
    assert peers[0].name == "caller-node"
    assert peers[0].base_url == "http://caller:80"


def test_pair_endpoint_rejects_reused_code(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    local = _localhost_client(app)
    remote = _remote_client(app)

    code = local.post("/api/federation/pairing-code").json()["code"]
    payload = {
        "device_id": "caller-device-id",
        "name": "caller-node",
        "base_url": "http://caller:80",
        "code": code,
    }
    first = remote.post("/api/federation/pair", json=payload)
    assert first.status_code == 200

    second = remote.post("/api/federation/pair", json=payload)
    assert second.status_code == 400


def test_pair_endpoint_rejects_unknown_code(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    remote = _remote_client(app)

    resp = remote.post(
        "/api/federation/pair",
        json={
            "device_id": "caller-device-id",
            "name": "caller-node",
            "base_url": "http://caller:80",
            "code": "never-issued-code",
        },
    )
    assert resp.status_code == 400
