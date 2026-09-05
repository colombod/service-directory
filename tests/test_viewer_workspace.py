"""Hermetic tests for the embedded service viewer + multi-node workspace UI.

Covers Tasks 1-5 of the goal condition:
  Task 1 -- Two-pane layout with collapsible sidebar
  Task 2 -- Open a service HTML UI embedded in the viewer (iframe)
  Task 3 -- Graceful fallback for services that refuse framing
  Task 4 -- Rendered JSON view for JSON endpoints
  Task 5 -- Optional per-service view configuration (view_url / view_kind)

No real network I/O: embed_probe and view_proxy are injected stubs.
All tests run under filterwarnings=error::DeprecationWarning (green).
"""

from __future__ import annotations

import html.parser

import pytest
from fastapi.testclient import TestClient
from service_directory.app import _render_html, create_app
from service_directory.config import (
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
)


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
# Task 1 -- Two-pane layout with collapsible sidebar
# ---------------------------------------------------------------------------


class TestTask1TwoPaneLayout:
    """Task 1 acceptance: sidebar + viewer pane, collapse control, filter."""

    def test_sidebar_element_present(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'id="sidebar"' in html

    def test_viewer_element_present(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'id="viewer"' in html

    def test_sidebar_collapse_button_present(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'id="sidebar-collapse-btn"' in html

    def test_sidebar_collapse_button_aria_expanded(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'aria-expanded="true"' in html

    def test_sidebar_data_collapsed_attribute(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-collapsed="false"' in html

    def test_collapse_toggle_js_present(self, tmp_path):
        """JS must reference sidebar-collapse-btn and data-collapsed."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "sidebar-collapse-btn" in html
        assert "data-collapsed" in html

    def test_services_grouped_by_origin_in_sidebar(self, tmp_path):
        """Services are grouped under node-group sections in the sidebar."""
        config = _make_config(tmp_path, name="node-alpha")
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert '<section class="node-group"' in html
        assert 'data-origin="node-alpha"' in html

    def test_sidebar_contains_service_rows(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'class="service"' in html
        assert 'data-name="Resolve"' in html

    def test_filter_still_filters_service_list(self, tmp_path):
        """The existing filter semantics JS is still present."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "applyFilter" in html
        assert "section.style.display = visibleCount > 0 ? '' : 'none';" in html

    def test_service_filter_input_present(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'id="service-filter"' in html

    def test_default_viewer_shows_registration_panel(self, tmp_path):
        """Viewer default state shows the registration panel (catalogue info)."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'id="add-service-form"' in html
        assert 'id="write-token-input"' in html

    def test_empty_state_renders_in_sidebar(self, tmp_path):
        """_render_html with empty services still renders the sidebar structure."""
        html = _render_html([], node_info=[{"name": "local-node", "description": None}])
        assert 'id="sidebar"' in html
        assert 'id="viewer"' in html
        assert "empty-state" in html
        assert 'id="service-filter"' in html
        assert 'id="add-service-form"' in html

    def test_workspace_layout_css_present(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert ".workspace" in html
        assert "#sidebar" in html
        assert "#viewer" in html

    def test_all_existing_hooks_still_present(self, tmp_path):
        """Every hook the existing tests depend on is still present."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'id="service-filter"' in html
        assert '<section class="node-group"' in html
        assert 'data-origin=' in html
        assert 'class="service"' in html
        assert 'data-search="' in html
        assert 'data-name="Resolve"' in html
        assert "health-dot" in html
        assert "health-pill" in html
        assert 'id="add-service-form"' in html
        assert 'id="write-token-input"' in html

    def test_no_external_assets(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "<script src=" not in html
        assert "cdn." not in html.lower()


# ---------------------------------------------------------------------------
# Sidebar-collapse-is-not-a-trap: a re-open affordance must exist OUTSIDE
# #sidebar, since collapsing #sidebar (width:0/height:0; overflow:hidden)
# hides anything rendered inside it -- including the only collapse control.
# ---------------------------------------------------------------------------


_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


def _sidebar_span_contains(html_text: str, container_id: str, target_id: str) -> bool:
    """True if target_id's opening tag lies between container_id's open/close.

    Walks tokens with stdlib html.parser.HTMLParser (no bs4/lxml available
    in this project), tracking depth relative to the container element
    (identified by id=container_id). Returns True iff the target element's
    start tag is encountered while still inside that container -- i.e. it
    is a genuine DOM descendant, not just later in the raw markup.
    """

    class _SpanParser(html.parser.HTMLParser):
        _VOID_TAGS = _VOID_TAGS

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.container_tag = None
            self.depth_in_container = 0
            self.found_inside = False
            self._tag_stack: list[tuple[str, bool]] = []  # (tag, is_container)

        def handle_starttag(self, tag, attrs):
            attr_dict = dict(attrs)
            elem_id = attr_dict.get("id")
            is_container = elem_id == container_id
            if elem_id == target_id and self.depth_in_container > 0:
                self.found_inside = True
            if tag not in self._VOID_TAGS:
                self._tag_stack.append((tag, is_container))
                if is_container:
                    self.depth_in_container += 1

        def handle_startendtag(self, tag, attrs):
            attr_dict = dict(attrs)
            elem_id = attr_dict.get("id")
            if elem_id == target_id and self.depth_in_container > 0:
                self.found_inside = True

        def handle_endtag(self, tag):
            if self._tag_stack and tag in [t for t, _ in self._tag_stack]:
                while self._tag_stack and self._tag_stack[-1][0] != tag:
                    self._tag_stack.pop()
                if self._tag_stack:
                    _popped_tag, popped_is_container = self._tag_stack.pop()
                    if popped_is_container:
                        self.depth_in_container -= 1

    parser = _SpanParser()
    parser.feed(html_text)
    return parser.found_inside


class TestSidebarCollapseIsNotATrap:
    """A collapsed #sidebar (width:0/height:0;overflow:hidden) must not be
    the only place a re-open control lives -- otherwise collapsing it traps
    the user until a full page reload.
    """

    def test_reopen_control_exists_and_is_not_inside_sidebar(self, tmp_path):
        """A visible, labelled re-open affordance must live OUTSIDE #sidebar.

        This is the core regression test: against the pre-fix code, the only
        control capable of un-collapsing the sidebar (#sidebar-collapse-btn)
        is rendered INSIDE <nav id="sidebar">, which the CSS rule
        `#sidebar[data-collapsed="true"] { width: 0; ... overflow: hidden; }`
        hides completely once collapsed. This test must fail against that
        layout.
        """
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        page = _localhost_client(app).get("/").text

        # There must be at least one control, other than the in-sidebar
        # collapse button, that can re-open the sidebar.
        assert "sidebar-expand-btn" in page, (
            "no outside-of-sidebar re-open control found; the sidebar "
            "collapse trap is not fixed"
        )
        assert not _sidebar_span_contains(page, "sidebar", "sidebar-expand-btn"), (
            "the re-open control is nested inside #sidebar -- it will be "
            "hidden by #sidebar[data-collapsed=\"true\"]'s overflow:hidden "
            "rule, recreating the collapse trap"
        )

    def test_reopen_control_has_labelled_state(self, tmp_path):
        """The outside control must expose aria-expanded and a title/label."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        page = _localhost_client(app).get("/").text
        assert 'id="sidebar-expand-btn"' in page
        # Grab the opening tag for the expand button and check it carries
        # both an aria-expanded attribute and a title/aria-label.
        start = page.index('id="sidebar-expand-btn"')
        tag_start = page.rindex("<", 0, start)
        tag_end = page.index(">", start)
        opening_tag = page[tag_start : tag_end + 1]
        assert "aria-expanded=" in opening_tag
        assert "title=" in opening_tag or "aria-label=" in opening_tag

    def test_collapse_and_expand_js_toggle_both_controls(self, tmp_path):
        """The JS must wire up both buttons to toggle data-collapsed and
        keep aria-expanded/title in sync on both, so the exposed state is
        never a lie."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        page = _localhost_client(app).get("/").text
        assert "sidebar-expand-btn" in page
        assert "aria-expanded" in page
        # The expand button must have a click handler wired somewhere in
        # the inline script referencing its id.
        script_start = page.index("<script")
        script = page[script_start:]
        assert "sidebar-expand-btn" in script
        assert "addEventListener" in script

    def test_mobile_breakpoint_also_has_reopen_path(self, tmp_path):
        """The same trap exists at the mobile breakpoint (height:0 rule);
        the fix must not be desktop-only. The re-open control's CSS must
        remain reachable (not itself hidden) inside the same
        max-width:720px media block that collapses the sidebar's height."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        page = _localhost_client(app).get("/").text
        media_start = page.index("@media (max-width: 720px)")
        media_end = page.index("}\n", page.index("}\n", media_start) + 1)
        # Ensure the mobile block doesn't hide/remove the expand button by
        # name (i.e. no `#sidebar-expand-btn { display: none` inside it).
        mobile_block = page[media_start:media_end]
        assert "#sidebar-expand-btn { display: none" not in mobile_block
        assert "#sidebar-expand-btn{display:none" not in mobile_block.replace(
            " ", ""
        )

    def test_existing_collapse_button_unaffected(self, tmp_path):
        """The pre-existing in-sidebar collapse button must still exist and
        still work -- this fix is additive, not a replacement."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        page = _localhost_client(app).get("/").text
        assert 'id="sidebar-collapse-btn"' in page
        assert _sidebar_span_contains(page, "sidebar", "sidebar-collapse-btn")


# ---------------------------------------------------------------------------
# Task 2 -- Open a service HTML UI embedded in the viewer
# ---------------------------------------------------------------------------


class TestTask2IframeViewer:
    """Task 2 acceptance: selecting an HTML service renders an iframe + header."""

    def test_service_row_has_data_view_url(self, tmp_path):
        """Each service row carries data-view-url for the JS viewer."""
        config = _make_config(
            tmp_path,
            services=[Service(name="Resolve", port=8080, path="/")],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-view-url="http://10.0.0.1:8080/"' in html

    def test_service_row_has_data_view_kind_auto_by_default(self, tmp_path):
        config = _make_config(
            tmp_path,
            services=[Service(name="Resolve", port=8080, path="/")],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-view-kind="auto"' in html

    def test_viewer_js_opens_iframe_for_html_service(self, tmp_path):
        """JS contains showViewerIframe logic with iframe element."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "showViewerIframe" in html
        assert "viewer-iframe" in html

    def test_viewer_js_shows_open_in_new_tab_link(self, tmp_path):
        """Viewer header includes an open-in-new-tab link."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-open-tab" in html
        assert "open in new tab" in html

    def test_viewer_js_shows_service_name_in_header(self, tmp_path):
        """Viewer header shows service name."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-svc-name" in html

    def test_viewer_js_shows_back_control(self, tmp_path):
        """Viewer header includes a back/close control."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-close-btn" in html

    def test_service_row_click_handler_js_present(self, tmp_path):
        """JS wires up click handlers on .service rows."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "openServiceInViewer" in html
        assert "data-view-url" in html

    def test_viewer_uses_tailnet_first_link(self, tmp_path):
        """data-view-url uses the first (tailnet-first) resolved link."""
        config = RegistryConfig(
            host_addresses=[
                HostAddress(label="Tailnet", host="100.1.1.1"),
                HostAddress(label="LAN", host="192.168.1.1"),
            ],
            services=[Service(name="muxterm", port=8311, path="/")],
            federation=FederationConfig(
                enabled=True,
                name="node-x",
                base_url="http://100.1.1.1:80",
                state_dir=str(tmp_path / "state"),
            ),
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        # Tailnet link appears first in data-view-url
        assert 'data-view-url="http://100.1.1.1:8311/"' in html


# ---------------------------------------------------------------------------
# Task 3 -- Graceful fallback for services that refuse framing
# ---------------------------------------------------------------------------


class TestTask3EmbedFallback:
    """Task 3 acceptance: embed-probe endpoint + fallback card."""

    def _make_app(self, tmp_path, probe_result):
        config = _make_config(
            tmp_path,
            services=[Service(name="Resolve", port=8080, path="/")],
        )
        return create_app(config, checker=_all_down, embed_probe=lambda url: probe_result)

    def test_embed_probe_endpoint_exists(self, tmp_path):
        config = _make_config(tmp_path)
        app = create_app(
            config,
            checker=_all_down,
            embed_probe=lambda url: {
                "reachable": True,
                "embeddable": True,
                "content_type": "text/html",
            },
        )
        client = _localhost_client(app)
        resp = client.get("/api/embed-probe?url=http://10.0.0.1:8080/")
        assert resp.status_code == 200
        data = resp.json()
        assert "reachable" in data
        assert "embeddable" in data
        assert "content_type" in data

    def test_embed_probe_returns_embeddable_true_for_html(self, tmp_path):
        probe = {"reachable": True, "embeddable": True, "content_type": "text/html"}
        app = self._make_app(tmp_path, probe)
        client = _localhost_client(app)
        resp = client.get("/api/embed-probe?url=http://10.0.0.1:8080/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["embeddable"] is True
        assert data["reachable"] is True

    def test_embed_probe_returns_not_embeddable(self, tmp_path):
        probe = {"reachable": True, "embeddable": False, "content_type": "text/html"}
        app = self._make_app(tmp_path, probe)
        client = _localhost_client(app)
        resp = client.get("/api/embed-probe?url=http://10.0.0.1:8080/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["embeddable"] is False

    def test_embed_probe_returns_unreachable(self, tmp_path):
        probe = {"reachable": False, "embeddable": False, "content_type": None}
        app = self._make_app(tmp_path, probe)
        client = _localhost_client(app)
        resp = client.get("/api/embed-probe?url=http://10.0.0.1:8080/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reachable"] is False

    def test_embed_probe_ssrf_guard_rejects_off_catalogue(self, tmp_path):
        """Probe refuses a URL not in the catalogue (SSRF guard)."""
        config = _make_config(tmp_path)
        # No embed_probe stub: use real endpoint logic with SSRF guard.
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)
        resp = client.get("/api/embed-probe?url=http://evil.example.com/")
        assert resp.status_code == 403

    def test_viewer_js_shows_fallback_card_for_non_embeddable(self, tmp_path):
        """JS contains showViewerFallback logic with fallback card markup."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "showViewerFallback" in html
        assert "viewer-fallback" in html
        assert "viewer-fallback-card" in html

    def test_viewer_fallback_card_has_open_in_new_tab_link(self, tmp_path):
        """Fallback card includes a working open-in-new-tab link."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "viewer-fallback-link" in html

    def test_viewer_fallback_title_text(self, tmp_path):
        """Fallback card shows clear 'Cannot be embedded' message."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "Cannot be embedded" in html

    def test_probe_unreachable_shows_fallback_via_js(self, tmp_path):
        """JS handles probe reachable=false by calling showViewerFallback."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        # The auto-mode JS branch checks probe.reachable
        assert "probe.reachable" in html
        assert "Service is unreachable" in html


# ---------------------------------------------------------------------------
# Task 4 -- Rendered JSON view for JSON endpoints
# ---------------------------------------------------------------------------


class TestTask4JsonView:
    """Task 4 acceptance: view-proxy endpoint + JSON tree renderer."""

    def _make_app_with_proxy(self, tmp_path, proxy_fn):
        config = _make_config(
            tmp_path,
            services=[Service(name="CI", port=8000, path="/status")],
        )
        return create_app(config, checker=_all_down, view_proxy=proxy_fn)

    def test_view_proxy_endpoint_exists(self, tmp_path):
        app = self._make_app_with_proxy(
            tmp_path, lambda url: {"status": "ok", "version": "1.0"}
        )
        client = _localhost_client(app)
        resp = client.get("/api/view-proxy?url=http://10.0.0.1:8000/status")
        assert resp.status_code == 200

    def test_view_proxy_returns_json_for_catalogue_target(self, tmp_path):
        payload = {"status": "ok", "services": 3}
        app = self._make_app_with_proxy(tmp_path, lambda url: payload)
        client = _localhost_client(app)
        resp = client.get("/api/view-proxy?url=http://10.0.0.1:8000/status")
        assert resp.status_code == 200
        assert resp.json() == payload

    def test_view_proxy_ssrf_guard_rejects_off_catalogue(self, tmp_path):
        """Proxy refuses a URL not in the catalogue."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)
        resp = client.get("/api/view-proxy?url=http://169.254.169.254/metadata")
        assert resp.status_code == 403

    def test_view_proxy_stub_none_returns_403(self, tmp_path):
        """When the stub returns None the endpoint returns 403 (SSRF guard)."""
        app = self._make_app_with_proxy(tmp_path, lambda url: None)
        client = _localhost_client(app)
        resp = client.get("/api/view-proxy?url=http://10.0.0.1:8000/status")
        assert resp.status_code == 403

    def test_viewer_js_has_json_tree_renderer(self, tmp_path):
        """JS contains the renderJsonTree function."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "renderJsonTree" in html

    def test_viewer_js_has_show_viewer_json(self, tmp_path):
        """JS contains showViewerJson for JSON-typed services."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "showViewerJson" in html
        assert "viewer-json" in html

    def test_viewer_js_json_tree_renders_keys_and_values(self, tmp_path):
        """JSON tree renderer emits json-key / json-str CSS classes."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "json-key" in html
        assert "json-str" in html

    def test_viewer_js_calls_view_proxy_for_json_kind(self, tmp_path):
        """JS calls /api/view-proxy when kind === 'json'."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "/api/view-proxy" in html
        assert "kind === 'json'" in html

    def test_viewer_js_auto_mode_detects_json_content_type(self, tmp_path):
        """Auto mode checks content_type for application/json."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "application/json" in html
        assert "probe.content_type" in html


# ---------------------------------------------------------------------------
# Task 5 -- Optional per-service view configuration
# ---------------------------------------------------------------------------


class TestTask5ViewConfig:
    """Task 5 acceptance: view_url / view_kind config fields."""

    def test_view_kind_json_sets_data_attribute(self, tmp_path):
        """view_kind: json → data-view-kind="json" on the service row."""
        config = _make_config(
            tmp_path,
            services=[
                Service(name="CI", port=8000, path="/status", view_kind="json")
            ],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-view-kind="json"' in html

    def test_view_kind_iframe_sets_data_attribute(self, tmp_path):
        config = _make_config(
            tmp_path,
            services=[
                Service(name="Resolve", port=8080, path="/", view_kind="iframe")
            ],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-view-kind="iframe"' in html

    def test_view_kind_auto_sets_data_attribute(self, tmp_path):
        config = _make_config(
            tmp_path,
            services=[
                Service(name="Resolve", port=8080, path="/", view_kind="auto")
            ],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-view-kind="auto"' in html

    def test_view_url_overrides_primary_link(self, tmp_path):
        """view_url overrides the default data-view-url."""
        config = _make_config(
            tmp_path,
            services=[
                Service(
                    name="CI",
                    port=8000,
                    path="/",
                    view_url="http://10.0.0.1:8000/status",
                    view_kind="json",
                )
            ],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-view-url="http://10.0.0.1:8000/status"' in html

    def test_no_view_fields_defaults_to_auto_and_primary_link(self, tmp_path):
        """A service with no view_url/view_kind defaults to auto + primary link."""
        config = _make_config(
            tmp_path,
            services=[Service(name="Resolve", port=8080, path="/")],
        )
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert 'data-view-kind="auto"' in html
        assert 'data-view-url="http://10.0.0.1:8080/"' in html

    def test_legacy_config_loads_without_error(self, tmp_path):
        """A config with no view_url/view_kind fields still loads and renders."""
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

    def test_view_kind_json_triggers_json_viewer_in_js(self, tmp_path):
        """JS openServiceInViewer routes kind=json to view-proxy path."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "kind === 'json'" in html
        assert "/api/view-proxy" in html

    def test_view_kind_iframe_triggers_iframe_in_js(self, tmp_path):
        """JS openServiceInViewer routes kind=iframe to showViewerIframe."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "kind === 'iframe'" in html
        assert "showViewerIframe" in html

    def test_view_kind_auto_uses_probe_in_js(self, tmp_path):
        """JS auto mode calls /api/embed-probe."""
        config = _make_config(tmp_path)
        app = create_app(config, checker=_all_down)
        html = _localhost_client(app).get("/").text
        assert "/api/embed-probe" in html

    def test_config_parse_view_kind_json(self, tmp_path):
        """view_kind: json is accepted by the config parser."""
        from service_directory.config import parse_config

        yaml_text = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "CI", port: 8000, view_kind: "json"}
"""
        cfg = parse_config(yaml_text)
        assert cfg.services[0].view_kind == "json"

    def test_config_parse_view_url(self, tmp_path):
        """view_url is accepted by the config parser."""
        from service_directory.config import parse_config

        yaml_text = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "CI", port: 8000, view_url: "http://10.0.0.1:8000/status", view_kind: "json"}
"""
        cfg = parse_config(yaml_text)
        assert cfg.services[0].view_url == "http://10.0.0.1:8000/status"
        assert cfg.services[0].view_kind == "json"

    def test_config_parse_rejects_invalid_view_kind(self, tmp_path):
        """An invalid view_kind value raises ConfigError."""
        from service_directory.config import ConfigError, parse_config

        yaml_text = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "CI", port: 8000, view_kind: "bogus"}
"""
        with pytest.raises(ConfigError):
            parse_config(yaml_text)

    def test_config_parse_rejects_unsafe_view_url(self, tmp_path):
        """A view_url with a non-http(s) scheme raises ConfigError."""
        from service_directory.config import ConfigError, parse_config

        yaml_text = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "CI", port: 8000, view_url: "javascript:alert(1)"}
"""
        with pytest.raises(ConfigError):
            parse_config(yaml_text)

    def test_api_services_includes_view_fields(self, tmp_path):
        """The /api/services/local endpoint propagates view_url/view_kind."""
        config = _make_config(
            tmp_path,
            services=[
                Service(
                    name="CI",
                    port=8000,
                    path="/status",
                    view_url="http://10.0.0.1:8000/status",
                    view_kind="json",
                )
            ],
        )
        app = create_app(config, checker=_all_down)
        client = _localhost_client(app)
        resp = client.get("/api/services/local")
        assert resp.status_code == 200
        data = resp.json()
        ci = next(s for s in data if s["name"] == "CI")
        assert ci["view_url"] == "http://10.0.0.1:8000/status"
        assert ci["view_kind"] == "json"
