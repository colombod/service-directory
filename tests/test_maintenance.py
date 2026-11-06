"""Hermetic maintenance contracts: source, auth, durable lifecycle and launch isolation."""
from __future__ import annotations

import builtins
import functools
import importlib.util
import json
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import service_directory.maintenance as maintenance_module
from service_directory.app import create_app
from service_directory.config import FederationConfig, HostAddress, RegistryConfig
from service_directory.install_source import InstallSource, check_for_update, detect_install_source
from service_directory.maintenance import (
    Maintenance, MaintenanceError, atomic_json, check_source, default_capability, git_revision,
    launch_worker, observe_transient_unit, run_worker, serving_process_identity_reason,
)
from service_directory.service_manager import ServiceResult
from service_directory.trust_store import PeerRecord, upsert_peer
from service_directory.upgrade import UpgradeResult, reinstall_command_for_source, run_upgrade
from service_directory.write_token import issue_write_token


OLD = 'a' * 40
NEW = 'b' * 40
SOURCE = InstallSource(kind='git', version='0.1.0', url='https://github.com/example/directory.git',
                       commit_id=OLD, requested_revision='main')


def maintenance(tmp_path, **kwargs):
    defaults = dict(source_detector=lambda: SOURCE, capability=lambda source: None,
                    checker=lambda source: {'update_available': True, 'latest_revision': NEW, 'latest_version': None},
                    launcher=lambda state, job: None, time_fn=lambda: 1000)
    return Maintenance(str(tmp_path), **(defaults | kwargs))


def config(tmp_path, **kwargs):
    return RegistryConfig(host_addresses=[HostAddress(label='LAN', host='10.0.0.1')], services=[],
                          federation=FederationConfig(state_dir=str(tmp_path), **kwargs))


IDENTITY_CGROUP = '/user.slice/user-1000.slice/user@1000.service/app.slice/service-directory.service'


def load_maintenance_module_without_fcntl(monkeypatch):
    alias = 'service_directory._maintenance_without_fcntl_test'
    module_path = Path(__file__).resolve().parents[1] / 'src' / 'service_directory' / 'maintenance.py'
    spec = importlib.util.spec_from_file_location(alias, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name == 'fcntl':
            raise ModuleNotFoundError("No module named 'fcntl'")
        return real_import(name, globals, locals, fromlist, level)

    sys.modules.pop(alias, None)
    sys.modules[alias] = module
    monkeypatch.setattr(builtins, '__import__', fake_import)
    spec.loader.exec_module(module)
    return module


def write_proc_identity(proc_root: Path, pid: int, *, cgroup: str, entrypoint: Path, serve_arg: str = 'serve'):
    proc_dir = proc_root / str(pid)
    proc_dir.mkdir(parents=True, exist_ok=True)
    (proc_dir / 'cgroup').write_text(f'0::{cgroup}\n')
    (proc_dir / 'cmdline').write_bytes(
        b'\0'.join(part.encode() for part in (sys.executable, str(entrypoint), serve_arg)) + b'\0'
    )
    (proc_dir / 'exe').symlink_to(sys.executable)


def systemd_show_text(*, fragment_path: Path, main_pid: int, control_group: str,
                      execstart_path: Path, unit_type: str = 'simple', serve_arg: str = 'serve') -> str:
    return (
        f'FragmentPath={fragment_path}\n'
        f'MainPID={main_pid}\n'
        f'ControlGroup={control_group}\n'
        f'ExecStart={{ path={execstart_path} ; argv[]={execstart_path} {serve_arg} ; '
        f'ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid={main_pid} ; '
        f'code=(null) ; status=0/0 }}\n'
        f'Type={unit_type}\n'
    )


def make_runner(show_output: str, *, version_output: str = 'systemd 255 (255)'):
    def runner(command, **kwargs):
        if command == ['systemd-run', '--version']:
            return subprocess.CompletedProcess(command, 0, version_output, '')
        if command[:3] == ['systemctl', '--user', 'show']:
            return subprocess.CompletedProcess(command, 0, show_output, '')
        raise AssertionError(f'unexpected command: {command!r}')
    return runner


def test_observe_transient_unit_parses_live_collected_status():
    observation = observe_transient_unit(
        'a' * 32,
        runner=lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            'LoadState=loaded\nActiveState=active\nSubState=running\nResult=success\nMainPID=4242\nignored-line\n',
            '',
        ),
    )

    assert observation is not None
    assert observation.active_state == 'active'
    assert observation.sub_state == 'running'
    assert observation.result == 'success'
    assert observation.main_pid == 4242
    assert observation.unit_not_found is False


def test_observe_transient_unit_tolerates_malformed_fields():
    observation = observe_transient_unit(
        'b' * 32,
        runner=lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            'LoadState=loaded\nActiveState=\nSubState=dead\nResult=\nMainPID=not-a-pid\nmalformed\n',
            '',
        ),
    )

    assert observation is not None
    assert observation.active_state is None
    assert observation.sub_state == 'dead'
    assert observation.result is None
    assert observation.main_pid is None
    assert observation.unit_not_found is False


