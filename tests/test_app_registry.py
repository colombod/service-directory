"""App-level (FastAPI TestClient) tests for the dynamic service registry:
POST /api/services, DELETE /api/services/{name},
POST /api/services/{name}/heartbeat, and their effects on GET /api/services,
GET /api/services/local, GET /api/health, and the rendered dashboard HTML.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from service_directory.app import create_app
from service_directory.config import (
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
)
from service_directory.registry import DynamicService, register_service
from service_directory.write_token import issue_write_token


def _all_down(url: str) -> bool:
    return False


def _all_up(url: str) -> bool:
    return True


def _make_config(tmp_path, *, require_write_token=False, name="local-node"):
    return RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[Service(name="Resolve", port=8080, path="/", description="d")],
        federation=FederationConfig(
            enabled=True,
            name=name,
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
            require_write_token=require_write_token,
        ),
    )


def _localhost_client(app) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 12345))


def _remote_client(app) -> TestClient:
    return TestClient(app, client=("203.0.113.9", 12345))


# --- POST /api/services: register/upsert -------------------------------------


def test_register_via_localhost_bypass_appears_in_api_services(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    resp = client.post(
        "/api/services",
        json={"name": "agent-svc", "port": 9000, "description": "an agent service"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "agent-svc"
    assert body["source"] == "dynamic"

    services = client.get("/api/services").json()
    by_name = {svc["name"]: svc for svc in services}
    assert "agent-svc" in by_name
    assert by_name["agent-svc"]["source"] == "dynamic"
    assert by_name["Resolve"]["source"] == "static"

    # Also flows through /api/services/local (federation surface).
    local = client.get("/api/services/local").json()
    local_by_name = {svc["name"]: svc for svc in local}
    assert local_by_name["agent-svc"]["source"] == "dynamic"

    # JSON round-trips (contract check).
    assert json.loads(client.get("/api/services").text) == services


def test_register_with_valid_write_token_from_remote(tmp_path):
    config = _make_config(tmp_path)
    token = issue_write_token(config.federation.state_dir)
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)

    resp = client.post(
        "/api/services",
        json={"name": "remote-agent", "port": 7000},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "remote-agent"


def test_register_without_token_from_remote_is_401(tmp_path):
    """Hard requirement: there is NO unauthenticated mutation path. A
    remote (non-localhost) client with no token must be rejected."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)

    resp = client.post("/api/services", json={"name": "bad-actor", "port": 1})
    assert resp.status_code == 401

    # Confirm it was never actually registered.
    local_client = _localhost_client(app)
    names = {svc["name"] for svc in local_client.get("/api/services").json()}
    assert "bad-actor" not in names


