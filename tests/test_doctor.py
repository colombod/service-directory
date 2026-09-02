from __future__ import annotations

from dataclasses import dataclass

from service_directory.config import ConfigError
from service_directory.doctor import (
    STATUS_FAIL,
    STATUS_OK,
    STATUS_WARN,
    CheckResult,
    DoctorDependencies,
    check_bind_port,
    check_config,
    check_install_source,
    check_peer_reachability,
    check_python_version,
    check_service_status,
    format_checklist,
    run_and_format,
    run_doctor,
)
from service_directory.install_source import InstallSource
from service_directory.service_manager import ServiceResult, UnsupportedPlatformError

# --- individual checks (stubbed seams, no real system mutation) -----------


def test_check_python_version_ok_for_supported_version():
    result = check_python_version((3, 12))
    assert result.status == STATUS_OK
    assert result.name == "Python version"


def test_check_python_version_fails_for_unsupported_version():
    result = check_python_version((3, 8))
    assert result.status == STATUS_FAIL


def test_check_config_reports_ok_for_valid_config(sample_config):
    result, config = check_config(None, loader=lambda path: sample_config)
    assert result.status == STATUS_OK
    assert config is sample_config
    assert "5 service" in result.message


def test_check_config_reports_fail_for_invalid_config():
    def bad_loader(path):
        raise ConfigError("Invalid config: missing required key 'services'")

    result, config = check_config(None, loader=bad_loader)
    assert result.status == STATUS_FAIL
    assert config is None
    assert "services" in result.message


def test_check_bind_port_ok_when_available():
    result = check_bind_port("127.0.0.1", 8080, bind_checker=lambda h, p: True)
    assert result.status == STATUS_OK


def test_check_bind_port_warns_when_in_use():
    result = check_bind_port("127.0.0.1", 80, bind_checker=lambda h, p: False)
    assert result.status == STATUS_WARN
    assert "in use" in result.message


def test_check_peer_reachability_ok_with_no_peers():
    result = check_peer_reachability([])
    assert result.status == STATUS_OK
    assert "no trusted peers" in result.message


def test_check_peer_reachability_ok_when_all_reachable():
    @dataclass
    class FakePeer:
        name: str
        base_url: str

    peers = [FakePeer("node-a", "http://a"), FakePeer("node-b", "http://b")]
    result = check_peer_reachability(peers, checker=lambda url: True)
    assert result.status == STATUS_OK
    assert "2/2" in result.message


def test_check_peer_reachability_warns_on_unreachable_peer():
    @dataclass
    class FakePeer:
        name: str
        base_url: str

    peers = [FakePeer("node-a", "http://a"), FakePeer("node-b", "http://b")]
    result = check_peer_reachability(peers, checker=lambda url: url == "http://a")
    assert result.status == STATUS_WARN
    assert "node-b" in result.message
    assert "1/2" in result.message


def test_check_peer_reachability_swallows_checker_exception():
    @dataclass
    class FakePeer:
        name: str
        base_url: str

    peers = [FakePeer("node-a", "http://a")]

    def exploding_checker(url):
        raise RuntimeError("boom")

    result = check_peer_reachability(peers, checker=exploding_checker)
    assert result.status == STATUS_WARN
    assert "node-a" in result.message


def test_check_install_source_editable_is_ok():
    source = InstallSource(kind="editable", version="0.1.0", editable=True)
    result = check_install_source(detector=lambda: source)
    assert result.status == STATUS_OK
    assert "editable" in result.message


def test_check_install_source_pypi_up_to_date_is_ok():
    source = InstallSource(kind="pypi", version="0.1.0")
    result = check_install_source(
        detector=lambda: source, update_checker_fn=lambda s: None
    )
    assert result.status == STATUS_OK
    assert "up to date" in result.message


def test_check_install_source_pypi_outdated_is_warn():
    source = InstallSource(kind="pypi", version="0.1.0")
    result = check_install_source(
        detector=lambda: source, update_checker_fn=lambda s: "0.2.0"
    )
    assert result.status == STATUS_WARN
    assert "0.2.0" in result.message


def test_check_install_source_unknown_is_warn():
    source = InstallSource(kind="unknown", version="unknown")
    result = check_install_source(
        detector=lambda: source, update_checker_fn=lambda s: None
    )
    assert result.status == STATUS_WARN


def test_check_service_status_reports_from_stubbed_manager():
    class FakeManager:
        def status(self):
            return ServiceResult(ok=True, message="active")

    result = check_service_status(manager_factory=lambda: FakeManager())
    assert result.status == STATUS_OK
    assert result.message == "active"


