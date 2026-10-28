"""No provider calls or actual task installation; subprocesses are stubbed."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from scripts import local_pilot as pilot


@pytest.fixture
def cfg(tmp_path):
    return {'state_dir': str(tmp_path), 'connected_dir': str(tmp_path / 'connected'),
            'ledger_dir': str(tmp_path / 'persona-history-v1'), 'account_id': '123456789012',
            'stack': 'argus-ueba-actors', 'queue_url': 'https://sqs.us-east-1.amazonaws.com/123456789012/argus-ueba-live-events',
            'repo': 'Zhe-cyber/argus-ueba', 'cloudflare': {'account': 'a' * 32, 'app_id': 'b' * 36},
            'actor_start': '2026-10-29', 'end_local': '2026-11-24', 'runtime_id': 'a' * 32,
            'source_hashes': {}, 'python': 'python.exe', 'gh': 'gh.exe'}


def mocked(cfg, monkeypatch, aws_ok=True, unknown=0, actor_ok=True):
    calls = []
    monkeypatch.setattr(pilot, 'ensure_backend', lambda _: None)
    monkeypatch.setattr(pilot, 'unknown_claims', lambda _: unknown)
    def command(c, script, args, timeout=150):
        calls.append((script, list(args)))
        return {'ok': aws_ok if 'aws' in args else actor_ok if '--execute' in args else True}
    monkeypatch.setattr(pilot, 'command', command)
    return calls


def test_commissioning_day_collects_without_actor_execution(cfg, monkeypatch):
    calls = mocked(cfg, monkeypatch)
    result = pilot.tick(cfg, datetime(2026, 10, 28, 4, tzinfo=timezone.utc))
    assert result['phases']['actors']['status'] == 'starts_2026_10_29'
    assert not any('--execute' in args for _, args in calls)
    assert result['model_activated'] is False


def test_normal_due_runner_uses_existing_profiles_and_ledger(cfg, monkeypatch):
    calls = mocked(cfg, monkeypatch)
    result = pilot.tick(cfg, datetime(2026, 10, 29, 4, tzinfo=timezone.utc))
    actors = [args for script, args in calls if script == 'run_persona_history.py' and '--execute' in args]
    assert len(actors) == 1 and actors[0][actors[0].index('--profile') + 1] == 'argus-simulator'
    assert actors[0][actors[0].index('--state-dir') + 1] == cfg['ledger_dir']
    aws = next(args for _, args in calls if 'aws' in args)
    assert aws[aws.index('--batches') + 1] == '5'
    assert result['ok']


@pytest.mark.parametrize('aws_ok,unknown', [(False, 0), (True, 1)])
def test_collection_failure_or_unknown_claim_blocks_actor(cfg, monkeypatch, aws_ok, unknown):
    calls = mocked(cfg, monkeypatch, aws_ok=aws_ok, unknown=unknown)
    result = pilot.tick(cfg, datetime(2026, 10, 29, 4, tzinfo=timezone.utc))
    assert not any('--execute' in args for _, args in calls)
    assert result['phases']['actors']['ok'] is False


def test_failed_actor_subprocess_is_not_retried(cfg, monkeypatch):
    calls = mocked(cfg, monkeypatch, actor_ok=False)
    result = pilot.tick(cfg, datetime(2026, 10, 29, 4, tzinfo=timezone.utc))
    assert sum('--execute' in args for _, args in calls) == 1
    assert result['ok'] is False


def test_expired_pilot_does_not_start_backend_or_call_providers(cfg, monkeypatch):
    monkeypatch.setattr(pilot, 'ensure_backend', lambda _: pytest.fail('Started backend after expiry'))
    monkeypatch.setattr(pilot, 'command', lambda *a, **k: pytest.fail('Cloud request after expiry'))
    assert pilot.tick(cfg, datetime(2026, 11, 25, 0, tzinfo=timezone.utc))['status'] == 'pilot_expired'


def test_genuine_poll_failures_persist_and_are_rate_limited(cfg, monkeypatch):
    calls = mocked(cfg, monkeypatch)
    def command(c, script, args, timeout=150):
        calls.append((script, list(args)))
        return {'ok': 'github' not in args}
    monkeypatch.setattr(pilot, 'command', command)
    start = datetime(2026, 10, 29, 4, tzinfo=timezone.utc)
    first = pilot.tick(cfg, start)
    second = pilot.tick(cfg, start + timedelta(minutes=5))
    assert not first['ok'] and not second['ok']
    assert second['phases']['github']['status'] == 'not_due_previous_failure'
    assert sum('github' in args for _, args in calls) == 1
    pilot.tick(cfg, start + timedelta(minutes=30))
    assert sum('github' in args for _, args in calls) == 2


def test_wrong_listener_is_rejected_without_actors(cfg, monkeypatch):
    import requests
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs): return SimpleNamespace(status_code=200, json=lambda: {'application_mode': 'live'})
    monkeypatch.setattr(requests, 'Session', Session)
    monkeypatch.setattr(pilot, 'command', lambda *a, **k: pytest.fail('Actors called on wrong backend'))
    with pytest.raises(ValueError, match='Unexpected listener'):
        pilot.tick(cfg, datetime(2026, 10, 29, 4, tzinfo=timezone.utc))


def test_ready_identity_requires_sqlite_unverified_and_actual_path(cfg):
    ready = pilot.expected_health(cfg)
    assert ready['storage'] == 'sqlite' and ready['application_mode'] == 'live'
    assert ready['cloud_model_profile'] == 'unverified'
    assert cfg['connected_dir'] not in json.dumps(ready)
    other = deepcopy(cfg)
    other['connected_dir'] += '-snapshot'
    assert pilot.expected_health(other)['database_path_sha256'] != ready['database_path_sha256']


def valid_config(tmp_path, monkeypatch):
    live = tmp_path / 'live'
    for name in ('connected', 'persona-history-v1', 'pilot-local-v1'):
        (live / name).mkdir(parents=True)
    scope = ['123456789012', 'argus-ueba-actors', pilot.PROFILE_SHA]
    with sqlite3.connect(live / 'persona-history-v1/ledger.db') as db:
        db.execute('create table scope(id integer,contract text)')
        db.execute('insert into scope values(1,?)', (json.dumps(scope),))
        db.execute('create table actions(status text,native_event_id text)')
        db.execute("insert into actions values('provider_verified','native-probe')")
    with sqlite3.connect(live / 'connected/events.db') as db:
        db.execute('create table events(source text,source_account_id text,event_id text)')
        db.execute("insert into events values('aws_cloudtrail','123456789012','native-probe')")
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    for name in ('python.exe', 'pythonw.exe', 'gh.exe'):
        (binaries / name).write_bytes(b'synthetic-never-executed')
    monkeypatch.setattr(pilot, 'pinned_sources', lambda: {'runtime.py': 'expected'})
    return {'schema': 'argus_local_pilot_v1', 'source_root': str(pilot.ROOT), 'api': pilot.API,
            'python': str(binaries / 'python.exe'), 'pythonw': str(binaries / 'pythonw.exe'), 'gh': str(binaries / 'gh.exe'),
            'state_dir': str(live / 'pilot-local-v1'), 'connected_dir': str(live / 'connected'),
            'ledger_dir': str(live / 'persona-history-v1'), 'account_id': scope[0], 'stack': scope[1],
            'queue_url': 'https://sqs.us-east-1.amazonaws.com/123456789012/argus-ueba-live-events',
            'repo': 'Zhe-cyber/argus-ueba', 'cloudflare': None, 'runtime_id': 'a' * 32,
            'actor_start': '2026-10-29', 'end_local': '2026-11-24', 'source_hashes': {'runtime.py': 'expected'}}


def test_source_drift_and_wrong_native_store_fail_closed(tmp_path, monkeypatch):
    config = valid_config(tmp_path, monkeypatch)
    assert pilot.validate(config) is config
    config['source_hashes'] = {'runtime.py': 'changed'}
    with pytest.raises(ValueError, match='runtime source changed'):
        pilot.validate(config)
    config['source_hashes'] = {'runtime.py': 'expected'}
    with sqlite3.connect(Path(config['connected_dir']) / 'events.db') as db:
        db.execute('delete from events')
    with pytest.raises(ValueError, match='does not match'):
        pilot.validate(config)


def test_child_payload_redaction_and_single_timeout(cfg, monkeypatch):
    payload = {'received': 1, 'access_key': 'secret', 'status': 'secret_token', 'action_states': {'private_user': 1}}
    monkeypatch.setattr(pilot.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload)))
    report = pilot.command(cfg, 'collect_live.py', ['github'])
    assert 'secret' not in json.dumps(report) and 'private_user' not in json.dumps(report)
    def timeout(*a, **k): raise pilot.subprocess.TimeoutExpired('synthetic', 1)
    monkeypatch.setattr(pilot.subprocess, 'run', timeout)
    assert pilot.command(cfg, 'run_persona_history.py', ['--execute'])['ok'] is False
