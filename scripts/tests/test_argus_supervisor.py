"""Supervisor restart policy and health file: fake processes, fake clock, temp folders only."""
import json
import sqlite3
import sys

import pytest

from scripts import argus_supervisor as sup
from scripts.tests.test_ops_collect import make_config


class FakeProc:
    def __init__(self):
        self.returncode, self.terminated = None, False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0


class Spawner:
    def __init__(self):
        self.started = []

    def __call__(self, child):
        proc = FakeProc()
        self.started.append((child.name, proc))
        return proc


def test_crashed_child_is_restarted_after_backoff():
    spawn, child = Spawner(), sup.Child('collector', ['x'])
    sup.step([child], 0, spawn)
    assert child.state == 'running' and len(spawn.started) == 1
    spawn.started[-1][1].returncode = 1
    sup.step([child], 10, spawn)
    assert child.state == 'backoff' and child.last_exit_code == 1 and len(spawn.started) == 1
    sup.step([child], 11, spawn)  # back-off of 2 s not yet over
    assert len(spawn.started) == 1
    sup.step([child], 12, spawn)
    assert child.state == 'running' and child.restarts == 1 and len(spawn.started) == 2


def test_five_crashes_in_ten_minutes_mark_failed_and_stop_restarting():
    spawn, child = Spawner(), sup.Child('mirror', ['x'])
    now = 0
    sup.step([child], now, spawn)
    for _ in range(5):
        spawn.started[-1][1].returncode = 3
        now += 1
        sup.step([child], now, spawn)  # notices the exit
        now += 60
        sup.step([child], now, spawn)  # restarts unless failed
    assert child.state == 'failed' and len(spawn.started) == 5
    sup.step([child], now + 3600, spawn)
    assert len(spawn.started) == 5


def test_crashes_spread_beyond_ten_minutes_do_not_fail():
    spawn, child = Spawner(), sup.Child('web-ui', ['x'])
    now = 0
    for _ in range(8):
        sup.step([child], now, spawn)
        spawn.started[-1][1].returncode = 1
        now += 200
    sup.step([child], now, spawn)
    assert child.state == 'running'


def test_health_file_content_and_shutdown(tmp_path):
    spawn = Spawner()
    children = [sup.Child('ingest-api', ['x']), sup.Child('collector', ['y'])]
    ticks = iter(range(0, 100))
    sup.run(children, tmp_path / 'health.json', spawn=spawn, clock=lambda: next(ticks) * 31.0,
            sleep=lambda s: None, until=lambda: len(spawn.started) >= 2 and (tmp_path / 'health.json').exists())
    data = json.loads((tmp_path / 'health.json').read_text(encoding='utf-8'))
    assert data['schema'] == 'argus_supervisor_health_v1'
    assert [c['name'] for c in data['components']] == ['ingest-api', 'collector']
    assert all(c['state'] == 'running' and c['restarts'] == 0 and c['running_since_utc'] for c in data['components'])
    assert all(proc.terminated for _, proc in spawn.started)  # children stopped with the supervisor


def test_components_come_from_config_with_one_scheduler(tmp_path):
    cfg = make_config(tmp_path)
    cfg['live_state_dir'].mkdir(parents=True)
    with sqlite3.connect(cfg['live_state_dir'] / 'events.db') as db:
        db.execute('CREATE TABLE events(id INTEGER)')
    cfg['supervisor'] = {'workspace_dir': str(tmp_path / 'workspace'), 'workspace_api_port': 8021, 'web_ui_port': 3016,
                         'python': sys.executable, 'node': 'node', 'frontend_dir': str(tmp_path / 'frontend')}
    cfg['auth'] = {'users_file': str(tmp_path / 'auth' / 'users.json'), 'secret_file': str(tmp_path / 'auth' / 'session.key')}
    children = sup.components(cfg, tmp_path / 'ops.json')
    assert [c.name for c in children] == ['ingest-api', 'collector', 'personas', 'mirror', 'workspace-api', 'notifier', 'web-ui']
    assert children[1].argv[2:4] == ['loop', '--config'] and children[2].argv[2] == 'loop'
    marker = json.loads((tmp_path / 'workspace' / 'workspace-copy.json').read_text(encoding='utf-8'))
    assert marker['not_live'] is True and (tmp_path / 'workspace' / 'preview.db').is_file()
    api = children[4]
    assert api.env['ARGUS_AUTH_USERS_FILE'].endswith('users.json') and api.env['ARGUS_WORKSPACE_UI_ORIGIN'].endswith(':3016')
    assert api.env['DATABASE_URL'] == 'sqlite-local'


def test_loop_survives_a_failing_pass():
    from scripts import ops_collect
    calls = []

    def once():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('one bad pass')
        if len(calls) == 3:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        ops_collect.loop(once, 5, sleep=lambda s: None)
    assert len(calls) == 3


def test_workspace_components_endpoint_reads_health(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from backend.tests.auth_helpers import sign_in
    health = tmp_path / 'health.json'
    health.write_text(json.dumps(sup.health([sup.Child('collector', ['x'])], 0)), encoding='utf-8')
    monkeypatch.setenv('ARGUS_SUPERVISOR_HEALTH', str(health))
    from backend import alert_store, event_store
    from workspace_next import case_store
    import shutil
    db = tmp_path / 'source.db'
    monkeypatch.setattr(event_store, 'DB_PATH', db)
    event_store.init_db(); alert_store.init_alerts_db(); case_store.init_db()
    shutil.copyfile(db, tmp_path / 'preview.db')
    (tmp_path / 'workspace-copy.json').write_text(json.dumps({'not_live': True, 'copy_db': str((tmp_path / 'preview.db').resolve())}))
    monkeypatch.setenv('ARGUS_WORKSPACE_COPY_DB', str(tmp_path / 'preview.db'))
    from workspace_next.app import create_app
    with TestClient(create_app()) as client:
        assert client.get('/workspace/components').status_code == 401
        sign_in(client, tmp_path / 'auth' / 'users.json')
        body = client.get('/workspace/components').json()
    assert body['available'] and [c['name'] for c in body['components']] == ['collector']