def test_observe_transient_unit_marks_missing_transient_unit_without_claiming_no_execution():
    observation = observe_transient_unit(
        'c' * 32,
        runner=lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            1,
            '',
            'Unit service-directory-update-cccccccccccccccccccccccccccccccc could not be found.\n',
        ),
    )

    assert observation is not None
    assert observation.active_state is None
    assert observation.sub_state is None
    assert observation.result is None
    assert observation.main_pid is None
    assert observation.unit_not_found is True


def build_identity_fixture(tmp_path, *, current_pid: int = 7674, main_pid: int | None = None,
                           control_group: str = IDENTITY_CGROUP, current_cgroup: str | None = None,
                           current_entrypoint: Path | None = None, execstart_path: Path | None = None,
                           fragment_path: Path | None = None, unit_type: str = 'simple',
                           execstart_serve_arg: str = 'serve'):
    unit_path = tmp_path / 'service-directory.service'
    unit_path.write_text('[Service]\n')
    current_entrypoint = current_entrypoint or (tmp_path / 'service-directory')
    current_entrypoint.parent.mkdir(parents=True, exist_ok=True)
    current_entrypoint.write_text('#!/bin/sh\n')
    execstart_path = execstart_path or current_entrypoint
    execstart_path.parent.mkdir(parents=True, exist_ok=True)
    if not execstart_path.exists():
        execstart_path.write_text('#!/bin/sh\n')
    fragment_path = fragment_path or unit_path
    fragment_path.parent.mkdir(parents=True, exist_ok=True)
    if not fragment_path.exists():
        fragment_path.write_text('[Service]\n')
    proc_root = tmp_path / 'proc'
    write_proc_identity(
        proc_root,
        current_pid,
        cgroup=current_cgroup or control_group,
        entrypoint=current_entrypoint,
    )
    show_output = systemd_show_text(
        fragment_path=fragment_path,
        main_pid=main_pid or current_pid,
        control_group=control_group,
        execstart_path=execstart_path,
        unit_type=unit_type,
        serve_arg=execstart_serve_arg,
    )
    manager_factory = lambda: SimpleNamespace(unit_path=str(unit_path), unit_name='service-directory.service')
    return make_runner(show_output), proc_root, manager_factory, unit_path, current_entrypoint


def write_job(state: Maintenance, job_id: str, *, status: str = 'queued', message: str | None = None,
              steps: list[str] | None = None, started_at: float = 1000, finished_at: float | None = None):
    default_message = {
        'queued': 'Independent updater queued.',
        'running': 'Updating; the directory may disconnect while its service restarts.',
        'succeeded': 'Update completed and the restarted directory responded.',
        'failed': 'Update did not complete. Check service-directory logs/doctor on this node.',
    }
    atomic_json(
        state.directory / f'{job_id}.json',
        {
            'id': job_id,
            'status': status,
            'message': message or default_message[status],
            'steps': steps or [],
            'started_at': started_at,
            'finished_at': finished_at,
        },
    )


def test_instance_info_probe_url_uses_loopback_for_ipv4_wildcard():
    assert maintenance_module.instance_info_probe_url('0.0.0.0', 8085) == 'http://127.0.0.1:8085/api/instance-info'


def test_instance_info_probe_url_uses_ipv6_loopback_for_ipv6_wildcard():
    assert maintenance_module.instance_info_probe_url('::', 8085) == 'http://[::1]:8085/api/instance-info'


def test_instance_info_probe_url_brackets_ipv6_literals():
    assert maintenance_module.instance_info_probe_url('2001:db8::1', 8085) == 'http://[2001:db8::1]:8085/api/instance-info'


def test_instance_info_probe_url_percent_encodes_scoped_ipv6_for_urllib_transport(monkeypatch):
    url = maintenance_module.instance_info_probe_url('fe80::1%eth0', 8085)
    parsed = urllib.parse.urlsplit(url)
    assert parsed.netloc == '[fe80::1%25eth0]:8085'
    assert parsed.hostname == 'fe80::1%25eth0'

    captured = {}

    def fake_create_connection(address, timeout=None, source_address=None, *, all_errors=False):
        captured['address'] = address
        captured['timeout'] = timeout
        raise OSError('stop')

    monkeypatch.setattr(socket, 'create_connection', fake_create_connection)

    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(url, timeout=1)

    assert captured == {'address': ('fe80::1%eth0', 8085), 'timeout': 1}


def test_verify_restarted_service_uses_configured_host_not_hardcoded_loopback(monkeypatch):
    requests = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def urlopen(url, timeout):
        requests.append((url, timeout))
        if url == 'http://192.0.2.44:8085/api/instance-info':
            return Response({'version': '0.1.0'})
        raise AssertionError(f'unexpected probe url: {url}')

    monkeypatch.setenv('SERVICE_REGISTRY_HOST', '192.0.2.44')
    monkeypatch.setenv('SERVICE_REGISTRY_PORT', '8085')
    monkeypatch.setattr(
        'service_directory.maintenance.SystemdUserServiceManager',
        lambda: SimpleNamespace(status=lambda: SimpleNamespace(ok=True)),
    )
    monkeypatch.setattr('service_directory.maintenance.urllib.request.urlopen', urlopen)
    monkeypatch.setattr('service_directory.maintenance.time.sleep', lambda *_: None)

    assert maintenance_module.verify_restarted_service() is True
    assert requests == [('http://192.0.2.44:8085/api/instance-info', 1)]

    requests.clear()
    monkeypatch.setattr(
        'service_directory.maintenance.SystemdUserServiceManager',
        lambda: SimpleNamespace(status=lambda: SimpleNamespace(ok=False)),
    )
    assert maintenance_module.verify_restarted_service() is False
    assert requests == []

    requests.clear()
    monkeypatch.setattr(
        'service_directory.maintenance.SystemdUserServiceManager',
        lambda: SimpleNamespace(status=lambda: SimpleNamespace(ok=True)),
    )
    monkeypatch.setattr(
        'service_directory.maintenance.urllib.request.urlopen',
        lambda url, timeout: Response({}),
    )
    assert maintenance_module.verify_restarted_service() is False
    assert requests == []


