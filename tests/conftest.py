from __future__ import annotations

import pytest

SAMPLE_CONFIG_YAML = """
host_addresses:
  - {label: "Tailnet", host: "100.111.191.22"}
  - {label: "LAN", host: "192.168.1.86"}
services:
  - {name: "Resolve", port: 8080, path: "/", description: "Video editor"}
  - {name: "Context Intelligence", port: 8000, path: "/"}
  - {name: "muxplex", port: 8088}
  - {name: "muxterm", port: 8311}
  - {name: "browser-bridge hub", port: 8900}
"""


@pytest.fixture
def sample_config_path(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(SAMPLE_CONFIG_YAML)
    return str(p)


@pytest.fixture
def sample_config():
    from service_directory.config import parse_config

    return parse_config(SAMPLE_CONFIG_YAML)
