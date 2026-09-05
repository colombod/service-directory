"""Hermetic tests for the Settings API and UI surface (Tasks 1-4).

Task 1 -- Read-only settings surface: identity + federation status.
Task 2 -- Trusted peers: list and remove from the UI.
Task 3 -- Pairing from the UI (both directions).
Task 4 -- Agent-facing API parity.

No real network, no real peer. Peer HTTP calls stubbed via the injectable
pair_with_peer_fn seam. Clock not needed here (pairing codes use
app.state.pairing_store which is in-memory). filterwarnings=error::DeprecationWarning
is respected (no deprecated API usage).
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
from service_directory.trust_store import PeerRecord, load_peers, upsert_peer
from service_directory.write_token import issue_write_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    tmp_path,
    *,
    enabled: bool = True,
    name: str = "local-node",
    description: str = "Test node",
    role: str = "primary",
    base_url: str = "http://10.0.0.1:80",
    require_write_token: bool = False,
) -> RegistryConfig:
    return RegistryConfig(
        host_addresses=[
            HostAddress(label="Tailnet", host="100.1.2.3"),
            HostAddress(label="LAN", host="10.0.0.1"),
        ],
        services=[Service(name="Resolve", port=8080, path="/", description="d")],
        federation=FederationConfig(
            enabled=enabled,
            name=name,
            description=description,
            role=role,
            base_url=base_url,
            state_dir=str(tmp_path / "state"),
            require_write_token=require_write_token,
        ),
    )


def _localhost_client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=True, client=("127.0.0.1", 12345))


def _remote_client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=True, client=("203.0.113.9", 12345))


def _all_down(url: str) -> bool:
    return False


# ---------------------------------------------------------------------------
# Task 1 -- GET /api/settings: read-only identity + federation status
# ---------------------------------------------------------------------------


class TestApiSettings:
    def test_returns_identity_fields_federation_enabled(self, tmp_path):
        config = _make_config(tmp_path, enabled=True, name="my-node",
                               description="My description", role="hub",
                               base_url="http://hub.example.com")
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)

        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "my-node"
        assert data["description"] == "My description"
        assert data["role"] == "hub"
        assert data["base_url"] == "http://hub.example.com"
        assert data["federation_enabled"] is True
        # host_addresses from config
        addrs = {a["label"]: a["host"] for a in data["host_addresses"]}
        assert addrs["Tailnet"] == "100.1.2.3"
        assert addrs["LAN"] == "10.0.0.1"

    def test_returns_identity_fields_federation_disabled(self, tmp_path):
        config = _make_config(tmp_path, enabled=False, name="standalone")
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)

        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "standalone"
        assert data["federation_enabled"] is False

    def test_values_not_hardcoded_differ_per_config(self, tmp_path):
        """Two different configs produce different settings -- values come from
        live config, not hardcoded."""
        config_a = _make_config(tmp_path / "a", name="node-alpha", enabled=True)
        config_b = _make_config(tmp_path / "b", name="node-beta", enabled=False)
        app_a = create_app(config_a, checker=_all_down)
        app_b = create_app(config_b, checker=_all_down)

        data_a = _localhost_client(app_a).get("/api/settings").json()
        data_b = _localhost_client(app_b).get("/api/settings").json()

        assert data_a["name"] == "node-alpha"
        assert data_b["name"] == "node-beta"
        assert data_a["federation_enabled"] is True
        assert data_b["federation_enabled"] is False

    def test_settings_open_by_default_no_read_token(self, tmp_path):
        """Read access is open by default (no require_read_token)."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        # Remote client (no token) should still read
        resp = _remote_client(app).get("/api/settings")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Task 2 -- GET /api/federation/peers: list peers
# ---------------------------------------------------------------------------


class TestApiListPeers:
    def test_empty_peers(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)

        resp = client.get("/api/federation/peers")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    def test_lists_peers_with_name_url_device_id(self, tmp_path):
        config = _make_config(tmp_path)
        upsert_peer(
            config.federation.state_dir,
            PeerRecord(
                name="peer-alpha",
                device_id="dev-alpha",
                base_url="http://alpha.example.com",
                token="tok-alpha",
            ),
        )
        upsert_peer(
            config.federation.state_dir,
            PeerRecord(
                name="peer-beta",
                device_id="dev-beta",
                base_url="http://beta.example.com",
                token="tok-beta",
            ),
        )
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)

        resp = client.get("/api/federation/peers")
        assert resp.status_code == 200
        data = resp.json()
        by_name = {p["name"]: p for p in data}

        assert "peer-alpha" in by_name
        assert by_name["peer-alpha"]["base_url"] == "http://alpha.example.com"
        assert by_name["peer-alpha"]["device_id"] == "dev-alpha"
        assert "reachable" in by_name["peer-alpha"]

        assert "peer-beta" in by_name

    def test_no_token_in_peer_list_response(self, tmp_path):
        """Tokens are never exposed via the API."""
        config = _make_config(tmp_path)
        upsert_peer(
            config.federation.state_dir,
            PeerRecord(
                name="peer-x",
                device_id="dev-x",
                base_url="http://x.example.com",
                token="super-secret-token",
            ),
        )
        app = create_app(config, checker=_all_down)
        resp = _localhost_client(app).get("/api/federation/peers")
        data = resp.json()
        for peer in data:
            assert "token" not in peer
        # Also check raw response text
        assert "super-secret-token" not in resp.text