def test_verify_restarted_service_uses_configured_scoped_ipv6_host(monkeypatch):
    requests = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def urlopen(url, timeout):
        requests.append((url, timeout))
        assert urllib.parse.urlsplit(url).netloc == '[fe80::1%25eth0]:8085'
        return Response({'version': '0.1.0'})

    monkeypatch.setenv('SERVICE_REGISTRY_HOST', 'fe80::1%eth0')
    monkeypatch.setenv('SERVICE_REGISTRY_PORT', '8085')
    monkeypatch.setattr(
        'service_directory.maintenance.SystemdUserServiceManager',
        lambda: SimpleNamespace(status=lambda: SimpleNamespace(ok=True)),
    )
    monkeypatch.setattr('service_directory.maintenance.urllib.request.urlopen', urlopen)
    monkeypatch.setattr('service_directory.maintenance.time.sleep', lambda *_: None)

    assert maintenance_module.verify_restarted_service() is True
    assert requests == [('http://[fe80::1%25eth0]:8085/api/instance-info', 1)]


def test_probe_url_rejects_invalid_host_or_port_injection():
    for host in (
        'http://127.0.0.1',
        'user@127.0.0.1',
        '127.0.0.1:8085',
        'host/path',
        'fe80::1%',
        'fe80::1%eth/0',
        'fe80::1%eth0%extra',
    ):
        with pytest.raises(ValueError):
            maintenance_module.instance_info_probe_url(host, 8085)

    for port in (0, 65536, '8085/path', '8085#frag'):
        with pytest.raises(ValueError):
            maintenance_module.instance_info_probe_url('127.0.0.1', port)


def test_pep610_preserves_requested_branch_and_unqualified_head():
    class Distribution:
        version = '0.1.0'
        def read_text(self, name):
            return json.dumps({'url': SOURCE.url, 'vcs_info': {'vcs': 'git', 'commit_id': OLD,
                                                                'requested_revision': 'main'}})
    detected = detect_install_source(distribution_factory=lambda name: Distribution())
    assert detected.requested_revision == 'main'
    assert f'git+{SOURCE.url}@main' in reinstall_command_for_source(detected)
    assert '--refresh' in reinstall_command_for_source(detected)
    class Unqualified(Distribution):
        def read_text(self, name):
            return json.dumps({'url': SOURCE.url, 'vcs_info': {'vcs': 'git', 'commit_id': OLD}})
    assert detect_install_source(distribution_factory=lambda name: Unqualified()).requested_revision == 'HEAD'


def test_source_check_respects_semantic_version_order_and_unknown():
    for latest, expected in [('0.9.0', False), ('1.0.0', False), ('1.0.1', True), (None, None), ('bad', None)]:
        result = check_source(InstallSource(kind='pypi', version='1.0.0'),
                              pypi_checker=lambda name, timeout: latest)
        assert result['update_available'] is expected
    assert check_source(SOURCE, git_checker=lambda source: None)['update_available'] is None
    assert check_source(SOURCE, git_checker=lambda source: NEW)['update_available'] is True
    assert check_source(SOURCE, git_checker=lambda source: OLD)['update_available'] is False


def test_doctor_update_check_does_not_report_older_or_invalid_versions():
    source = InstallSource(kind='pypi', version='1.0.0')
    assert check_for_update(source, checker=lambda name, timeout: '0.9.0') is None
    assert check_for_update(source, checker=lambda name, timeout: 'invalid') is None


def test_git_lookup_is_bounded_noninteractive_and_branch_specific():
    commands = []
    def runner(command, **kwargs):
        commands.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, f'{NEW}\trefs/heads/main\n', '')
    assert git_revision(SOURCE, runner) == NEW
    command, args = commands[0]
    assert command == ['git', 'ls-remote', '--', SOURCE.url, 'refs/heads/main', 'refs/tags/main', 'refs/tags/main^{}']
    assert args['timeout'] == 5
    assert args['env']['GIT_TERMINAL_PROMPT'] == '0'
    assert 'BatchMode=yes' in args['env']['GIT_SSH_COMMAND']


def test_git_lookup_rejects_unsafe_transport_and_handles_missing_remote():
    def never(*args, **kwargs):
        raise AssertionError('must not execute')
    assert git_revision(InstallSource(kind='git', version='1', url='ext::bad'), never) is None
    pinned = InstallSource(kind='git', version='1', url=SOURCE.url, requested_revision=OLD)
    assert git_revision(pinned, never) == OLD
    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired('git', 5)
    assert git_revision(SOURCE, timed_out) is None


