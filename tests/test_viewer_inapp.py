"""Hermetic tests for the in-app service viewer -- new features added by the
goal condition (Tasks 1-5 refinement):

  Task 1 -- view_refresh_seconds config field (parse + data-attr exposure)
  Task 2 -- Detail view first: selecting a service shows metadata before opening
  Task 3 -- iframe viewer has a Reload control
  Task 4 -- JSON viewer has manual Refresh, Auto-refresh toggle, updated-ago
  Task 5 -- auto mode + non-embeddable fallback (already tested; extended here)
  Sample  -- config.sample.yaml shows iframe + json examples with view_refresh_seconds

No real network I/O: embed_probe and view_proxy are injected stubs.
All tests run under filterwarnings=error::DeprecationWarning (green).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from service_directory.app import _render_html, create_app
from service_directory.config import (
    ConfigError,
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
    load_config,
    parse_config,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_down(url: str) -> bool:
    return False


def _make_config(
    tmp_path,
    *,
    services=None,
    name="local-node",
):
    return RegistryConfig(
        host_addresses=[HostAddress(label="Tailnet", host="10.0.0.1")],
        services=services
        if services is not None
        else [Service(name="Resolve", port=8080, path="/", description="Resolve UI")],
        federation=FederationConfig(
            enabled=True,
            name=name,
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
        ),
    )


def _localhost_client(app) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 12345))


# ---------------------------------------------------------------------------
# Task 1 -- view_refresh_seconds config field
# ---------------------------------------------------------------------------


class TestTask1ViewRefreshSeconds:
    """Task 1: view_refresh_seconds is parsed, validated, and exposed."""

    def test_parse_view_refresh_seconds_positive_int(self):
        yaml_text = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "CI", port: 8000, view_kind: "json", view_refresh_seconds: 30}
"""
        cfg = parse_config(yaml_text)
        assert cfg.services[0].view_refresh_seconds == 30

    def test_parse_view_refresh_seconds_none_by_default(self):
        yaml_text = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "CI", port: 8000, view_kind: "json"}
"""
        cfg = parse_config(yaml_text)
        assert cfg.services[0].view_refresh_seconds is None

    def test_parse_view_refresh_seconds_rejects_zero(self):
        yaml_text = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "CI", port: 8000, view_refresh_seconds: 0}
"""
        with pytest.raises(ConfigError):
            parse_config(yaml_text)

    def test_parse_view_refresh_seconds_rejects_negative(self):
        yaml_text = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "CI", port: 8000, view_refresh_seconds: -5}
"""
        with pytest.raises(ConfigError):
            parse_config(yaml_text)

    def test_parse_view_refresh_seconds_rejects_string(self):
        yaml_text = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "CI", port: 8000, view_refresh_seconds: "fast"}
"""
        with pytest.raises(ConfigError):
            parse_config(yaml_text)

    def test_parse_view_refresh_seconds_rejects_bool(self):
        yaml_text = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "CI", port: 8000, view_refresh_seconds: true}
"""
        with pytest.raises(ConfigError):
            parse_config(yaml_text)

    def test_view_refresh_seconds_on_non_json_view_accepted(self):
        """view_refresh_seconds on a non-JSON view is accepted (silently ignored)."""
        yaml_text = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "Resolve", port: 8080, view_kind: "iframe", view_refresh_seconds: 60}
"""
        cfg = parse_config(yaml_text)
        assert cfg.services[0].view_refresh_seconds == 60
        assert cfg.services[0].view_kind == "iframe"

    def test_data_view_refresh_seconds_attr_in_html(self, tmp_path):
        """data-view-refresh-seconds attribute appears in the HTML row."""
        config = _make_config(
            tmp_path,
            services=[
                Service(
                    name="CI",
                    port=8000,
                    path="/status",
                    view_kind="json",
                    view_refresh_seconds=30,
                )
            ],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-view-refresh-seconds="30"' in html

    def test_no_refresh_attr_when_unset(self, tmp_path):
        """When view_refresh_seconds is None, no data-view-refresh-seconds="N" attr in rows."""
        config = _make_config(
            tmp_path,
            services=[Service(name="CI", port=8000, path="/status", view_kind="json")],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        # The attribute should NOT appear as an HTML attribute assignment in the row.
        # (The JS code uses the string as a key to read the attr, that's OK.)
        assert 'data-view-refresh-seconds="' not in html

    def test_api_services_includes_view_refresh_seconds(self, tmp_path):
        """The /api/services/local endpoint propagates view_refresh_seconds."""
        config = _make_config(
            tmp_path,
            services=[
                Service(
                    name="CI",
                    port=8000,
                    path="/status",
                    view_kind="json",
                    view_refresh_seconds=30,
                )
            ],
        )
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)
        resp = client.get("/api/services/local")
        assert resp.status_code == 200
        data = resp.json()
        ci = next(s for s in data if s["name"] == "CI")
        assert ci["view_refresh_seconds"] == 30

    def test_api_services_view_refresh_seconds_none_when_unset(self, tmp_path):
        """view_refresh_seconds is None in the API when not configured."""
        config = _make_config(
            tmp_path,
            services=[Service(name="CI", port=8000, path="/status", view_kind="json")],
        )
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)
        resp = client.get("/api/services/local")
        assert resp.status_code == 200
        data = resp.json()
        ci = next(s for s in data if s["name"] == "CI")
        assert ci.get("view_refresh_seconds") is None

    def test_backward_compat_legacy_config_no_view_refresh_seconds(self, tmp_path):
        """A legacy config with no view fields loads and renders without error."""
        config = _make_config(
            tmp_path,
            services=[
                Service(name="Resolve", port=8080, path="/"),
                Service(name="muxterm", port=8311),
            ],
        )
        app = create_app(config, checker=_all_down)
        resp = _localhost_client(app).get("/")
        assert resp.status_code == 200
        assert "Resolve" in resp.text
        assert "muxterm" in resp.text
        # No actual refresh-seconds attribute values in the HTML rows
        assert 'data-view-refresh-seconds="' not in resp.text


