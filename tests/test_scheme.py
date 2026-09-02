"""Tests for the optional `scheme` field on host_addresses / services.

Covers:
- config.py parsing: optional scheme on host_addresses (default "http") and
  on services (default None -- meaning "inherit from host address").
- urls.py: build_url respects an explicit scheme (default "http" preserved
  for backward compatibility); resolve_service applies per-service scheme
  override when present, otherwise the host address's own scheme.
- Full backward compatibility: a config with no scheme fields anywhere
  behaves EXACTLY like before (all http:// links).
- Negative/adversarial cases: invalid scheme values raise ConfigError with
  a clear message; malformed types are rejected.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from service_directory.app import create_app
from service_directory.config import (
    ConfigError,
    HostAddress,
    RegistryConfig,
    Service,
    parse_config,
)
from service_directory.urls import build_url, resolve_all, resolve_service


def _all_down(url: str) -> bool:
    return False


# --- urls.py: build_url --------------------------------------------------


def test_build_url_defaults_to_http_when_scheme_omitted():
    assert build_url("host", 80) == "http://host:80/"


def test_build_url_respects_explicit_https_scheme():
    assert build_url("host", 443, "/", scheme="https") == "https://host:443/"


def test_build_url_https_with_custom_path():
    assert (
        build_url("100.111.191.22", 8080, "app", scheme="https")
        == "https://100.111.191.22:8080/app"
    )


# --- urls.py: resolve_service scheme precedence ---------------------------


def test_resolve_service_uses_host_address_scheme_by_default():
    addr = HostAddress(label="Tailnet", host="10.0.0.1", scheme="https")
    svc = Service(name="svc", port=80)
    resolved = resolve_service(svc, [addr])
    assert resolved.links[0].url == "https://10.0.0.1:80/"


def test_resolve_service_defaults_to_http_when_no_scheme_anywhere():
    addr = HostAddress(label="Tailnet", host="10.0.0.1")
    svc = Service(name="svc", port=80)
    resolved = resolve_service(svc, [addr])
    assert resolved.links[0].url == "http://10.0.0.1:80/"


def test_resolve_service_per_service_scheme_override_wins():
    """Per-service scheme override wins over the host address's own scheme,
    in EITHER direction (upgrade to https, or downgrade to http)."""
    addr = HostAddress(label="Tailnet", host="10.0.0.1", scheme="http")
    svc = Service(name="svc", port=443, scheme="https")
    resolved = resolve_service(svc, [addr])
    assert resolved.links[0].url == "https://10.0.0.1:443/"

    addr2 = HostAddress(label="Tailnet", host="10.0.0.1", scheme="https")
    svc2 = Service(name="svc2", port=80, scheme="http")
    resolved2 = resolve_service(svc2, [addr2])
    assert resolved2.links[0].url == "http://10.0.0.1:80/"


def test_resolve_all_mixed_schemes_across_host_addresses():
    """Each host address's own scheme applies independently when the
    service has no override -- order (tailnet-first) is preserved."""
    config = RegistryConfig(
        host_addresses=[
            HostAddress(label="Tailnet", host="100.111.191.22", scheme="https"),
            HostAddress(label="LAN", host="192.168.1.86"),  # default http
        ],
        services=[Service(name="svc", port=8080)],
    )
    resolved = resolve_all(config)
    links = resolved[0].links
    assert links[0].label == "Tailnet"
    assert links[0].url == "https://100.111.191.22:8080/"
    assert links[1].label == "LAN"
    assert links[1].url == "http://192.168.1.86:8080/"


# --- config.py: parsing scheme on host_addresses --------------------------


def test_parse_host_address_scheme_defaults_to_http():
    cfg = parse_config(
        "host_addresses:\n  - {label: a, host: b}\nservices:\n  - {name: x, port: 1}\n"
    )
    assert cfg.host_addresses[0].scheme == "http"


def test_parse_host_address_scheme_https_explicit():
    cfg = parse_config(
        'host_addresses:\n  - {label: a, host: b, scheme: "https"}\n'
        "services:\n  - {name: x, port: 1}\n"
    )
    assert cfg.host_addresses[0].scheme == "https"


def test_parse_host_address_invalid_scheme_raises_config_error():
    with pytest.raises(ConfigError, match="scheme"):
        parse_config(
            'host_addresses:\n  - {label: a, host: b, scheme: "ftp"}\n'
            "services:\n  - {name: x, port: 1}\n"
        )


def test_parse_host_address_non_string_scheme_raises_config_error():
    with pytest.raises(ConfigError, match="scheme"):
        parse_config(
            "host_addresses:\n  - {label: a, host: b, scheme: 5}\n"
            "services:\n  - {name: x, port: 1}\n"
        )


# --- config.py: parsing scheme on services --------------------------------


def test_parse_service_scheme_defaults_to_none():
    cfg = parse_config(
        "host_addresses:\n  - {label: a, host: b}\nservices:\n  - {name: x, port: 1}\n"
    )
    assert cfg.services[0].scheme is None


def test_parse_service_scheme_https_explicit():
    cfg = parse_config(
        "host_addresses:\n  - {label: a, host: b}\n"
        'services:\n  - {name: x, port: 1, scheme: "https"}\n'
    )
    assert cfg.services[0].scheme == "https"


def test_parse_service_invalid_scheme_raises_config_error():
    with pytest.raises(ConfigError, match="scheme"):
        parse_config(
            "host_addresses:\n  - {label: a, host: b}\n"
            'services:\n  - {name: x, port: 1, scheme: "javascript"}\n'
        )


# --- Backward compatibility -----------------------------------------------


def test_legacy_config_no_scheme_fields_resolves_all_http(sample_config):
    """A config with no `scheme` key anywhere behaves EXACTLY like before
    this feature was added -- every resolved link is http://."""
    resolved = resolve_all(sample_config)
    for svc in resolved:
        for link in svc.links:
            assert link.url.startswith("http://")
            assert "https://" not in link.url