def test_status_does_not_check_network_and_is_unknown_until_checked(tmp_path):
    calls = []
    state = maintenance(tmp_path, checker=lambda source: calls.append(source) or {})
    assert state.status()['update_available'] is None
    assert calls == []
    state = maintenance(tmp_path)
    assert state.check()['update_available'] is True
    assert maintenance(tmp_path).status()['latest_revision'] == NEW
    updated = InstallSource(kind='git', version='0.1.0', commit_id=NEW)
    assert maintenance(tmp_path, source_detector=lambda: updated).status()['update_available'] is None


def test_job_persists_across_instances_and_blocks_concurrent_update(tmp_path):
    started = []
    state = maintenance(tmp_path, launcher=lambda path, job: started.append(job))
    job = state.start()
    assert job['status'] == 'queued'
    assert maintenance(tmp_path).status()['job'] == job
    with pytest.raises(MaintenanceError) as caught:
        maintenance(tmp_path).start()
    assert caught.value.status_code == 409
    assert started == [job['id']]
    assert state.job('../../secrets') is None


def test_concurrent_requests_launch_only_one_worker(tmp_path):
    launched = []
    state = maintenance(tmp_path, launcher=lambda path, job: launched.append(job))
    statuses = []
    def start():
        try:
            statuses.append(state.start()['status'])
        except MaintenanceError as error:
            statuses.append(error.status_code)
    threads = [threading.Thread(target=start) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sorted(map(str, statuses)) == ['409', 'queued']
    assert len(launched) == 1


def test_unsupported_and_launcher_failure_do_not_claim_success(tmp_path):
    blocked = maintenance(tmp_path, capability=lambda source: 'editable install')
    with pytest.raises(MaintenanceError) as error:
        blocked.start()
    assert error.value.status_code == 422
    def broken(*args):
        raise FileNotFoundError('token-in-source-url')
    state = maintenance(tmp_path, launcher=broken)
    with pytest.raises(MaintenanceError) as error:
        state.start()
    assert error.value.status_code == 503
    job = state.status()['job']
    assert job['status'] == 'failed'
    assert 'token-in-source-url' not in str(job)


def test_interrupted_jobs_expire_honestly_and_can_retry(tmp_path):
    state = maintenance(tmp_path)
    job = state.start()
    later = maintenance(tmp_path, time_fn=lambda: 2000)
    assert later.status()['job']['status'] == 'failed'
    assert later.start()['id'] != job['id']


def test_launcher_file_not_found_marks_failed_503(tmp_path):
    def missing(*args):
        raise FileNotFoundError('systemd-run')

    state = maintenance(tmp_path, launcher=missing)

    with pytest.raises(MaintenanceError) as error:
        state.start()

    assert error.value.status_code == 503
    job = state.status()['job']
    assert job['status'] == 'failed'
    assert job['finished_at'] is not None


def test_launcher_permission_error_marks_failed_503(tmp_path):
    def denied(*args):
        raise PermissionError('systemd-run')

    state = maintenance(tmp_path, launcher=denied)

    with pytest.raises(MaintenanceError) as error:
        state.start()

    assert error.value.status_code == 503
    job = state.status()['job']
    assert job['status'] == 'failed'
    assert job['finished_at'] is not None


def test_worker_finished_before_launcher_timeout_is_not_clobbered(tmp_path):
    def launcher(state_dir, job_id):
        worker = threading.Thread(
            target=run_worker,
            args=(state_dir, job_id),
            kwargs={
                'upgrader': lambda **kwargs: UpgradeResult(True, False, '', ['stop', 'reinstall', 'verify']),
                'verifier': lambda: True,
            },
        )
        worker.start()
        worker.join()
        raise subprocess.TimeoutExpired('systemd-run', 10)

    state = maintenance(tmp_path, launcher=launcher)
    job = state.start()
    assert job['status'] == 'succeeded'
    assert state.job(job['id'])['status'] == 'succeeded'


def test_worker_running_update_is_not_clobbered_by_late_launcher_error(tmp_path):
    upgrader_started = threading.Event()
    release_upgrader = threading.Event()
    workers = []

    def upgrader(**kwargs):
        upgrader_started.set()
        assert release_upgrader.wait(5)
        return UpgradeResult(True, False, '', ['stop', 'reinstall', 'verify'])

    def launcher(state_dir, job_id):
        worker = threading.Thread(
            target=run_worker,
            args=(state_dir, job_id),
            kwargs={'upgrader': upgrader, 'verifier': lambda: True},
        )
        workers.append(worker)
        worker.start()
        assert upgrader_started.wait(5)
        raise subprocess.TimeoutExpired('systemd-run', 10)

    state = maintenance(tmp_path, launcher=launcher)
    job = state.start()
    assert state.job(job['id'])['status'] == 'running'
    release_upgrader.set()
    workers[0].join()
    assert state.job(job['id'])['status'] == 'succeeded'


def test_timeout_delayed_ipc_keeps_original_active_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'service_directory.maintenance.observe_transient_unit',
        lambda job_id, *, runner=subprocess.run: SimpleNamespace(
            active_state='active',
            sub_state='running',
            result='success',
            main_pid=4242,
            unit_not_found=False,
        ),
        raising=False,
    )

    def timed_out(*args):
        raise subprocess.TimeoutExpired('systemd-run', 10)

    state = maintenance(tmp_path, launcher=timed_out)
    job = state.start()
    assert job['status'] == 'queued'
    assert state.job(job['id'])['status'] == 'queued'


