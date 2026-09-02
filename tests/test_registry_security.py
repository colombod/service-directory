"""Security remediation tests for the dynamic service registry.

A prior automated security review flagged two medium-severity issues in
the dynamic-registry feature:

S1 (SSRF): a dynamic entry's ``health_url`` (and the TCP-fallback target
built from a raw ``url`` field) is fully caller-supplied. Without a
target allow-list, every hit of GET /api/health becomes a server-side
outbound HTTP GET / TCP connect to an attacker-chosen host -- including
loopback ports, RFC1918-private LAN services, link-local addresses, and
the cloud-metadata address 169.254.169.254.

S2 (stored XSS): the dashboard renders a resolved link's raw URL as a
clickable <a href="..."> without the same javascript:/unsafe-scheme
filtering already applied to docs_url, allowing a stored `javascript:`
link to execute attacker JS in the dashboard origin when clicked.

Fix (S1): ``config.is_safe_health_target`` blocks unsafe schemes and
literal loopback/link-local/private/reserved hosts; ``health.
check_service_entries`` applies it to every DYNAMIC entry's health_url
and raw-url TCP-fallback target before ever invoking the checker seam.
Port-based dynamic links (built against configured, trusted
host_addresses) are unaffected -- they reuse the same trust tier as
static services.

Fix (S2): ``app._service_card_html`` filters every resolved link through
``is_safe_docs_url`` before rendering it as an href, exactly like
docs_url already does.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from service_directory.app import _service_card_html, create_app
from service_directory.config import (
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
    is_safe_health_target,
)
from service_directory.health import check_service_entries


def _all_down(url: str) -> bool:
    return False


def _all_up(url: str) -> bool:
    return True


def _http_up(url: str) -> bool:
    return True


def _make_config(tmp_path, *, allow_private_health_targets=False):
    return RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[Service(name="Resolve", port=8080, path="/", description="d")],
        federation=FederationConfig(
            enabled=True,
            name="local-node",
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
            allow_private_health_targets=allow_private_health_targets,
        ),
    )


def _localhost_client(app) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 12345))


# --- is_safe_health_target: unit-level allow-list -----------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid/health",
        "https://example.invalid/health",
        "http://8.8.8.8/health",  # public IP literal is fine
    ],
)
def test_is_safe_health_target_allows_public_http_https(url):
    assert is_safe_health_target(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9999/admin",  # loopback IP literal
        "http://localhost:9999/admin",  # loopback hostname
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://10.0.0.5:22/",  # RFC1918 private
        "http://172.16.0.1/",  # RFC1918 private
        "http://192.168.1.1/",  # RFC1918 private
        "javascript:alert(1)",  # unsafe scheme
        "ftp://example.invalid/",  # unsafe scheme
        "",
        "not a url at all",
    ],
)
def test_is_safe_health_target_rejects_private_and_unsafe_targets(url):
    assert is_safe_health_target(url) is False


def test_is_safe_health_target_allow_private_opt_in():
    assert is_safe_health_target("http://127.0.0.1:9999/", allow_private=True) is True
    assert is_safe_health_target("http://169.254.169.254/", allow_private=True) is True
    # Scheme allow-list still applies even with allow_private:
    assert is_safe_health_target("javascript:alert(1)", allow_private=True) is False


# --- check_service_entries: SSRF guard applied to dynamic health_url ----------


def test_dynamic_health_url_targeting_loopback_is_blocked_never_calls_checker():
    def exploding_http(url):
        raise AssertionError("must never be called for an SSRF-blocked target")

    entries = [
        {
            "name": "evil-svc",
            "ttl": None,
            "source": "dynamic",
            "health_url": "http://127.0.0.1:9999/admin",
            "links": [],
        }
    ]
    results = check_service_entries(
        entries, checker=_all_up, http_checker=exploding_http
    )
    assert results == {"evil-svc": "down"}


def test_dynamic_health_url_targeting_metadata_address_is_blocked():
    def exploding_http(url):
        raise AssertionError("must never be called for an SSRF-blocked target")

    entries = [
        {
            "name": "evil-svc",
            "ttl": None,
            "source": "dynamic",
            "health_url": "http://169.254.169.254/latest/meta-data/",
            "links": [],
        }
    ]
    results = check_service_entries(
        entries, checker=_all_up, http_checker=exploding_http
    )
    assert results == {"evil-svc": "down"}


def test_dynamic_raw_url_tcp_fallback_targeting_private_lan_is_blocked():
    """A dynamic entry registered with a raw `url` (no `port`) builds a
    link with host="" (see app._dynamic_service_json) -- this is the
    genuinely caller-controlled TCP-fallback target and must be SSRF-
    checked."""

    def exploding_tcp(url):
        raise AssertionError("must never be called for an SSRF-blocked target")

    entries = [
        {
            "name": "evil-tcp",
            "ttl": None,
            "source": "dynamic",
            "health_url": None,
            "links": [{"label": "url", "host": "", "url": "http://10.0.0.5:22/"}],
        }
    ]
    results = check_service_entries(
        entries, checker=exploding_tcp, http_checker=_all_up
    )
    assert results == {"evil-tcp": "down"}


def test_dynamic_health_url_public_target_still_checked_normally():
    entries = [
        {
            "name": "good-svc",
            "ttl": None,
            "source": "dynamic",
            "health_url": "http://example.invalid/health",
            "links": [],
        }
    ]
    results = check_service_entries(entries, checker=_all_down, http_checker=_http_up)
    assert results == {"good-svc": "up"}


def test_static_entries_never_subject_to_ssrf_check_even_with_private_link():
    """Static services legitimately resolve against private LAN
    host_addresses (that's the whole point of this app) -- they must
    never be blocked by the SSRF guard."""
    entries = [
        {
            "name": "static-svc",
            "ttl": None,
            "source": "static",
            "health_url": None,
            "links": [
                {"label": "LAN", "host": "10.0.0.1", "url": "http://10.0.0.1:8080/"}
            ],
        }
    ]
    results = check_service_entries(entries, checker=_all_up, http_checker=_all_down)
    assert results == {"static-svc": "up"}


def test_dynamic_port_based_link_against_trusted_host_address_not_blocked():
    """A dynamic entry registered with `port` (not raw `url`) resolves
    against the SAME configured, trusted host_addresses as static
    services -- see app._dynamic_service_json setting host=addr.host.
    This must NOT be treated as an SSRF target even though the configured
    LAN address is itself a private IP."""
    entries = [
        {
            "name": "dynamic-port-svc",
            "ttl": None,
            "source": "dynamic",
            "health_url": None,
            "links": [
                {"label": "LAN", "host": "10.0.0.1", "url": "http://10.0.0.1:9000/"}
            ],
        }
    ]
    results = check_service_entries(entries, checker=_all_up, http_checker=_all_down)
    assert results == {"dynamic-port-svc": "up"}


def test_allow_private_health_targets_opt_in_permits_loopback():
    entries = [
        {
            "name": "internal-svc",
            "ttl": None,
            "source": "dynamic",
            "health_url": "http://127.0.0.1:9999/health",
            "links": [],
        }
    ]
    results = check_service_entries(
        entries,
        checker=_all_down,
        http_checker=_http_up,
        allow_private_health_targets=True,
    )
    assert results == {"internal-svc": "up"}


# --- app-level: end-to-end SSRF guard via /api/health -------------------------


def test_api_health_blocks_ssrf_against_loopback_via_health_url(tmp_path):
    def exploding_http(url):
        raise AssertionError("must never be called for an SSRF-blocked target")

    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_up, http_checker=exploding_http)
    client = _localhost_client(app)
    client.post(
        "/api/services",
        json={
            "name": "attacker-svc",
            "port": 1,
            "health_url": "http://127.0.0.1:9999/internal-admin",
        },
    )
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["attacker-svc"] == "down"


def test_api_health_blocks_ssrf_against_cloud_metadata_via_health_url(tmp_path):
    def exploding_http(url):
        raise AssertionError("must never be called for an SSRF-blocked target")

    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_up, http_checker=exploding_http)
    client = _localhost_client(app)
    client.post(
        "/api/services",
        json={
            "name": "attacker-svc",
            "port": 1,
            "health_url": "http://169.254.169.254/latest/meta-data/",
        },
    )
    resp = client.get("/api/health")
    assert resp.json()["attacker-svc"] == "down"


def test_api_health_allows_public_health_url_normally(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down, http_checker=_http_up)
    client = _localhost_client(app)
    client.post(
        "/api/services",
        json={
            "name": "public-svc",
            "port": 1,
            "health_url": "http://example.invalid/health",
        },
    )
    resp = client.get("/api/health")
    assert resp.json()["public-svc"] == "up"


# --- app-level: XSS scheme filtering on resolved links (S2) -------------------


def test_service_card_html_omits_link_for_javascript_scheme_url():
    svc = {
        "name": "evil-svc",
        "description": None,
        "links": [
            {"label": "url", "host": "", "url": "javascript:alert(document.cookie)"}
        ],
        "category": None,
        "tags": [],
        "icon": None,
        "owner": None,
        "docs_url": None,
        "origin": "local",
        "source": "dynamic",
    }
    html = _service_card_html(svc)
    assert "javascript:" not in html
    assert "evil-svc" in html


def test_service_card_html_renders_link_for_https_url():
    svc = {
        "name": "good-svc",
        "description": None,
        "links": [{"label": "url", "host": "", "url": "https://example.invalid/"}],
        "category": None,
        "tags": [],
        "icon": None,
        "owner": None,
        "docs_url": None,
        "origin": "local",
        "source": "dynamic",
    }
    html = _service_card_html(svc)
    assert 'href="https://example.invalid/"' in html


def test_dashboard_end_to_end_never_emits_javascript_href_for_dynamic_url(tmp_path):
    """Full end-to-end: register a dynamic service with a raw
    `javascript:` url; the rendered dashboard HTML must never contain it
    as a live link."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)
    resp = client.post(
        "/api/services",
        json={
            "name": "xss-svc",
            "url": "javascript:fetch('/api/services',{method:'POST'})",
        },
    )
    assert resp.status_code == 200

    page = client.get("/")
    assert page.status_code == 200
    assert "javascript:" not in page.text
    assert "xss-svc" in page.text
