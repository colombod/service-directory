"""Security remediation tests: docs_url scheme allow-list.

A prior automated security review (S1, medium severity) flagged that the
new `docs_url` service-metadata field was rendered directly into an
`<a href="...">` attribute using only HTML-entity escaping, which does not
block `javascript:`/`data:`/`vbscript:` URI schemes. Because docs_url can
be populated from LOCAL config (fully trusted) or RELAYED from a federated
peer's own /api/services/local response (a lower trust tier -- see
federation.py aggregate_services / app.py _aggregated_services), a
malicious or compromised peer could otherwise inject a click-to-execute
script link into this node's dashboard.

Fix: validate against an http(s)-only scheme allow-list both (a) at config
parse time (fail closed on bad local admin input) and (b) defensively again
at render time in _service_card_html, since peer-relayed docs_url values
never pass through the config parser at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from service_directory.app import _service_card_html, create_app
from service_directory.config import (
    ConfigError,
    HostAddress,
    RegistryConfig,
    Service,
    is_safe_docs_url,
    parse_config,
)

BASE_YAML = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
"""


def _all_down(url: str) -> bool:
    return False


# --- is_safe_docs_url: unit-level scheme allow-list ---------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid/docs",
        "https://example.invalid/docs",
        "https://example.invalid/docs?x=1#frag",
    ],
)
def test_is_safe_docs_url_allows_http_and_https(url):
    assert is_safe_docs_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(document.cookie)",
        "javascript:fetch('/api/federation/pairing-code')",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "JAVASCRIPT:alert(1)",  # scheme match must be case-insensitive
        "",
        "not-a-url-at-all",
        "//example.invalid/protocol-relative",  # empty scheme -- reject
    ],
)
def test_is_safe_docs_url_rejects_dangerous_and_malformed_schemes(url):
    assert is_safe_docs_url(url) is False


# --- config.py: fail closed on bad local admin input --------------------------


def test_config_rejects_javascript_scheme_docs_url():
    yaml_text = BASE_YAML + (
        '  - {name: "x", port: 80, docs_url: "javascript:alert(1)"}\n'
    )
    with pytest.raises(ConfigError, match="docs_url"):
        parse_config(yaml_text)


def test_config_rejects_data_scheme_docs_url():
    yaml_text = BASE_YAML + (
        '  - {name: "x", port: 80, docs_url: "data:text/html,<script>x</script>"}\n'
    )
    with pytest.raises(ConfigError, match="docs_url"):
        parse_config(yaml_text)


def test_config_accepts_https_docs_url():
    yaml_text = BASE_YAML + (
        '  - {name: "x", port: 80, docs_url: "https://example.invalid/docs"}\n'
    )
    cfg = parse_config(yaml_text)
    assert cfg.services[0].docs_url == "https://example.invalid/docs"


# --- render-time defense: peer-relayed docs_url never passes through config.py -


def _config_with(svc: Service) -> RegistryConfig:
    return RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[svc],
    )


def test_service_card_html_omits_link_for_javascript_scheme_docs_url():
    """Simulates a peer-relayed service dict (never validated by
    config.py's parser) carrying a malicious docs_url -- the render path
    must still refuse to emit it as a clickable href."""
    svc = {
        "name": "evil-svc",
        "description": None,
        "links": [],
        "category": None,
        "tags": [],
        "icon": None,
        "owner": None,
        "docs_url": "javascript:alert(document.cookie)",
        "origin": "compromised-peer",
    }
    html = _service_card_html(svc)
    assert "javascript:" not in html
    assert '<a class="docs"' not in html
    # Rest of the card still renders fine.
    assert "evil-svc" in html


def test_service_card_html_renders_link_for_https_docs_url():
    svc = {
        "name": "good-svc",
        "description": None,
        "links": [],
        "category": None,
        "tags": [],
        "icon": None,
        "owner": None,
        "docs_url": "https://example.invalid/docs",
        "origin": "trusted-node",
    }
    html = _service_card_html(svc)
    assert 'href="https://example.invalid/docs"' in html


def test_dashboard_html_end_to_end_never_emits_javascript_href_from_peer():
    """Full end-to-end: a stubbed peer fetch returns a service with a
    javascript: docs_url; the rendered dashboard HTML must not contain it
    as a live link, even though this value never touched config.py."""
    from service_directory.config import FederationConfig

    config = RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[Service(name="local-svc", port=80)],
        federation=FederationConfig(
            enabled=True,
            name="local-node",
            base_url="http://10.0.0.1:80",
            state_dir=None,
        ),
    )

    def stub_fetcher(peer, timeout):
        return [
            {
                "name": "peer-svc",
                "description": "from peer",
                "links": [],
                "docs_url": "javascript:alert(1)",
            }
        ]

    app = create_app(config, checker=_all_down, peer_fetcher=stub_fetcher)
    client = TestClient(app, client=("127.0.0.1", 12345))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "javascript:" not in resp.text
