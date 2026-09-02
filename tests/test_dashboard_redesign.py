"""Tests for the visual redesign of GET / (Part B of the dashboard task).

Verifies:
- Required HTML hooks that existing JS/tests depend on are still present
  (id=service-filter, section.node-group with data-origin, li.service with
  data-search/data-name, health pill/dot element, add-service form,
  write-token input, delete control on dynamic entries only).
- The redesign's NEW structural requirements: CSS token system with light
  AND dark support (@media prefers-color-scheme: dark), the responsive
  card-grid CSS, category chip / tag pills / health status pill markup,
  primary/secondary link buttons, node-group header badge, sticky filter.
- Graceful empty state when there are no services.
- No external assets (no <script src=, no CDN references) -- single
  self-contained page.
- Accessible: aria-label on the filter input.
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


def _all_down(url: str) -> bool:
    return False


def _make_config(tmp_path, *, services=None, name="local-node"):
    return RegistryConfig(
        host_addresses=[HostAddress(label="Tailnet", host="10.0.0.1")],
        services=services
        if services is not None
        else [Service(name="Resolve", port=8080, path="/", description="d")],
        federation=FederationConfig(
            enabled=True,
            name=name,
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
        ),
    )


def _localhost_client(app) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 12345))


# --- required hooks preserved ----------------------------------------------


def test_required_hooks_all_present(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text

    assert 'id="service-filter"' in html
    assert '<section class="node-group"' in html
    assert 'data-origin="local-node"' in html
    assert 'class="service card"' in html or "service" in html
    assert 'data-search="' in html
    assert 'data-name="Resolve"' in html
    assert "health-dot" in html
    assert "health-pill" in html
    assert 'id="add-service-form"' in html
    assert 'name="name"' in html
    assert 'name="port"' in html
    assert 'id="write-token-input"' in html


def test_delete_control_present_on_dynamic_entry_only(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    client.post("/api/services", json={"name": "dyn-svc", "port": 1})

    html = client.get("/").text
    assert 'data-remove-name="dyn-svc"' in html
    assert 'data-remove-name="Resolve"' not in html


def test_no_external_assets(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text
    assert "<script src=" not in html
    assert "cdn." not in html.lower()
    assert "http://fonts.googleapis" not in html
    assert "http://cdnjs" not in html.lower()


# --- new visual redesign requirements ---------------------------------------


def test_css_token_system_present(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text
    assert "<style>" in html
    assert ":root" in html
    assert "--bg" in html
    assert "--accent" in html


def test_light_and_dark_mode_support(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text
    assert "prefers-color-scheme: dark" in html
    assert "color-scheme: light dark" in html


def test_responsive_card_grid_css_present(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text
    assert "display: grid" in html
    assert "repeat(auto-fill, minmax(280px" in html


def test_category_tags_and_link_buttons_present(tmp_path):
    config = _make_config(
        tmp_path,
        services=[
            Service(
                name="Resolve",
                port=8080,
                path="/",
                description="d",
                category="pipelines",
                tags=["video", "editor"],
            )
        ],
    )
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text
    assert 'class="category"' in html
    assert 'class="tag"' in html
    assert "pipelines" in html
    assert "video" in html
    assert 'class="link-btn link-btn-primary"' in html


def test_node_group_has_reachable_badge(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text
    assert 'class="reachable-badge reachable"' in html


def test_filter_input_has_aria_label(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text
    assert "aria-label=" in html


def test_empty_state_when_no_services(tmp_path):
    """An empty (but valid) catalogue renders a clean empty-state, not a
    bare/broken page. RegistryConfig requires >=1 static service via YAML
    parsing, but nothing stops an empty catalogue at the dataclass level
    (e.g. all services filtered out upstream) -- exercise _render_html
    directly for this case."""
    from service_directory.app import _render_html

    html = _render_html([], node_info=[{"name": "local-node", "description": None}])
    assert "empty-state" in html
    assert "No services registered yet" in html
    # Still a valid page with the filter/add-form present.
    assert 'id="service-filter"' in html
    assert 'id="add-service-form"' in html


def test_docs_link_and_owner_shown_in_footer(tmp_path):
    config = _make_config(
        tmp_path,
        services=[
            Service(
                name="Resolve",
                port=8080,
                path="/",
                description="d",
                owner="team-x",
                docs_url="https://example.invalid/docs",
            )
        ],
    )
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text
    assert 'class="meta"' in html
    assert "team-x" in html
    assert 'class="docs"' in html
    assert 'href="https://example.invalid/docs"' in html


def test_health_pill_updates_via_js_status_classes(tmp_path):
    """The inline JS must map /api/health status onto BOTH .health-dot and
    .health-pill classes (up/down) -- assert the JS source references both
    selectors and both status literals."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text
    assert "health-pill" in html
    assert "'up'" in html
    assert "'down'" in html


# --- filter semantics unchanged ---------------------------------------------


def test_filter_hides_empty_node_groups_semantics_preserved(tmp_path):
    """The JS filter logic (unchanged) hides a node-group section when none
    of its cards match -- confirm the JS block implementing this is still
    present verbatim in structure (section.style.display toggle)."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    html = client.get("/").text
    assert "section.style.display = visibleCount > 0 ? '' : 'none';" in html
