from __future__ import annotations

from pathlib import Path

from service_directory.config import load_config
from service_directory.urls import resolve_all

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_shipped_sample_config_loads_and_matches_spec():
    cfg = load_config(str(REPO_ROOT / "config.sample.yaml"))

    hosts = {(h.label, h.host) for h in cfg.host_addresses}
    assert hosts == {("Tailnet", "100.111.191.22"), ("LAN", "192.168.1.86")}
    assert cfg.host_addresses[0].label == "Tailnet"  # tailnet-first

    names_ports = {(s.name, s.port) for s in cfg.services}
    assert names_ports == {
        ("Resolve", 8080),
        ("Context Intelligence", 8000),
        ("muxplex", 8088),
        ("muxterm", 8311),
        ("browser-bridge hub", 8900),
    }


def test_shipped_sample_config_resolves_without_error():
    cfg = load_config(str(REPO_ROOT / "config.sample.yaml"))
    resolved = resolve_all(cfg)
    assert len(resolved) == 5
    for svc in resolved:
        assert len(svc.links) == 2
        for link in svc.links:
            assert link.url.startswith("http://")