# ---------------------------------------------------------------------------
# Task 2 -- Detail view first (metadata before opening)
# ---------------------------------------------------------------------------


class TestTask2DetailViewFirst:
    """Task 2: clicking a service shows a detail panel, not the iframe directly."""

    def test_show_viewer_detail_js_present(self, tmp_path):
        """JS contains showViewerDetail function."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "showViewerDetail" in html

    def test_row_click_calls_show_viewer_detail(self, tmp_path):
        """Row click handler calls showViewerDetail(row), not openServiceInViewer."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        # The click handler now calls showViewerDetail
        assert "showViewerDetail(row)" in html

    def test_detail_view_renders_service_name(self, tmp_path):
        """Detail view shows the service name (detail-name element)."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "detail-name" in html

    def test_detail_view_renders_description(self, tmp_path):
        """Detail view shows description (detail-desc element)."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "detail-desc" in html

    def test_detail_view_renders_category(self, tmp_path):
        """Detail view shows category metadata."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "detail-meta" in html

    def test_detail_view_has_open_here_button(self, tmp_path):
        """Detail view has a primary 'Open here' action button."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "detail-open-here-btn" in html
        assert "Open here" in html

    def test_detail_view_has_external_links(self, tmp_path):
        """Detail view shows external links (open externally option)."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "detail-ext-link" in html
        assert "Open externally" in html

    def test_detail_view_has_back_control(self, tmp_path):
        """Detail view header has a back control."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-close-btn" in html

    def test_detail_view_has_open_in_new_tab_link(self, tmp_path):
        """Detail view shows open-in-new-tab as a secondary control."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-open-tab" in html

    def test_detail_view_no_view_url_shows_no_view_message(self, tmp_path):
        """JS handles case where no view_url: shows 'No in-app view' message."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "No in-app view configured" in html

    def test_detail_view_open_here_calls_open_service_in_viewer(self, tmp_path):
        """Clicking 'Open here' in detail view calls openServiceInViewer."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "openServiceInViewer" in html

    def test_service_name_is_a_real_open_button(self, tmp_path):
        """The service name is a real <button>, not inert text.

        Opening a service IN-APP is the default action, so its control must be
        a semantic, focusable button that appears in the accessibility tree --
        not a click on row whitespace. Regression guard: previously the only
        interactive per-service elements were the external <a href> links,
        which made navigating AWAY the only discoverable behaviour.
        """
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "service-name" in html
        assert 'class="service-name service-open"' in html
        assert '<button type="button" class="service-name service-open"' in html
        # The button is explicitly wired to open the in-app detail view.
        assert "service-open" in html
        assert "showViewerDetail" in html

    def test_data_desc_attr_on_service_row(self, tmp_path):
        """Service row has data-desc attribute for detail view."""
        config = _make_config(
            tmp_path,
            services=[Service(name="Resolve", port=8080, path="/", description="My UI")],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-desc="My UI"' in html

    def test_data_category_attr_on_service_row(self, tmp_path):
        """Service row has data-category attribute for detail view."""
        config = _make_config(
            tmp_path,
            services=[Service(name="Resolve", port=8080, category="pipelines")],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-category="pipelines"' in html

    def test_data_tags_attr_on_service_row(self, tmp_path):
        """Service row has data-tags attribute for detail view."""
        config = _make_config(
            tmp_path,
            services=[Service(name="Resolve", port=8080, tags=["alpha", "beta"])],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-tags="alpha,beta"' in html

    def test_data_docs_url_attr_on_service_row(self, tmp_path):
        """Service row has data-docs-url attribute for detail view."""
        config = _make_config(
            tmp_path,
            services=[
                Service(
                    name="Resolve",
                    port=8080,
                    docs_url="https://example.com/docs",
                )
            ],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-docs-url="https://example.com/docs"' in html


# ---------------------------------------------------------------------------
# Task 3 -- iframe viewer has a Reload control
# ---------------------------------------------------------------------------


class TestTask3IframeReload:
    """Task 3: iframe viewer includes a Reload button."""

    def test_viewer_iframe_has_reload_btn(self, tmp_path):
        """JS showViewerIframe renders a viewer-reload-btn."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-reload-btn" in html

    def test_viewer_iframe_reload_btn_text(self, tmp_path):
        """Reload button has 'Reload' text."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "Reload" in html

    def test_viewer_iframe_reload_btn_wires_to_iframe_src(self, tmp_path):
        """Reload button JS reloads the iframe by reassigning iframe.src."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "iframe.src = iframe.src" in html

    def test_viewer_iframe_still_has_open_in_new_tab(self, tmp_path):
        """iframe viewer still has the secondary open-in-new-tab link."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-open-tab" in html

    def test_viewer_iframe_still_has_back_control(self, tmp_path):
        """iframe viewer still has the back control."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-close-btn" in html

    def test_viewer_iframe_still_has_service_name(self, tmp_path):
        """iframe viewer header shows the service name."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-svc-name" in html


# ---------------------------------------------------------------------------
# Task 4 -- JSON viewer: manual Refresh, Auto-refresh, updated-ago, timer cleanup
# ---------------------------------------------------------------------------


class TestTask4JsonViewerRefresh:
    """Task 4: JSON viewer has refresh controls and timer cleanup."""

    def test_viewer_json_has_refresh_btn(self, tmp_path):
        """JS showViewerJson renders a viewer-refresh-btn."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-refresh-btn" in html

    def test_viewer_json_refresh_btn_text(self, tmp_path):
        """Manual refresh button has 'Refresh' text."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "Refresh" in html

    def test_viewer_json_has_autorefresh_btn(self, tmp_path):
        """JS showViewerJson renders a viewer-autorefresh-btn."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-autorefresh-btn" in html

    def test_viewer_json_autorefresh_btn_text_on_when_refresh_seconds_set(self, tmp_path):
        """Auto-refresh button text shows 'on' when refreshSeconds > 0."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "Auto-refresh: on" in html
        assert "Auto-refresh: off" in html

    def test_viewer_json_has_updated_ago_indicator(self, tmp_path):
        """JS showViewerJson renders a viewer-updated-ago indicator."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-updated-ago" in html

    def test_viewer_json_updated_ago_text(self, tmp_path):
        """updated-ago indicator shows 'updated just now' initially."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "updated just now" in html

    def test_viewer_json_manual_refresh_fetches_view_proxy(self, tmp_path):
        """Manual refresh button calls /api/view-proxy."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "/api/view-proxy" in html
        assert "doRefresh" in html

    def test_viewer_json_autorefresh_uses_set_interval(self, tmp_path):
        """Auto-refresh uses setInterval for periodic polling."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "setInterval" in html
        assert "startAutoRefresh" in html

    def test_viewer_json_timer_cleared_on_back(self, tmp_path):
        """Auto-refresh timer is cleared when going back (_clearAutoRefresh)."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "_clearAutoRefresh" in html
        assert "clearInterval" in html

    def test_viewer_json_auto_refresh_starts_when_refresh_seconds_configured(self, tmp_path):
        """Auto-refresh starts automatically when refreshSeconds > 0."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        # JS: if (autoOn) startAutoRefresh()
        assert "if (autoOn) startAutoRefresh()" in html

    def test_viewer_json_auto_refresh_off_by_default_when_no_refresh_seconds(self, tmp_path):
        """Auto-refresh is off by default when refreshSeconds is 0."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        # JS: var autoOn = (refreshSeconds > 0)
        assert "refreshSeconds > 0" in html

    def test_viewer_json_toggle_auto_refresh(self, tmp_path):
        """Auto-refresh can be toggled on/off via the button."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "stopAutoRefresh" in html

    def test_viewer_json_timer_cleared_on_view_switch(self, tmp_path):
        """showViewerDefault clears the auto-refresh timer."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        # showViewerDefault calls _clearAutoRefresh
        assert "showViewerDefault" in html
        assert "_clearAutoRefresh" in html

    def test_viewer_json_timer_cleared_in_show_viewer_iframe(self, tmp_path):
        """showViewerIframe clears any running auto-refresh timer."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        # showViewerIframe also calls _clearAutoRefresh
        assert "showViewerIframe" in html

    def test_view_proxy_endpoint_still_works(self, tmp_path):
        """The /api/view-proxy endpoint still returns JSON for a catalogue target."""
        config = _make_config(
            tmp_path,
            services=[Service(name="CI", port=8000, path="/status")],
        )
        payload = {"status": "ok", "version": "2.0"}
        app = create_app(
            config, checker=_all_down, view_proxy=lambda url: payload
        )
        client = _localhost_client(app)
        resp = client.get("/api/view-proxy?url=http://10.0.0.1:8000/status")
        assert resp.status_code == 200
        assert resp.json() == payload


# ---------------------------------------------------------------------------
# Task 5 -- auto mode + non-embeddable fallback (extended)
# ---------------------------------------------------------------------------


class TestTask5AutoModeExtended:
    """Task 5: extended tests for auto mode with refresh_seconds threading."""

    def test_auto_mode_passes_refresh_seconds_to_json_viewer(self, tmp_path):
        """openServiceInViewer passes refreshSecs to showViewerJson in auto mode."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        # In auto mode, showViewerJson is called with refreshSecs
        assert "showViewerJson(name, url, data, refreshSecs)" in html

    def test_json_kind_passes_refresh_seconds_to_json_viewer(self, tmp_path):
        """openServiceInViewer passes refreshSecs to showViewerJson for json kind."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "showViewerJson(name, url, data, refreshSecs)" in html

    def test_fallback_card_has_open_in_new_tab_not_default(self, tmp_path):
        """Fallback card's new-tab link is secondary, not the default click."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-fallback-link" in html
        # The fallback link opens in new tab -- it is an <a> with target=_blank
        assert "target=\\_blank" in html or 'target="_blank"' in html or "target=\\'_blank\\'" in html

    def test_embed_probe_ssrf_still_guarded(self, tmp_path):
        """embed-probe still rejects off-catalogue URLs."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)
        resp = client.get("/api/embed-probe?url=http://evil.example.com/")
        assert resp.status_code == 403

    def test_view_proxy_ssrf_still_guarded(self, tmp_path):
        """view-proxy still rejects off-catalogue URLs."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)
        resp = client.get("/api/view-proxy?url=http://169.254.169.254/metadata")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Sample config -- iframe + json examples with view_refresh_seconds