def test_unit_collected_after_timeout_does_not_prove_no_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'service_directory.maintenance.observe_transient_unit',
        lambda job_id, *, runner=subprocess.run: SimpleNamespace(
            active_state=None,
            sub_state=None,
            result=None,
            main_pid=None,
            unit_not_found=True,
        ),
        raising=False,
    )

    def timed_out(*args):
        raise subprocess.TimeoutExpired('systemd-run', 10)

    state = maintenance(tmp_path, launcher=timed_out)
    job = state.start()
    assert job['status'] == 'queued'
    assert state.job(job['id'])['status'] == 'queued'


def test_ambiguous_launch_timeout_preserves_active_job_and_blocks_duplicate_start(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'service_directory.maintenance.observe_transient_unit',
        lambda job_id, *, runner=subprocess.run: None,
        raising=False,
    )

    def timed_out(*args):
        raise subprocess.TimeoutExpired('systemd-run', 10)

    state = maintenance(tmp_path, launcher=timed_out)
    first = state.start()
    with pytest.raises(MaintenanceError) as error:
        state.start()
    assert error.value.status_code == 409
    assert state.job(first['id'])['status'] == 'queued'


def test_ambiguous_launch_nonzero_preserves_active_job_until_reconciled(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'service_directory.maintenance.observe_transient_unit',
        lambda job_id, *, runner=subprocess.run: None,
        raising=False,
    )

    def nonzero(*args):
        raise RuntimeError('Could not start the independent updater; check the systemd user manager.')

    state = maintenance(tmp_path, launcher=nonzero)
    first = state.start()
    with pytest.raises(MaintenanceError) as error:
        state.start()
    assert error.value.status_code == 409
    assert state.job(first['id'])['status'] == 'queued'


def test_observed_failed_transient_unit_marks_job_failed_and_allows_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'service_directory.maintenance.observe_transient_unit',
        lambda job_id, *, runner=subprocess.run: SimpleNamespace(
            active_state='failed',
            sub_state='failed',
            result='exit-code',
            main_pid=None,
            unit_not_found=False,
        ),
        raising=False,
    )

    launches = []

    def launcher(*args):
        launches.append(args)
        if len(launches) == 1:
            raise RuntimeError('Could not start the independent updater; check the systemd user manager.')

    state = maintenance(tmp_path, launcher=launcher)
    first = state.start()

    assert first['status'] == 'failed'
    assert first['message'] == 'independent updater exited unsuccessfully; check service status'
    assert first['finished_at'] is not None
    assert state.job(first['id'])['status'] == 'failed'

    second = state.start()

    assert second['id'] != first['id']
    assert second['status'] == 'queued'
    assert len(launches) == 2


def test_observed_deactivating_unit_with_no_mainpid_and_exit_code_remains_active_and_blocks_duplicate_start(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        'service_directory.maintenance.observe_transient_unit',
        lambda job_id, *, runner=subprocess.run: SimpleNamespace(
            active_state='deactivating',
            sub_state='stop-post',
            result='exit-code',
            main_pid=None,
            unit_not_found=False,
        ),
        raising=False,
    )

    def nonzero(*args):
        raise RuntimeError('Could not start the independent updater; check the systemd user manager.')

    state = maintenance(tmp_path, launcher=nonzero)
    first = state.start()

    assert first['status'] == 'queued'
    with pytest.raises(MaintenanceError) as error:
        state.start()
    assert error.value.status_code == 409
    assert state.job(first['id'])['status'] == 'queued'


def test_stale_exact_job_read_uses_same_reconciliation_as_latest_job(tmp_path):
    exact_state = maintenance(tmp_path / 'exact', time_fn=lambda: 2000)
    exact_id = 'd' * 32
    write_job(exact_state, exact_id, started_at=1)
    atomic_json(exact_state.directory / 'latest-job.json', {'id': exact_id})

    latest_state = maintenance(tmp_path / 'latest', time_fn=lambda: 2000)
    latest_id = 'e' * 32
    write_job(latest_state, latest_id, started_at=1)
    atomic_json(latest_state.directory / 'latest-job.json', {'id': latest_id})

    exact = exact_state.job(exact_id)
    latest = latest_state.latest_job()

    assert latest['status'] == 'failed'
    assert exact['status'] == latest['status']
    assert exact['message'] == latest['message']
    persisted = json.loads((exact_state.directory / f'{exact_id}.json').read_text())
    assert persisted['status'] == 'failed'


def test_terminal_worker_write_is_not_resurrected_by_stale_read(tmp_path):
    state = maintenance(tmp_path)
    job_id = 'f' * 32
    write_job(state, job_id, started_at=1)
    atomic_json(state.directory / 'latest-job.json', {'id': job_id})

    upgrader_started = threading.Event()
    release_upgrader = threading.Event()

    def upgrader(**kwargs):
        upgrader_started.set()
        assert release_upgrader.wait(5)
        return UpgradeResult(True, False, '', ['stop', 'reinstall', 'verify'])

    worker = threading.Thread(
        target=run_worker,
        args=(str(tmp_path), job_id),
        kwargs={'upgrader': upgrader, 'verifier': lambda: True},
    )
    worker.start()
    assert upgrader_started.wait(5)

    stale_reader = maintenance(tmp_path, time_fn=lambda: 2000)
    assert stale_reader.latest_job()['status'] == 'failed'

    release_upgrader.set()
    worker.join()

    assert maintenance(tmp_path, time_fn=lambda: 2000).job(job_id)['status'] == 'failed'


