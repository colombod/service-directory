"""Hermetic maintenance contracts: source, auth, durable lifecycle and launch isolation."""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from service_directory.app import create_app
from service_directory.config import FederationConfig, HostAddress, RegistryConfig
from service_directory.install_source import InstallSource, check_for_update, detect_install_source
from service_directory.maintenance import (
    Maintenance, MaintenanceError, atomic_json, check_source, default_capability, git_revision,
    launch_worker, run_worker,
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
        raise OSError('token-in-source-url')
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


def test_settings_has_maintenance_section_and_same_api_actions(tmp_path):
    page = TestClient(create_app(config(tmp_path), maintenance=maintenance(tmp_path))).get('/').text
    assert 'id="settings-tab-maintenance"' in page
    assert 'id="settings-panel-maintenance"' in page
    assert "maintenanceRequest('/api/maintenance/update', 'POST')" in page
    assert "maintenanceRequest('/api/maintenance/check', 'POST')" in page
    assert 'Hosted services are managed separately' in page


def test_capability_requires_managed_uv_install_and_supported_systemd(tmp_path, monkeypatch):
    monkeypatch.setattr('service_directory.maintenance.platform.system', lambda: 'Linux')
    monkeypatch.setattr('service_directory.maintenance.shutil.which', lambda name: '/usr/bin/' + name)
    monkeypatch.setattr('service_directory.maintenance.sys.prefix', str(tmp_path))
    monkeypatch.setattr('service_directory.maintenance.subprocess.run',
                        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, 'systemd 255 (255)', ''))
    assert 'uv tool environment' in default_capability(SOURCE)
    (tmp_path / 'uv-receipt.toml').write_text('')
    class Manager:
        unit_path = str(tmp_path / 'directory.service')
    monkeypatch.setattr('service_directory.maintenance.SystemdUserServiceManager', Manager)
    assert 'Install the' in default_capability(SOURCE)
    Path(Manager.unit_path).write_text('')
    assert default_capability(SOURCE) is None
    monkeypatch.setattr('service_directory.maintenance.subprocess.run',
                        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, 'systemd 249 (249)', ''))
    assert '254' in default_capability(SOURCE)
    monkeypatch.setattr('service_directory.maintenance.platform.system', lambda: 'Darwin')
    assert 'CLI' in default_capability(SOURCE)


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
