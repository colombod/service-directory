from __future__ import annotations

import pytest
from service_directory.config import ConfigError, load_config, parse_config


def test_parse_valid_config_shape(sample_config):
    assert len(sample_config.host_addresses) == 2
    assert sample_config.host_addresses[0].label == "Tailnet"
    assert sample_config.host_addresses[0].host == "100.111.191.22"
    assert sample_config.host_addresses[1].label == "LAN"
    assert sample_config.host_addresses[1].host == "192.168.1.86"

    assert len(sample_config.services) == 5
    resolve = sample_config.services[0]
    assert resolve.name == "Resolve"
    assert resolve.port == 8080
    assert resolve.path == "/"
    assert resolve.description == "Video editor"

    muxplex = sample_config.services[2]
    assert muxplex.name == "muxplex"
    assert muxplex.port == 8088
    # path defaults to "/" when omitted
    assert muxplex.path == "/"
    assert muxplex.description is None


def test_load_config_from_path(sample_config_path):
    cfg = load_config(sample_config_path)
    assert len(cfg.services) == 5
    assert cfg.host_addresses[0].label == "Tailnet"


def test_load_config_missing_env_var(monkeypatch):
    monkeypatch.delenv("SERVICE_REGISTRY_CONFIG", raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_load_config_nonexistent_file():
    with pytest.raises(ConfigError, match="cannot read file"):
        load_config("/nonexistent/path/does/not/exist.yaml")


@pytest.mark.parametrize(
    "bad_yaml,expected_match",
    [
        ("", "empty"),
        ("not: valid: yaml: [", "not valid YAML"),
        ("just a string", "must be a mapping"),
        ("host_addresses: []\nservices: []", "must not be empty"),
        ("services:\n  - {name: x, port: 1}", "host_addresses"),
        ("host_addresses:\n  - {label: a, host: b}", "services"),
        (
            "host_addresses: not-a-list\nservices:\n  - {name: x, port: 1}",
            "must be a list",
        ),
        (
            "host_addresses:\n  - {host: 1.2.3.4}\nservices:\n  - {name: x, port: 1}",
            "label",
        ),
        (
            "host_addresses:\n  - {label: a, host: b}\nservices:\n  - {name: x}",
            "port",
        ),
        (
            'host_addresses:\n  - {label: a, host: b}\nservices:\n  - {name: x, port: "not-an-int"}',
            "port",
        ),
        (
            "host_addresses:\n  - {label: a, host: b}\nservices:\n  - {port: 80}",
            "name",
        ),
        (
            "host_addresses:\n  - not-a-mapping\nservices:\n  - {name: x, port: 1}",
            "host_addresses",
        ),
    ],
)
def test_malformed_config_raises_clear_error(bad_yaml, expected_match):
    with pytest.raises(ConfigError, match=expected_match):
        parse_config(bad_yaml)


def test_malformed_config_never_raises_raw_exception():
    """A malformed config must yield ConfigError, not e.g. a raw
    yaml.YAMLError, KeyError, TypeError, or AttributeError bubbling up."""
    bad_inputs = [
        "[1, 2, 3]",
        "{",
        "host_addresses: 5\nservices: 5",
        None,
    ]
    for bad in bad_inputs:
        if bad is None:
            continue
        try:
            parse_config(bad)
        except ConfigError:
            pass  # expected
        except Exception as exc:  # pragma: no cover - failure path
            pytest.fail(
                f"Expected ConfigError for input {bad!r}, got {type(exc)}: {exc}"
            )