def test_worker_writes_terminal_result_and_requires_verification(tmp_path):
    state = maintenance(tmp_path)
    job = state.start()
    seen = []
    def upgrader(**kwargs):
        assert kwargs['recover_on_failure'] is True
        assert kwargs['doctor_verifier']() is True
        seen.append(state.job(job['id'])['status'])
        return UpgradeResult(True, False, 'secret install stdout', ['stop', 'reinstall', 'verify'])
    run_worker(str(tmp_path), job['id'], upgrader=upgrader, verifier=lambda: True)
    assert seen == ['running']
    assert state.job(job['id'])['status'] == 'succeeded'
    assert 'secret' not in str(state.status())
    # A second delivery of the same job must not upgrade twice.
    run_worker(str(tmp_path), job['id'], upgrader=lambda **kwargs: pytest.fail('duplicate worker'))


def test_worker_failure_is_durable_and_redacts_installer_errors(tmp_path):
    state = maintenance(tmp_path)
    job = state.start()
    def bad(**kwargs):
        raise RuntimeError('https://secret-token@repository')
    run_worker(str(tmp_path), job['id'], upgrader=bad)
    final = state.job(job['id'])
    assert final['status'] == 'failed'
    assert final['finished_at'] is not None
    assert 'secret-token' not in str(final)


def test_worker_launch_is_independent_systemd_unit_and_forwards_install_environment(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setenv('SERVICE_REGISTRY_CONFIG', '/a/config.yaml')
    monkeypatch.setenv('SERVICE_REGISTRY_PORT', '8085')
    def runner(command, **kwargs):
        commands.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, '', '')
    monkeypatch.setattr('service_directory.maintenance.subprocess.run', runner)
    launch_worker(str(tmp_path), 'a' * 32)
    command, kwargs = commands[0]
    assert command[:2] == ['systemd-run', '--user']
    assert '--property=RuntimeMaxSec=900' in command
    assert '--setenv=SERVICE_REGISTRY_PORT' in command
    assert '--setenv=SERVICE_REGISTRY_CONFIG' in command
    assert '--expand-environment=no' in command
    assert '/a/config.yaml' not in str(command)
    assert 'service_directory.maintenance' in command
    assert kwargs['timeout'] == 10
    assert 'shell' not in kwargs


def test_upgrade_stop_failure_never_reinstalls():
    class Manager:
        def stop(self): return ServiceResult(False, 'denied')
    result = run_upgrade(source_detector=lambda name: SOURCE, manager_factory=Manager,
                         runner=lambda cmd: pytest.fail('must not install when stop fails'))
    assert result.ok is False
    assert result.steps == ['stop']


def test_upgrade_reinstall_failure_recovers_service_for_cli_and_api():
    calls = []
    class Manager:
        def stop(self): calls.append('stop'); return ServiceResult(True, 'stopped')
        def start(self): calls.append('start'); return ServiceResult(True, 'started')
    result = run_upgrade(source_detector=lambda name: SOURCE, manager_factory=Manager,
                         runner=lambda cmd: subprocess.CompletedProcess(cmd, 1, '', 'offline'),
                         recover_on_failure=True)
    assert result.ok is False
    assert calls == ['stop', 'start']
    assert result.steps == ['stop', 'reinstall', 'recover_service']


def test_api_auth_and_read_gate(tmp_path):
    state = maintenance(tmp_path)
    app = create_app(config(tmp_path, require_read_token=True, require_write_token=True), maintenance=state)
    token = issue_write_token(str(tmp_path))
    upsert_peer(str(tmp_path), PeerRecord(name='peer', device_id='p', base_url='http://p', token='peer-secret'))
    client = TestClient(app, client=('198.51.100.9', 1234))
    assert client.get('/api/maintenance').status_code == 401
    assert client.get('/api/maintenance/jobs/any').status_code == 401
    assert client.get('/api/maintenance', headers={'Authorization': 'Bearer peer-secret'}).status_code == 200
    for path in ('check', 'update'):
        assert client.post('/api/maintenance/' + path).status_code == 401
        assert client.post('/api/maintenance/' + path, headers={'Authorization': 'Bearer peer-secret'}).status_code == 401
    headers = {'Authorization': 'Bearer ' + token}
    assert client.post('/api/maintenance/check', headers=headers).status_code == 200
    response = client.post('/api/maintenance/update', headers=headers)
    assert response.status_code == 202
    assert response.json()['status'] == 'queued'
    assert client.post('/api/maintenance/update', headers=headers).status_code == 409


def test_api_rejects_command_input_and_reports_unsupported(tmp_path):
    state = maintenance(tmp_path, capability=lambda source: 'unsupported')
    app = create_app(config(tmp_path), maintenance=state)
    client = TestClient(app, client=('127.0.0.1', 1234))
    assert client.get('/api/maintenance').json()['update_supported'] is False
    response = client.post('/api/maintenance/update', json={'command': 'evil'})
    assert response.status_code == 400
    assert client.post('/api/maintenance/update').status_code == 422
    assert client.get('/api/maintenance/jobs/unknown').status_code == 404
    assert not (tmp_path / 'maintenance/latest-job.json').exists()