# ---------------------------------------------------------------------------
# Task 2 -- DELETE /api/federation/peers/{name}: remove peer
# ---------------------------------------------------------------------------


class TestApiRemovePeer:
    def test_authorised_remove_succeeds(self, tmp_path):
        config = _make_config(tmp_path, require_write_token=True)
        state_dir = config.federation.state_dir
        token = issue_write_token(state_dir)
        upsert_peer(
            state_dir,
            PeerRecord(name="doomed", device_id="d", base_url="http://d", token="t"),
        )
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)

        resp = client.delete(
            "/api/federation/peers/doomed",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["removed"] == "doomed"

        # Peer is gone from trust store
        remaining = load_peers(state_dir)
        assert not any(p.name == "doomed" for p in remaining)

    def test_unauthorised_remove_refused(self, tmp_path):
        """A missing/invalid write token must refuse removal (401)."""
        config = _make_config(tmp_path, require_write_token=True)
        state_dir = config.federation.state_dir
        issue_write_token(state_dir)  # set a token
        upsert_peer(
            state_dir,
            PeerRecord(name="alive", device_id="d", base_url="http://d", token="t"),
        )
        app = create_app(config, checker=_all_down)
        # Remote client, no auth header
        client = _remote_client(app)

        resp = client.delete("/api/federation/peers/alive")
        assert resp.status_code == 401

        # Peer must still be present
        remaining = load_peers(state_dir)
        assert any(p.name == "alive" for p in remaining)

    def test_remove_nonexistent_peer_returns_404(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)

        resp = client.delete("/api/federation/peers/no-such-peer")
        assert resp.status_code == 404

    def test_localhost_bypass_allows_remove_without_token(self, tmp_path):
        """Localhost bypass still works for remove when require_write_token=False."""
        config = _make_config(tmp_path, require_write_token=False)
        state_dir = config.federation.state_dir
        upsert_peer(
            state_dir,
            PeerRecord(name="target", device_id="d", base_url="http://d", token="t"),
        )
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)

        resp = client.delete("/api/federation/peers/target")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Task 3 -- POST /api/federation/ui-pairing-code: issue code (write-token auth)
# ---------------------------------------------------------------------------


