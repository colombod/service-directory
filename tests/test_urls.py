from __future__ import annotations

from service_directory.urls import build_url, resolve_all


def test_build_url_default_path():
    assert build_url("192.168.1.86", 8088) == "http://192.168.1.86:8088/"


def test_build_url_explicit_path():
    assert build_url("100.111.191.22", 8080, "/") == "http://100.111.191.22:8080/"


def test_build_url_normalizes_missing_leading_slash():
    assert build_url("host", 80, "app") == "http://host:80/app"


def test_resolve_all_exact_url_for_every_service_x_address_pair(sample_config):
    resolved = resolve_all(sample_config)

    # Build the expected cartesian product directly from config, independent
    # of resolve_all's internals, so this test can actually catch bugs.
    expected = {}
    for svc in sample_config.services:
        for addr in sample_config.host_addresses:
            path = svc.path or "/"
            expected[(svc.name, addr.host)] = f"http://{addr.host}:{svc.port}{path}"

    assert len(resolved) == len(sample_config.services)
    for resolved_svc in resolved:
        assert len(resolved_svc.links) == len(sample_config.host_addresses)
        for link in resolved_svc.links:
            key = (resolved_svc.name, link.host)
            assert key in expected, f"unexpected pair {key}"
            assert link.url == expected[key], (
                f"URL mismatch for {key}: got {link.url}, want {expected[key]}"
            )
            del expected[key]

    assert expected == {}, f"missing pairs: {expected}"


def test_resolve_all_preserves_tailnet_first_order(sample_config):
    resolved = resolve_all(sample_config)
    for svc in resolved:
        labels = [link.label for link in svc.links]
        assert labels == ["Tailnet", "LAN"], (
            f"expected tailnet-first order, got {labels} for service {svc.name}"
        )
        assert svc.links[0].host == "100.111.191.22"
        assert svc.links[1].host == "192.168.1.86"


def test_resolve_service_names_and_descriptions_preserved(sample_config):
    resolved = resolve_all(sample_config)
    by_name = {svc.name: svc for svc in resolved}
    assert by_name["Resolve"].description == "Video editor"
    assert by_name["muxplex"].description is None
    assert by_name["browser-bridge hub"].name == "browser-bridge hub"