def test_check_service_status_warns_when_not_running():
    class FakeManager:
        def status(self):
            return ServiceResult(ok=False, message="inactive")

    result = check_service_status(manager_factory=lambda: FakeManager())
    assert result.status == STATUS_WARN


def test_check_service_status_handles_unsupported_platform():
    def factory():
        raise UnsupportedPlatformError("no service manager for this platform")

    result = check_service_status(manager_factory=factory)
    assert result.status == STATUS_WARN
    assert "platform" in result.message


# --- run_doctor: full checklist structure, never crashes -------------------


def test_run_doctor_returns_a_check_per_area(sample_config):
    deps = DoctorDependencies(
        loader=lambda path: sample_config,
        bind_checker=lambda h, p: True,
        identity_loader=lambda state_dir: type("I", (), {"device_id": "test-id"})(),
        peers_loader=lambda state_dir: [],
        peer_reachability_checker=lambda url: True,
        install_source_detector=lambda: InstallSource(kind="editable", version="0.1.0"),
        service_manager_factory=lambda: type(
            "M", (), {"status": lambda self: ServiceResult(ok=True, message="active")}
        )(),
    )
    results = run_doctor(deps)
    names = {r.name for r in results}
    assert names == {
        "Python version",
        "Config",
        "Bind port",
        "Device identity",
        "Federation peers",
        "Install source",
        "Service status",
    }
    assert all(isinstance(r, CheckResult) for r in results)
    assert all(r.status in (STATUS_OK, STATUS_WARN, STATUS_FAIL) for r in results)


def test_run_doctor_never_crashes_on_bad_config():
    def bad_loader(path):
        raise ConfigError("Invalid config: file is empty")

    deps = DoctorDependencies(loader=bad_loader, bind_checker=lambda h, p: True)
    results = run_doctor(deps)
    # Must still produce a full checklist, not crash/raise.
    assert len(results) == len(
        {
            "Python version",
            "Config",
            "Bind port",
            "Device identity",
            "Federation peers",
            "Install source",
            "Service status",
        }
    )
    config_result = next(r for r in results if r.name == "Config")
    assert config_result.status == STATUS_FAIL
    identity_result = next(r for r in results if r.name == "Device identity")
    assert identity_result.status == STATUS_WARN


def test_run_doctor_never_crashes_when_a_check_raises(sample_config):
    """A misbehaving injected seam (raises instead of returning) must be
    caught -- doctor produces a 'fail' line for it, never propagates."""

    def exploding_bind_checker(h, p):
        raise RuntimeError("socket exploded")

    deps = DoctorDependencies(
        loader=lambda path: sample_config,
        bind_checker=exploding_bind_checker,
    )
    results = run_doctor(deps)
    bind_result = next(r for r in results if r.name == "Bind port")
    assert bind_result.status == STATUS_FAIL
    assert "errored" in bind_result.message


def test_format_checklist_includes_symbol_and_message_per_line():
    results = [
        CheckResult(name="A", status=STATUS_OK, message="all good"),
        CheckResult(name="B", status=STATUS_WARN, message="careful"),
        CheckResult(name="C", status=STATUS_FAIL, message="broken"),
    ]
    text = format_checklist(results, color=False)
    lines = text.splitlines()
    assert len(lines) == 3
    assert "\u2713 A: all good" in lines[0]
    assert "! B: careful" in lines[1]
    assert "\u2717 C: broken" in lines[2]


def test_format_checklist_with_color_includes_ansi_codes():
    results = [CheckResult(name="A", status=STATUS_OK, message="good")]
    text = format_checklist(results, color=True)
    assert "\033[" in text


def test_run_and_format_all_ok_true_when_no_failures(sample_config):
    deps = DoctorDependencies(
        loader=lambda path: sample_config,
        bind_checker=lambda h, p: True,
        peer_reachability_checker=lambda url: True,
        install_source_detector=lambda: InstallSource(kind="editable", version="0.1.0"),
        service_manager_factory=lambda: type(
            "M", (), {"status": lambda self: ServiceResult(ok=True, message="active")}
        )(),
    )
    text, all_ok = run_and_format(deps, color=False)
    assert isinstance(text, str)
    assert all_ok is True


def test_run_and_format_all_ok_false_when_config_invalid():
    def bad_loader(path):
        raise ConfigError("bad")

    deps = DoctorDependencies(loader=bad_loader, bind_checker=lambda h, p: True)
    text, all_ok = run_and_format(deps, color=False)
    assert all_ok is False
    assert "Config" in text