def test_localhost_respects_require_write_token(tmp_path):
    client = TestClient(create_app(config(tmp_path, require_write_token=True), maintenance=maintenance(tmp_path)),
                        client=('127.0.0.1', 1234))
    assert client.post('/api/maintenance/update').status_code == 401
    assert client.post('/api/maintenance/check').status_code == 401


def test_settings_has_maintenance_section_and_existing_actions(tmp_path):
    page = TestClient(create_app(config(tmp_path), maintenance=maintenance(tmp_path))).get('/').text
    assert 'id="settings-tab-maintenance"' in page
    assert 'id="settings-panel-maintenance"' in page
    assert 'id="settings-maintenance-content"' in page
    assert 'Check for updates' in page
    assert 'Install update & restart' in page
    assert 'Refresh status' in page
    assert "maintenanceRequest('/api/maintenance/update', 'POST')" in page
    assert "maintenanceRequest('/api/maintenance/check', 'POST')" in page
    assert "/api/maintenance/jobs/" in page
    assert 'Hosted services are managed separately' in page


def test_maintenance_module_imports_without_fcntl_available(monkeypatch):
    module = load_maintenance_module_without_fcntl(monkeypatch)
    assert module.__name__ == 'service_directory._maintenance_without_fcntl_test'
    assert hasattr(module, 'Maintenance')


def test_unsupported_platform_status_and_check_work_and_update_returns_422_without_fcntl(tmp_path, monkeypatch):
    monkeypatch.setattr('service_directory.maintenance._load_fcntl', lambda: None)
    launched = []
    state = Maintenance(
        str(tmp_path),
        source_detector=lambda: SOURCE,
        capability=functools.partial(
            default_capability,
            runner=lambda *args, **kwargs: pytest.fail('fcntl-free capability must not shell out'),
            current_pid=7674,
            proc_root=tmp_path / 'proc',
            manager_factory=lambda: SimpleNamespace(
                unit_path=str(tmp_path / 'service-directory.service'),
                unit_name='service-directory.service',
            ),
        ),
        checker=lambda source: {'update_available': True, 'latest_revision': NEW, 'latest_version': None},
        launcher=lambda state_dir, job_id: launched.append((state_dir, job_id)),
        time_fn=lambda: 1000,
    )

    @contextmanager
    def forbidden_lock():
        raise AssertionError('update should reject before attempting a Unix lock')
        yield

    state.locked = forbidden_lock
    job_id = 'c' * 32
    atomic_json(
        state.directory / f'{job_id}.json',
        {'id': job_id, 'status': 'failed', 'message': 'kept readable without fcntl',
         'steps': [], 'started_at': 1, 'finished_at': 2},
    )
    client = TestClient(create_app(config(tmp_path), maintenance=state), client=('127.0.0.1', 1234))

    status = client.get('/api/maintenance')
    assert status.status_code == 200
    assert status.json()['update_supported'] is False
    assert 'locking support' in status.json()['unsupported_reason']

    check = client.post('/api/maintenance/check')
    assert check.status_code == 200
    assert check.json()['update_supported'] is False
    assert check.json()['latest_revision'] == NEW

    exact_job = client.get(f'/api/maintenance/jobs/{job_id}')
    assert exact_job.status_code == 200
    assert exact_job.json()['id'] == job_id

    update = client.post('/api/maintenance/update')
    assert update.status_code == 422
    assert 'locking support' in update.json()['detail']
    assert launched == []


def test_foreground_process_rejected_even_from_localhost(tmp_path, monkeypatch):
    runner, proc_root, manager_factory, _, _ = build_identity_fixture(tmp_path, main_pid=9001)
    monkeypatch.setattr('service_directory.maintenance.platform.system', lambda: 'Linux')
    monkeypatch.setattr('service_directory.maintenance.shutil.which', lambda name: '/usr/bin/' + name)
    monkeypatch.setattr('service_directory.maintenance.sys.prefix', str(tmp_path))
    (tmp_path / 'uv-receipt.toml').write_text('')
    state = Maintenance(
        str(tmp_path),
        source_detector=lambda: SOURCE,
        capability=functools.partial(
            default_capability,
            runner=runner,
            current_pid=7674,
            proc_root=proc_root,
            manager_factory=manager_factory,
        ),
    )
    client = TestClient(create_app(config(tmp_path), maintenance=state), client=('127.0.0.1', 1234))
    response = client.post('/api/maintenance/update')
    assert response.status_code == 422
    assert 'managed service' in response.json()['detail']


def test_managed_mainpid_process_reports_supported(tmp_path, monkeypatch):
    runner, proc_root, manager_factory, _, _ = build_identity_fixture(tmp_path)
    monkeypatch.setattr('service_directory.maintenance.platform.system', lambda: 'Linux')
    monkeypatch.setattr('service_directory.maintenance.shutil.which', lambda name: '/usr/bin/' + name)
    monkeypatch.setattr('service_directory.maintenance.sys.prefix', str(tmp_path))
    (tmp_path / 'uv-receipt.toml').write_text('')
    reason = default_capability(
        SOURCE,
        runner=runner,
        current_pid=7674,
        proc_root=proc_root,
        manager_factory=manager_factory,
    )
    assert reason is None


