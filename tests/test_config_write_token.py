from __future__ import annotations

import pytest
from service_directory.config import ConfigError, FederationConfig, parse_config

BASE_YAML = """
host_addresses:
  - {label: "LAN", host: "10.0.0.1"}
services:
  - {name: "svc", port: 80}
"""


def test_require_write_token_defaults_false_when_absent():
    cfg = parse_config(BASE_YAML)
    assert cfg.federation.require_write_token is False


def test_require_write_token_parses_true():
    yaml_text = BASE_YAML + "federation:\n  require_write_token: true\n"
    cfg = parse_config(yaml_text)
    assert cfg.federation.require_write_token is True


def test_require_write_token_independent_of_require_read_token():
    yaml_text = BASE_YAML + (
        "federation:\n  require_read_token: true\n  require_write_token: false\n"
    )
    cfg = parse_config(yaml_text)
    assert cfg.federation.require_read_token is True
    assert cfg.federation.require_write_token is False


def test_require_write_token_malformed_raises_clear_error():
    yaml_text = BASE_YAML + "federation:\n  require_write_token: not-a-bool\n"
    with pytest.raises(ConfigError, match="require_write_token"):
        parse_config(yaml_text)


def test_legacy_federation_block_without_require_write_token_still_works():
    """A federation block using only pre-existing keys must parse
    identically -- require_write_token defaults to False."""
    yaml_text = BASE_YAML + (
        "federation:\n"
        "  enabled: true\n"
        "  name: my-node\n"
        "  base_url: http://10.0.0.1:80\n"
    )
    cfg = parse_config(yaml_text)
    assert cfg.federation.require_write_token is False
    assert cfg.federation == FederationConfig(
        enabled=True, name="my-node", base_url="http://10.0.0.1:80"
    )