# --- end-to-end: real FastAPI app + TestClient (real ASGI transport) ------


def test_end_to_end_https_scheme_rendered_in_index_and_api(tmp_path):
    """Real end-to-end path: build a real RegistryConfig with an https
    host_address, boot a real FastAPI app, hit it through TestClient (real
    ASGI request/response cycle, not a mock), and confirm both GET / (HTML)
    and GET /api/services (JSON) surface the https:// URL."""
    config = RegistryConfig(
        host_addresses=[HostAddress(label="Tailnet", host="10.0.0.1", scheme="https")],
        services=[Service(name="svc-tls", port=443, path="/")],
    )
    app = create_app(config, checker=_all_down)
    client = TestClient(app)

    index_html = client.get("/").text
    assert "https://10.0.0.1:443/" in index_html

    api_resp = client.get("/api/services")
    assert api_resp.status_code == 200
    data = api_resp.json()
    assert data[0]["links"][0]["url"] == "https://10.0.0.1:443/"


def test_end_to_end_dynamic_service_uses_host_address_scheme(tmp_path):
    """A dynamically-registered service (POST /api/services) must ALSO
    resolve its links using the host address's scheme -- not hard-coded
    http://. Real end-to-end: register via a real POST, then read back via
    both GET /api/services and the rendered dashboard HTML."""
    from service_directory.config import FederationConfig

    config = RegistryConfig(
        host_addresses=[HostAddress(label="Tailnet", host="10.0.0.1", scheme="https")],
        services=[Service(name="static-svc", port=1)],
        federation=FederationConfig(state_dir=str(tmp_path / "state")),
    )
    app = create_app(config, checker=_all_down)
    client = TestClient(app, client=("127.0.0.1", 1))  # localhost bypass

    resp = client.post("/api/services", json={"name": "dyn-svc", "port": 9999})
    assert resp.status_code == 200
    body = resp.json()
    assert body["links"][0]["url"] == "https://10.0.0.1:9999/"

    api_resp = client.get("/api/services")
    by_name = {s["name"]: s for s in api_resp.json()}
    assert by_name["dyn-svc"]["links"][0]["url"] == "https://10.0.0.1:9999/"

    html = client.get("/").text
    assert "https://10.0.0.1:9999/" in html


def test_per_service_scheme_override_end_to_end_wins_over_host_address(tmp_path):
    """A service-level scheme override must win over the host address's
    own scheme, verified through the real app + JSON API (not just the
    pure resolve_service unit test above)."""
    config = RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="192.168.1.1", scheme="http")],
        services=[Service(name="tls-svc", port=443, scheme="https")],
    )
    app = create_app(config, checker=_all_down)
    client = TestClient(app)
    data = client.get("/api/services").json()
    assert data[0]["links"][0]["url"] == "https://192.168.1.1:443/"
