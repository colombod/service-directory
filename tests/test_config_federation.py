from __future__ import annotations

import pytest
from service_directory.config import ConfigError, FederationConfig, parse_config, resolve_state_dir

BASE_YAML = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "svc", port: 80}
"""


def test_federation_defaults_when_absent():
    cfg = parse_config(BASE_YAML)
    assert cfg.federation == FederationConfig()
    assert cfg.federation.enabled is False


def test_federation_parses_when_present():
    yaml_text = BASE_YAML + (
        "federation:\n"
        "  enabled: true\n"
        "  name: my-node\n"
        "  base_url: http://10.0.0.1:80\n"
        "  state_dir: /tmp/sd-state\n"
        "  require_read_token: true\n"
    )
    cfg = parse_config(yaml_text)
    assert cfg.federation.enabled is True
    assert cfg.federation.name == "my-node"
    assert cfg.federation.base_url == "http://10.0.0.1:80"
    assert cfg.federation.state_dir == "/tmp/sd-state"
    assert cfg.federation.require_read_token is True


def test_federation_partial_keys_use_defaults():
    yaml_text = BASE_YAML + "federation:\n  enabled: true\n"
    cfg = parse_config(yaml_text)
    assert cfg.federation.enabled is True
    assert cfg.federation.name == ""
    assert cfg.federation.require_read_token is False


@pytest.mark.parametrize(
    "bad_federation,expected_match",
    [
        ("federation: not-a-mapping\n", "federation.*must be a mapping"),
        ("federation:\n  enabled: not-a-bool\n", "enabled"),
        ("federation:\n  name: 5\n", "name"),
        ("federation:\n  require_read_token: not-a-bool\n", "require_read_token"),
    ],
)
def test_malformed_federation_raises_clear_error(bad_federation, expected_match):
    with pytest.raises(ConfigError, match=expected_match):
        parse_config(BASE_YAML + bad_federation)


def test_resolve_state_dir_prefers_config_value(monkeypatch):
    monkeypatch.setenv("SERVICE_REGISTRY_STATE_DIR", "/env/state")
    cfg = parse_config(
        BASE_YAML + "federation:\n  state_dir: /config/state\n"
    )
    assert resolve_state_dir(cfg) == "/config/state"


def test_resolve_state_dir_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("SERVICE_REGISTRY_STATE_DIR", "/env/state")
    cfg = parse_config(BASE_YAML)
    assert resolve_state_dir(cfg) == "/env/state"


def test_resolve_state_dir_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("SERVICE_REGISTRY_STATE_DIR", raising=False)
    cfg = parse_config(BASE_YAML)
    result = resolve_state_dir(cfg)
    assert result  # non-empty
    assert "service-directory" in result