class TestApiUiPairingCode:
    def test_issue_code_requires_auth_from_remote(self, tmp_path):
        """Remote caller without write token must be refused."""
        config = _make_config(tmp_path, require_write_token=True)
        state_dir = config.federation.state_dir
        issue_write_token(state_dir)
        app = create_app(config, checker=_all_down)
        client = _remote_client(app)

        resp = client.post("/api/federation/ui-pairing-code")
        assert resp.status_code == 401

    def test_issue_code_with_valid_write_token(self, tmp_path):
        """A valid write token returns a code + ttl."""
        config = _make_config(tmp_path, require_write_token=True)
        state_dir = config.federation.state_dir
        token = issue_write_token(state_dir)
        app = create_app(config, checker=_all_down)
        client = _remote_client(app)

        resp = client.post(
            "/api/federation/ui-pairing-code",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "code" in data
        assert isinstance(data["code"], str) and len(data["code"]) > 0
        assert "ttl_seconds" in data
        assert data["ttl_seconds"] > 0

    def test_issue_code_localhost_bypass(self, tmp_path):
        """Localhost bypass allows code issuance without explicit token."""
        config = _make_config(tmp_path, require_write_token=False)
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)

        resp = client.post("/api/federation/ui-pairing-code")
        assert resp.status_code == 200
        data = resp.json()
        assert "code" in data

    def test_code_is_not_a_secret(self, tmp_path):
        """The pairing code itself MAY be displayed (that is its purpose)."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)

        resp = client.post("/api/federation/ui-pairing-code")
        assert resp.status_code == 200
        # Code is present and non-empty (it's meant to be shown)
        assert resp.json()["code"]


# ---------------------------------------------------------------------------
# Task 3 -- POST /api/federation/pair-with-peer: pair with peer (stubbed)
# ---------------------------------------------------------------------------


class TestApiPairWithPeer:
    def _stub_pair_fn(self, peer_data: dict):
        """Returns a stub pair_with_peer_fn that simulates a successful peer."""
        def _fn(url: str, payload: dict) -> dict:
            return peer_data
        return _fn

    def test_pair_with_peer_requires_write_token(self, tmp_path):
        """Remote caller without write token must be refused."""
        config = _make_config(tmp_path, require_write_token=True)
        state_dir = config.federation.state_dir
        issue_write_token(state_dir)
        app = create_app(config, checker=_all_down)
        client = _remote_client(app)

        resp = client.post(
            "/api/federation/pair-with-peer",
            json={"url": "http://peer.example.com", "code": "abc123"},
        )
        assert resp.status_code == 401

    def test_pair_with_peer_succeeds_and_adds_peer(self, tmp_path):
        """Successful pairing adds the peer to the trust store."""
        config = _make_config(tmp_path)
        state_dir = config.federation.state_dir
        peer_response = {
            "name": "new-peer",
            "device_id": "dev-new",
            "base_url": "http://new-peer.example.com",
            "token": "per-peer-secret-token",
        }
        app = create_app(
            config,
            checker=_all_down,
            pair_with_peer_fn=self._stub_pair_fn(peer_response),
        )
        client = _localhost_client(app)

        resp = client.post(
            "/api/federation/pair-with-peer",
            json={"url": "http://new-peer.example.com", "code": "valid-code"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new-peer"
        assert data["base_url"] == "http://new-peer.example.com"
        # Token must NOT be returned to the caller
        assert "token" not in data

        # Peer is now in trust store
        peers = load_peers(state_dir)
        assert any(p.name == "new-peer" for p in peers)

    def test_pair_with_peer_token_not_in_response(self, tmp_path):
        """The per-peer token must never be echoed back in the API response."""
        config = _make_config(tmp_path)
        peer_response = {
            "name": "secret-peer",
            "device_id": "dev-s",
            "base_url": "http://s.example.com",
            "token": "super-secret-per-peer-token",
        }
        app = create_app(
            config,
            checker=_all_down,
            pair_with_peer_fn=self._stub_pair_fn(peer_response),
        )
        client = _localhost_client(app)

        resp = client.post(
            "/api/federation/pair-with-peer",
            json={"url": "http://s.example.com", "code": "code"},
        )
        assert resp.status_code == 200
        assert "super-secret-per-peer-token" not in resp.text

    def test_pair_with_peer_failure_surfaces_real_error(self, tmp_path):
        """A failing peer call must return 502 with the real error detail."""
        config = _make_config(tmp_path)

        def _failing_fn(url: str, payload: dict) -> dict:
            raise ConnectionError("simulated peer unreachable")

        app = create_app(config, checker=_all_down, pair_with_peer_fn=_failing_fn)
        client = _localhost_client(app)

        resp = client.post(
            "/api/federation/pair-with-peer",
            json={"url": "http://unreachable.example.com", "code": "code"},
        )
        assert resp.status_code == 502
        detail = resp.json()["detail"]
        # Must surface the real error, not a generic message
        assert "simulated peer unreachable" in detail

    def test_pair_with_peer_bad_code_surfaces_error(self, tmp_path):
        """A bad code (rejected by peer) must surface the real error."""
        config = _make_config(tmp_path)

        def _bad_code_fn(url: str, payload: dict) -> dict:
            raise ValueError("invalid or expired pairing code")

        app = create_app(config, checker=_all_down, pair_with_peer_fn=_bad_code_fn)
        client = _localhost_client(app)

        resp = client.post(
            "/api/federation/pair-with-peer",
            json={"url": "http://peer.example.com", "code": "bad-code"},
        )
        assert resp.status_code == 502
        assert "invalid or expired pairing code" in resp.json()["detail"]

    def test_pair_with_peer_localhost_bypass(self, tmp_path):
        """Localhost bypass allows pairing without explicit write token."""
        config = _make_config(tmp_path, require_write_token=False)
        peer_response = {
            "name": "peer-bypass",
            "device_id": "dev-bypass",
            "base_url": "http://bypass.example.com",
            "token": "tok-bypass",
        }
        app = create_app(
            config,
            checker=_all_down,
            pair_with_peer_fn=self._stub_pair_fn(peer_response),
        )
        client = _localhost_client(app)

        resp = client.post(
            "/api/federation/pair-with-peer",
            json={"url": "http://bypass.example.com", "code": "code"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Task 4 -- API parity: every action reachable as a JSON endpoint
# ---------------------------------------------------------------------------


class TestApiFederationParity:
    """Every action available in the UI is also reachable via a documented
    JSON endpoint. Reads follow existing read-access rules; mutations require
    the existing write token."""

    def test_read_settings_endpoint_exists(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        resp = _localhost_client(app).get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        # All expected fields present
        for field in ("name", "federation_enabled", "host_addresses"):
            assert field in data, f"missing field: {field}"

    def test_list_peers_endpoint_exists(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        resp = _localhost_client(app).get("/api/federation/peers")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_remove_peer_endpoint_requires_write_token(self, tmp_path):
        """Mutating endpoint must refuse without auth."""
        config = _make_config(tmp_path, require_write_token=True)
        state_dir = config.federation.state_dir
        issue_write_token(state_dir)
        upsert_peer(
            state_dir,
            PeerRecord(name="p", device_id="d", base_url="http://p", token="t"),
        )
        app = create_app(config, checker=_all_down)
        resp = _remote_client(app).delete("/api/federation/peers/p")
        assert resp.status_code == 401

    def test_issue_pairing_code_endpoint_requires_write_token(self, tmp_path):
        """Mutating endpoint must refuse without auth."""
        config = _make_config(tmp_path, require_write_token=True)
        state_dir = config.federation.state_dir
        issue_write_token(state_dir)
        app = create_app(config, checker=_all_down)
        resp = _remote_client(app).post("/api/federation/ui-pairing-code")
        assert resp.status_code == 401

    def test_pair_with_peer_endpoint_requires_write_token(self, tmp_path):
        """Mutating endpoint must refuse without auth."""
        config = _make_config(tmp_path, require_write_token=True)
        state_dir = config.federation.state_dir
        issue_write_token(state_dir)
        app = create_app(config, checker=_all_down)
        resp = _remote_client(app).post(
            "/api/federation/pair-with-peer",
            json={"url": "http://peer", "code": "code"},
        )
        assert resp.status_code == 401

    def test_ui_cannot_do_more_than_api(self, tmp_path):
        """Smoke test: every action the UI performs has a corresponding
        API endpoint that is tested above. The UI uses these endpoints
        via fetch() calls, so parity is structural."""
        # This is verified by the existence of all the endpoints above.
        # Additionally, verify the dashboard HTML references the endpoints.
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        resp = _localhost_client(app).get("/")
        assert resp.status_code == 200
        html = resp.text
        assert "/api/settings" in html
        assert "/api/federation/peers" in html
        assert "/api/federation/ui-pairing-code" in html
        assert "/api/federation/pair-with-peer" in html


# ---------------------------------------------------------------------------
# Task 1 -- Dashboard HTML: Settings surface discoverable
# ---------------------------------------------------------------------------


class TestDashboardSettingsSurface:
    def test_settings_button_present_in_html(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        resp = _localhost_client(app).get("/")
        assert resp.status_code == 200
        html = resp.text
        assert "settings-btn" in html
        assert "settings-overlay" in html

    def test_settings_panel_has_identity_section(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        resp = _localhost_client(app).get("/")
        html = resp.text
        assert "settings-identity-section" in html
        assert "settings-identity-content" in html

    def test_settings_panel_has_peers_section(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        resp = _localhost_client(app).get("/")
        html = resp.text
        assert "settings-peers-section" in html
        assert "settings-peers-content" in html

    def test_settings_panel_has_pairing_section(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        resp = _localhost_client(app).get("/")
        html = resp.text
        assert "settings-pairing-section" in html
        assert "settings-issue-code-btn" in html
        assert "settings-pair-btn" in html

    def test_write_token_input_id_preserved(self, tmp_path):
        """The existing write-token-input id must be preserved (existing tests
        depend on it)."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        resp = _localhost_client(app).get("/")
        html = resp.text
        assert 'id="write-token-input"' in html

    def test_existing_hooks_preserved(self, tmp_path):
        """All hooks existing tests depend on must be present."""
        config = _make_config(tmp_path, enabled=True)
        app = create_app(config, checker=_all_down)
        resp = _localhost_client(app).get("/")
        html = resp.text
        for hook in [
            'id="service-filter"',
            "node-group",
            "data-origin",
            "svc-table",
            "health-pill",
            "health-dot",
            'id="add-service-form"',
            'id="write-token-input"',
            "remove-service",
            "service-name service-open",
            "/api/embed-probe",
            "/api/view-proxy",
        ]:
            assert hook in html, f"missing hook: {hook!r}"

    def test_no_secret_rendered_in_html(self, tmp_path):
        """Write tokens and peer tokens must never appear in the HTML."""
        config = _make_config(tmp_path, require_write_token=True)
        state_dir = config.federation.state_dir
        write_tok = issue_write_token(state_dir)
        upsert_peer(
            state_dir,
            PeerRecord(
                name="peer-x",
                device_id="dev-x",
                base_url="http://x.example.com",
                token="peer-secret-xyz",
            ),
        )
        app = create_app(config, checker=_all_down)
        # Use localhost to bypass read token requirement
        resp = _localhost_client(app).get("/")
        html = resp.text
        assert write_tok not in html
        assert "peer-secret-xyz" not in html