def test_identity_rejects_fragment_path_mismatch(tmp_path):
    runner, proc_root, manager_factory, _, _ = build_identity_fixture(
        tmp_path,
        fragment_path=tmp_path / 'other.service',
    )
    reason = serving_process_identity_reason(
        runner=runner,
        current_pid=7674,
        proc_root=proc_root,
        manager_factory=manager_factory,
    )
    assert 'unit file' in reason


def test_identity_rejects_control_group_mismatch(tmp_path):
    runner, proc_root, manager_factory, _, _ = build_identity_fixture(
        tmp_path,
        current_cgroup='/user.slice/user-1000.slice/user@1000.service/app.slice/foreground.scope',
    )
    reason = serving_process_identity_reason(
        runner=runner,
        current_pid=7674,
        proc_root=proc_root,
        manager_factory=manager_factory,
    )
    assert 'control group' in reason


def test_identity_rejects_execstart_mismatch(tmp_path):
    runner, proc_root, manager_factory, _, _ = build_identity_fixture(
        tmp_path,
        execstart_path=tmp_path / 'other-entrypoint',
    )
    reason = serving_process_identity_reason(
        runner=runner,
        current_pid=7674,
        proc_root=proc_root,
        manager_factory=manager_factory,
    )
    assert 'ExecStart' in reason


def test_identity_does_not_reject_custom_unit_type_when_other_identity_matches(tmp_path):
    runner, proc_root, manager_factory, _, _ = build_identity_fixture(tmp_path, unit_type='notify')
    reason = serving_process_identity_reason(
        runner=runner,
        current_pid=7674,
        proc_root=proc_root,
        manager_factory=manager_factory,
    )
    assert reason is None


def test_capability_requires_managed_uv_install_and_supported_systemd(tmp_path, monkeypatch):
    monkeypatch.setattr('service_directory.maintenance.platform.system', lambda: 'Linux')
    monkeypatch.setattr('service_directory.maintenance.shutil.which', lambda name: '/usr/bin/' + name)
    monkeypatch.setattr('service_directory.maintenance.sys.prefix', str(tmp_path))
    version_runner = lambda *args, **kwargs: subprocess.CompletedProcess([], 0, 'systemd 255 (255)', '')
    assert 'uv tool environment' in default_capability(SOURCE, runner=version_runner)
    (tmp_path / 'uv-receipt.toml').write_text('')
    missing_manager_factory = lambda: SimpleNamespace(
        unit_path=str(tmp_path / 'directory.service'),
        unit_name='service-directory.service',
    )
    assert 'Install the' in default_capability(
        SOURCE,
        runner=version_runner,
        manager_factory=missing_manager_factory,
    )
    runner, proc_root, manager_factory, _, _ = build_identity_fixture(tmp_path)
    assert default_capability(
        SOURCE,
        runner=runner,
        current_pid=7674,
        proc_root=proc_root,
        manager_factory=manager_factory,
    ) is None
    low_version_runner = lambda *args, **kwargs: subprocess.CompletedProcess([], 0, 'systemd 249 (249)', '')
    assert '254' in default_capability(SOURCE, runner=low_version_runner)
    monkeypatch.setattr('service_directory.maintenance.platform.system', lambda: 'Darwin')
    assert 'CLI' in default_capability(SOURCE, runner=version_runner)


def test_regenerate_exception_attempts_recovery_and_stays_failed():
    calls = []
    class Manager:
        def stop(self): return ServiceResult(True, 'stopped')
        def install(self): raise OSError('cannot write unit')
        def start(self): calls.append('start'); return ServiceResult(True, 'started')
    result = run_upgrade(source_detector=lambda name: SOURCE, manager_factory=Manager,
                         runner=lambda cmd: subprocess.CompletedProcess(cmd, 0, '', ''),
                         recover_on_failure=True)
    assert not result.ok
    assert result.steps == ['stop', 'reinstall', 'regenerate_unit', 'recover_service']
    assert calls == ['start']


def test_worker_recovery_is_owned_by_systemd_not_the_upgraded_python(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr('service_directory.maintenance.subprocess.run',
                        lambda command, **kwargs: commands.append(command) or
                        subprocess.CompletedProcess(command, 0, '', ''))
    launch_worker(str(tmp_path), 'b' * 32)
    command = commands[0]
    properties = {arg.removeprefix('--property=') for arg in command if arg.startswith('--property=')}
    # The manager runs ExecStopPost after termination, including a deadline or
    # SIGKILL. A Python finally/except block cannot substitute for this contract.
    assert 'RuntimeMaxSec=900' in properties
    assert 'KillMode=control-group' in properties
    assert 'TimeoutStopSec=20' in properties
    assert 'ExecStopPost=systemctl --user start service-directory.service' in properties
    recovery = next(prop for prop in properties if prop.startswith('ExecStopPost='))
    assert str(tmp_path) not in recovery
    assert 'python' not in recovery
    assert 'service_directory.maintenance' not in recovery


def test_capability_requires_systemctl_for_external_recovery(monkeypatch):
    monkeypatch.setattr('service_directory.maintenance.platform.system', lambda: 'Linux')
    monkeypatch.setattr('service_directory.maintenance.shutil.which',
                        lambda tool: None if tool == 'systemctl' else '/usr/bin/' + tool)
    assert 'systemctl' in default_capability(SOURCE)