def test_register_with_wrong_token_from_remote_is_401(tmp_path):
    config = _make_config(tmp_path)
    issue_write_token(config.federation.state_dir)
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)

    resp = client.post(
        "/api/services",
        json={"name": "bad-actor", "port": 1},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


def test_register_dynamic_name_colliding_with_static_is_409(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    resp = client.post("/api/services", json={"name": "Resolve", "port": 1})
    assert resp.status_code == 409

    # Static entry must be completely unaffected (no silent shadowing).
    services = client.get("/api/services").json()
    resolve_entries = [s for s in services if s["name"] == "Resolve"]
    assert len(resolve_entries) == 1
    assert resolve_entries[0]["source"] == "static"


def test_register_missing_name_is_rejected(tmp_path):
    """`name` is a required field -- FastAPI/pydantic rejects a missing
    required field with 422 before the handler ever runs."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    resp = client.post("/api/services", json={"port": 1})
    assert resp.status_code == 422


def test_register_missing_port_and_url_is_400(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    resp = client.post("/api/services", json={"name": "no-port-no-url"})
    assert resp.status_code == 400


def test_register_upsert_updates_existing_dynamic_entry(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    client.post("/api/services", json={"name": "svc", "port": 1})
    resp = client.post(
        "/api/services", json={"name": "svc", "port": 2, "description": "updated"}
    )
    assert resp.status_code == 200

    services = client.get("/api/services").json()
    matches = [s for s in services if s["name"] == "svc"]
    assert len(matches) == 1
    assert matches[0]["description"] == "updated"


# --- DELETE /api/services/{name}: deregister ----------------------------------


def test_delete_removes_dynamic_entry(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    client.post("/api/services", json={"name": "temp-svc", "port": 1})
    resp = client.delete("/api/services/temp-svc")
    assert resp.status_code == 200

    names = {svc["name"] for svc in client.get("/api/services").json()}
    assert "temp-svc" not in names


def test_delete_without_token_from_remote_is_401(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    local = _localhost_client(app)
    remote = _remote_client(app)

    local.post("/api/services", json={"name": "temp-svc", "port": 1})
    resp = remote.delete("/api/services/temp-svc")
    assert resp.status_code == 401

    # still present
    names = {svc["name"] for svc in local.get("/api/services").json()}
    assert "temp-svc" in names


def test_delete_static_service_is_403(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    resp = client.delete("/api/services/Resolve")
    assert resp.status_code == 403

    # static entry unaffected
    names = {svc["name"] for svc in client.get("/api/services").json()}
    assert "Resolve" in names


def test_delete_unknown_dynamic_name_is_404(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    resp = client.delete("/api/services/never-existed")
    assert resp.status_code == 404


# --- POST /api/services/{name}/heartbeat --------------------------------------


def test_heartbeat_refreshes_ttl_entry(tmp_path):
    config = _make_config(tmp_path)
    clock = {"t": 1000.0}

    app = create_app(config, checker=_all_down, time_fn=lambda: clock["t"])
    client = _localhost_client(app)

    client.post("/api/services", json={"name": "ttl-svc", "port": 1, "ttl": 10})

    clock["t"] += 8
    resp = client.post("/api/services/ttl-svc/heartbeat")
    assert resp.status_code == 200

    clock["t"] += 8  # 16s since registration, but only 8s since heartbeat
    names = {svc["name"] for svc in client.get("/api/services").json()}
    assert "ttl-svc" in names


def test_ttl_entry_pruned_after_expiry_without_heartbeat(tmp_path):
    config = _make_config(tmp_path)
    clock = {"t": 1000.0}
    app = create_app(config, checker=_all_down, time_fn=lambda: clock["t"])
    client = _localhost_client(app)

    client.post("/api/services", json={"name": "ttl-svc", "port": 1, "ttl": 10})
    clock["t"] += 20  # well past ttl, no heartbeat sent

    names = {svc["name"] for svc in client.get("/api/services").json()}
    assert "ttl-svc" not in names


def test_persistent_entry_survives_without_heartbeat(tmp_path):
    config = _make_config(tmp_path)
    clock = {"t": 1000.0}
    app = create_app(config, checker=_all_down, time_fn=lambda: clock["t"])
    client = _localhost_client(app)

    client.post("/api/services", json={"name": "persist-svc", "port": 1})  # no ttl
    clock["t"] += 1_000_000

    names = {svc["name"] for svc in client.get("/api/services").json()}
    assert "persist-svc" in names


def test_heartbeat_static_name_is_403(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    resp = client.post("/api/services/Resolve/heartbeat")
    assert resp.status_code == 403


def test_heartbeat_unknown_dynamic_name_is_404(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    resp = client.post("/api/services/ghost/heartbeat")
    assert resp.status_code == 404


def test_heartbeat_without_token_from_remote_is_401(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    local = _localhost_client(app)
    remote = _remote_client(app)
    local.post("/api/services", json={"name": "ttl-svc", "port": 1, "ttl": 10})

    resp = remote.post("/api/services/ttl-svc/heartbeat")
    assert resp.status_code == 401


# --- require_write_token=true forces token even on localhost -----------------


def test_require_write_token_true_forces_token_even_on_localhost(tmp_path):
    config = _make_config(tmp_path, require_write_token=True)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    resp = client.post("/api/services", json={"name": "svc", "port": 1})
    assert resp.status_code == 401


def test_require_write_token_true_localhost_with_valid_token_succeeds(tmp_path):
    config = _make_config(tmp_path, require_write_token=True)
    token = issue_write_token(config.federation.state_dir)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    resp = client.post(
        "/api/services",
        json={"name": "svc", "port": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


# --- health priority integration (via /api/health) ----------------------------


def test_api_health_reports_up_for_ttl_entry_without_probing(tmp_path):
    def exploding_checker(url):
        raise AssertionError("must not be called for a fresh ttl entry")

    config = _make_config(tmp_path)
    app = create_app(config, checker=exploding_checker)
    client = _localhost_client(app)
    client.post("/api/services", json={"name": "ttl-svc", "port": 1, "ttl": 60})

    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["ttl-svc"] == "up"


def test_api_health_uses_health_url_stubbed_http_checker(tmp_path):
    config = _make_config(tmp_path)

    def http_checker_up(url):
        return url == "http://myservice/health"

    app = create_app(config, checker=_all_down, http_checker=http_checker_up)
    client = _localhost_client(app)
    client.post(
        "/api/services",
        json={"name": "http-svc", "port": 1, "health_url": "http://myservice/health"},
    )

    resp = client.get("/api/health")
    data = resp.json()
    assert data["http-svc"] == "up"
    assert data["Resolve"] == "down"  # static, tcp-checker stubbed to always-down


def test_api_health_falls_back_to_tcp_for_dynamic_entry_without_health_url(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_up)
    client = _localhost_client(app)
    client.post("/api/services", json={"name": "tcp-svc", "port": 1})

    resp = client.get("/api/health")
    assert resp.json()["tcp-svc"] == "up"


# --- federation: dynamic services flow through /api/services/local -----------


def test_dynamic_services_aggregate_across_peers(tmp_path):
    """A dynamic service registered on the local node must be visible to a
    peer's aggregation pull, exactly like a static one -- i.e. it appears
    in /api/services/local, which is what peer_fetcher targets."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    client.post("/api/services", json={"name": "shared-agent", "port": 1})

    local_view = client.get("/api/services/local").json()
    names = {svc["name"] for svc in local_view}
    assert "shared-agent" in names
    entry = next(s for s in local_view if s["name"] == "shared-agent")
    assert entry["origin"] == config.federation.name
    assert entry["source"] == "dynamic"


# --- dashboard HTML: add form, delete control, write-token input --------------


def test_index_html_contains_add_service_form(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    resp = client.get("/")
    html = resp.text
    assert 'id="add-service-form"' in html
    assert 'name="name"' in html
    assert 'name="port"' in html


def test_index_html_contains_write_token_input(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text
    assert 'id="write-token-input"' in html


def test_index_html_shows_delete_control_on_dynamic_entry_only(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    client.post("/api/services", json={"name": "dyn-svc", "port": 1})

    html = client.get("/").text
    assert 'data-remove-name="dyn-svc"' in html
    # Static entry must show NO remove control.
    assert 'data-remove-name="Resolve"' not in html


def test_index_html_escapes_dynamic_service_name_xss(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    register_service(
        config.federation.state_dir,
        DynamicService(name="<script>alert(1)</script>", port=1),
    )
    html = client.get("/").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