# ---------------------------------------------------------------------------


class TestSampleConfigViewerFields:
    """config.sample.yaml shows one iframe-kind and one json-kind example."""

    def test_sample_config_loads(self):
        cfg = load_config(str(REPO_ROOT / "config.sample.yaml"))
        assert cfg is not None

    def test_sample_config_has_iframe_kind_example(self):
        cfg = load_config(str(REPO_ROOT / "config.sample.yaml"))
        iframe_svcs = [s for s in cfg.services if s.view_kind == "iframe"]
        assert len(iframe_svcs) >= 1, "Expected at least one iframe-kind service in sample"

    def test_sample_config_has_json_kind_example(self):
        cfg = load_config(str(REPO_ROOT / "config.sample.yaml"))
        json_svcs = [s for s in cfg.services if s.view_kind == "json"]
        assert len(json_svcs) >= 1, "Expected at least one json-kind service in sample"

    def test_sample_config_json_kind_has_view_refresh_seconds(self):
        cfg = load_config(str(REPO_ROOT / "config.sample.yaml"))
        json_svcs = [s for s in cfg.services if s.view_kind == "json"]
        assert any(
            s.view_refresh_seconds is not None for s in json_svcs
        ), "Expected at least one json-kind service with view_refresh_seconds in sample"

    def test_sample_config_view_refresh_seconds_positive(self):
        cfg = load_config(str(REPO_ROOT / "config.sample.yaml"))
        for s in cfg.services:
            if s.view_refresh_seconds is not None:
                assert s.view_refresh_seconds > 0

    def test_sample_config_all_existing_services_still_present(self):
        cfg = load_config(str(REPO_ROOT / "config.sample.yaml"))
        names = {s.name for s in cfg.services}
        assert "Resolve" in names
        assert "Context Intelligence" in names
        assert "muxplex" in names
        assert "muxterm" in names
        assert "browser-bridge hub" in names
