from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from service_directory.app import create_app
from service_directory.config import ConfigError, load_config


def _all_down(url: str) -> bool:
    return False


def _all_up(url: str) -> bool:
    return True


@pytest.fixture
def client(sample_config):
    app = create_app(sample_config, checker=_all_down)
    return TestClient(app)


def test_index_renders_exact_url_for_every_service_x_address_pair(
    client, sample_config
):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text

    for svc in sample_config.services:
        assert svc.name in html
        for addr in sample_config.host_addresses:
            path = svc.path or "/"
            expected_url = f"http://{addr.host}:{svc.port}{path}"
            assert expected_url in html, f"missing {expected_url} in rendered HTML"


def test_index_includes_description_when_present(client):
    resp = client.get("/")
    assert "Video editor" in resp.text


def test_index_html_escapes_content(sample_config):
    """Guard against XSS via config-provided name/description -- html must be
    escaped, not raw-injected."""
    from service_directory.config import HostAddress, RegistryConfig, Service

    evil_config = RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[
            Service(
                name="<script>alert(1)</script>",
                port=80,
                path="/",
                description="<img src=x onerror=alert(2)>",
            )
        ],
    )
    app = create_app(evil_config, checker=_all_down)
    c = TestClient(app)
    resp = c.get("/")
    assert "<script>alert(1)</script>" not in resp.text
    assert "&lt;script&gt;" in resp.text


def test_api_services_returns_same_urls_as_html(client, sample_config):
    resp = client.get("/api/services")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) == len(sample_config.services)
    by_name = {svc["name"]: svc for svc in data}

    for svc in sample_config.services:
        entry = by_name[svc.name]
        assert entry["description"] == svc.description
        urls = {link["url"] for link in entry["links"]}
        expected_urls = {
            f"http://{addr.host}:{svc.port}{svc.path or '/'}"
            for addr in sample_config.host_addresses
        }
        assert urls == expected_urls

    # JSON is genuinely parseable / round-trips (contract check).
    reparsed = json.loads(resp.text)
    assert reparsed == data


def test_api_services_host_addresses_tailnet_first(client):
    resp = client.get("/api/services")
    data = resp.json()
    for svc in data:
        labels = [link["label"] for link in svc["links"]]
        assert labels == ["Tailnet", "LAN"]


def test_api_health_all_down_when_checker_stubbed_to_fail(client, sample_config):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()

    expected_names = {svc.name for svc in sample_config.services}
    assert set(data.keys()) == expected_names
    assert all(status == "down" for status in data.values())


def test_index_still_renders_when_all_health_checks_fail(client):
    """The dashboard page itself doesn't even call the health checker, but
    per spec the page must render fine when every check fails -- confirm
    both endpoints work together without error in the all-down scenario."""
    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200

    index_resp = client.get("/")
    assert index_resp.status_code == 200
    assert "<html" in index_resp.text.lower()


def test_api_health_reports_up_when_checker_stubbed_to_succeed(sample_config):
    app = create_app(sample_config, checker=_all_up)
    c = TestClient(app)
    resp = c.get("/api/health")
    data = resp.json()
    assert all(status == "up" for status in data.values())


def test_app_creation_fails_clearly_on_malformed_config(tmp_path):
    bad_config = tmp_path / "bad.yaml"
    bad_config.write_text("not: valid: yaml: [")

    with pytest.raises(ConfigError):
        load_config(str(bad_config))


def test_app_creation_fails_clearly_on_missing_required_keys(tmp_path):
    bad_config = tmp_path / "bad2.yaml"
    bad_config.write_text("host_addresses:\n  - {label: a, host: b}\n")

    with pytest.raises(ConfigError, match="services"):
        load_config(str(bad_config))
