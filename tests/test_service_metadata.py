"""Tests for the richer, all-optional service metadata fields (category,
tags, icon, owner, docs_url) added to config.py and surfaced via
/api/services and /api/services/local.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from service_directory.app import create_app
from service_directory.config import ConfigError, Service, parse_config

BASE_YAML = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
"""


def _all_down(url: str) -> bool:
    return False


# --- config.py parsing --------------------------------------------------------


def test_service_metadata_all_omitted_defaults_to_none_and_empty_list():
    """A legacy service with only name/port/path/description must still
    load identically -- new fields default to None/[] when absent."""
    cfg = parse_config(
        BASE_YAML + '  - {name: "legacy", port: 80, path: "/", description: "d"}\n'
    )
    svc = cfg.services[0]
    assert svc.name == "legacy"
    assert svc.port == 80
    assert svc.description == "d"
    assert svc.category is None
    assert svc.tags == []
    assert svc.icon is None
    assert svc.owner is None
    assert svc.docs_url is None


def test_service_metadata_bare_legacy_entry_still_loads():
    """A service with ONLY name/port (no path, no description, no new
    fields at all) must still parse and behave identically to before."""
    cfg = parse_config(BASE_YAML + '  - {name: "bare", port: 1234}\n')
    svc = cfg.services[0]
    assert svc.name == "bare"
    assert svc.port == 1234
    assert svc.path == "/"
    assert svc.description is None
    assert svc.category is None
    assert svc.tags == []
    assert svc.icon is None
    assert svc.owner is None
    assert svc.docs_url is None


def test_service_metadata_all_fields_parse_when_present():
    yaml_text = BASE_YAML + (
        '  - {name: "rich", port: 80, category: "tools", '
        'tags: ["a", "b"], icon: "🔧", owner: "team-x", '
        'docs_url: "https://example.invalid/docs"}\n'
    )
    cfg = parse_config(yaml_text)
    svc = cfg.services[0]
    assert svc.category == "tools"
    assert svc.tags == ["a", "b"]
    assert svc.icon == "🔧"
    assert svc.owner == "team-x"
    assert svc.docs_url == "https://example.invalid/docs"


def test_service_metadata_partial_fields_use_defaults_for_rest():
    yaml_text = BASE_YAML + '  - {name: "partial", port: 80, category: "infra"}\n'
    cfg = parse_config(yaml_text)
    svc = cfg.services[0]
    assert svc.category == "infra"
    assert svc.tags == []
    assert svc.icon is None


@pytest.mark.parametrize(
    "bad_field,expected_match",
    [
        ('category: 5', "category"),
        ('tags: "not-a-list"', "tags"),
        ('tags: [1, 2]', "tags"),
        ('icon: 5', "icon"),
        ('owner: 5', "owner"),
        ('docs_url: 5', "docs_url"),
    ],
)
def test_service_metadata_malformed_fields_raise_clear_error(bad_field, expected_match):
    yaml_text = BASE_YAML + f'  - {{name: "x", port: 80, {bad_field}}}\n'
    with pytest.raises(ConfigError, match=expected_match):
        parse_config(yaml_text)


def test_service_metadata_tags_null_treated_as_empty_list():
    """An explicit `tags: null` (valid YAML) must degrade to [] rather than
    crash -- defensive against a config author writing an empty key."""
    yaml_text = BASE_YAML + '  - {name: "x", port: 80, tags: null}\n'
    cfg = parse_config(yaml_text)
    assert cfg.services[0].tags == []


# --- surfaced via HTTP API ----------------------------------------------------


def _config_with(svc: Service):
    from service_directory.config import HostAddress, RegistryConfig

    return RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[svc],
    )


def test_api_services_includes_metadata_when_present():
    svc = Service(
        name="rich",
        port=80,
        category="tools",
        tags=["a", "b"],
        icon="🔧",
        owner="team-x",
        docs_url="https://example.invalid/docs",
    )
    app = create_app(_config_with(svc), checker=_all_down)
    client = TestClient(app)
    resp = client.get("/api/services")
    assert resp.status_code == 200
    entry = resp.json()[0]
    assert entry["category"] == "tools"
    assert entry["tags"] == ["a", "b"]
    assert entry["icon"] == "🔧"
    assert entry["owner"] == "team-x"
    assert entry["docs_url"] == "https://example.invalid/docs"


def test_api_services_metadata_is_none_when_absent():
    svc = Service(name="plain", port=80)
    app = create_app(_config_with(svc), checker=_all_down)
    client = TestClient(app)
    resp = client.get("/api/services")
    entry = resp.json()[0]
    assert entry["category"] is None
    assert entry["tags"] == []
    assert entry["icon"] is None
    assert entry["owner"] is None
    assert entry["docs_url"] is None


def test_api_services_local_includes_metadata_too():
    svc = Service(name="rich", port=80, category="tools", tags=["x"])
    app = create_app(_config_with(svc), checker=_all_down)
    client = TestClient(app)
    resp = client.get("/api/services/local")
    entry = resp.json()[0]
    assert entry["category"] == "tools"
    assert entry["tags"] == ["x"]


def test_legacy_config_full_end_to_end_loads_and_renders_identically(sample_config_path):
    """A legacy config file (no new fields at all, from the shared
    conftest fixture) must still load via load_config and render the
    dashboard page without error -- full backward-compat guarantee."""
    from service_directory.config import load_config

    cfg = load_config(sample_config_path)
    for svc in cfg.services:
        assert svc.category is None
        assert svc.tags == []
        assert svc.icon is None
        assert svc.owner is None
        assert svc.docs_url is None

    app = create_app(cfg, checker=_all_down)
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    resp2 = client.get("/api/services")
    assert resp2.status_code == 200
    assert len(resp2.json()) == len(cfg.services)
