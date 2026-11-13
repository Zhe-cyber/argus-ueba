"""Workspace sign-in and enforcement. Temp users file, temp secret, fixture passwords only."""
import json
import logging
import re
import shutil
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import alert_store, auth, event_store
from backend.tests.auth_helpers import PASSWORD, sign_in
from workspace_next import case_store


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    assert not event_store._PG, 'Run with DATABASE_URL=sqlite-local'
    db = tmp_path / 'source.db'
    monkeypatch.setattr(event_store, 'DB_PATH', db)
    event_store.init_db(); alert_store.init_alerts_db(); case_store.init_db()
    preview = tmp_path / 'preview.db'
    shutil.copyfile(db, preview)
    (tmp_path / 'workspace-copy.json').write_text(json.dumps({'not_live': True, 'copy_db': str(preview.resolve())}))
    monkeypatch.setenv('ARGUS_WORKSPACE_COPY_DB', str(preview))
    from workspace_next.app import create_app
    app = create_app()
    clock = {'now': 1_000_000.0}
    app.state.auth.clock = lambda: clock['now']
    with TestClient(app) as client:
        yield app, client, tmp_path / 'auth' / 'users.json', clock, preview


def protected_routes(app):
    for route in app.routes:
        for method in sorted(getattr(route, 'methods', None) or []):
            if method in ('HEAD', 'OPTIONS') or (method, route.path) in auth.PUBLIC:
                continue
            if route.path.startswith(('/docs', '/redoc', '/openapi')):
                continue
            yield method, re.sub(r'\{[^}]+\}', '1', route.path)


def test_route_list_is_not_empty(workspace):
    app = workspace[0]
    routes = list(protected_routes(app))
    assert len(routes) > 20 and ('POST', '/findings/1/status') in routes and ('GET', '/auth/me') in routes


def test_every_protected_route_needs_a_session(workspace):
    app, client, *_ = workspace
    client.headers['X-Argus-Request'] = '1'
    for method, path in protected_routes(app):
        response = client.request(method, path, json={})
        assert response.status_code == 401, (method, path, response.status_code)
    assert client.get('/health').json() == {'status': 'ok'}


def test_login_sets_strict_http_only_cookie_and_logout_ends_it(workspace):
    _, client, users, *_ = workspace
    sign_in(client, users)
    cookie = client.cookies.get(auth.COOKIE)
    assert cookie and PASSWORD not in cookie
    assert client.get('/auth/me').json()['user'] == 'fixture-analyst'
    login = client.post('/auth/login', json={'username': 'fixture-analyst', 'password': PASSWORD})
    header = login.headers['set-cookie'].lower()
    assert 'httponly' in header and 'samesite=strict' in header
    cookie = client.cookies.get(auth.COOKIE)
    client.post('/auth/logout')
    client.cookies.set(auth.COOKIE, cookie)  # the old cookie no longer opens a session
    assert client.get('/auth/me').status_code == 401


def test_wrong_password_and_lockout(workspace, caplog):
    _, client, users, clock, _ = workspace
    auth.add_user(users, 'alice', 'analyst', PASSWORD)
    client.headers['X-Argus-Request'] = '1'
    caplog.set_level(logging.INFO, logger='argus.auth')
    for _ in range(5):
        r = client.post('/auth/login', json={'username': 'alice', 'password': 'wrong-password-123'})
        assert r.status_code == 401 and r.json()['detail'] == 'Wrong user name or password'
    r = client.post('/auth/login', json={'username': 'alice', 'password': PASSWORD})
    assert r.status_code == 401 and 'Too many' in r.json()['detail']
    assert 'wrong-password-123' not in caplog.text and PASSWORD not in caplog.text and 'alice' in caplog.text
    clock['now'] += 301
    assert client.post('/auth/login', json={'username': 'alice', 'password': PASSWORD}).status_code == 200
    unknown = client.post('/auth/login', json={'username': 'nobody', 'password': PASSWORD})
    assert unknown.status_code == 401 and unknown.json()['detail'] == 'Wrong user name or password'


def test_idle_session_expires_and_activity_extends_it(workspace):
    _, client, users, clock, _ = workspace
    sign_in(client, users)
    clock['now'] += 8 * 3600 - 10
    assert client.get('/auth/me').status_code == 200  # activity resets the idle timer
    clock['now'] += 8 * 3600 - 10
    assert client.get('/auth/me').status_code == 200
    clock['now'] += 8 * 3600 + 1
    assert client.get('/auth/me').status_code == 401


def test_tampered_cookie_is_rejected(workspace):
    _, client, users, *_ = workspace
    sign_in(client, users)
    sid, _, sig = client.cookies.get(auth.COOKIE).partition('.')
    for forged in (sid + '.' + sig[:-2] + ('AA' if sig[-2:] != 'AA' else 'BB'), sid[:-1] + 'x.' + sig, sid):
        client.cookies.set(auth.COOKIE, forged)
        assert client.get('/auth/me').status_code == 401


def test_viewer_reads_but_cannot_change(workspace):
    _, client, users, *_ = workspace
    sign_in(client, users, 'victor', 'viewer')
    assert client.get('/cases').status_code == 200
    r = client.post('/cases', json={'title': 't', 'request_key': 'k'})
    assert r.status_code == 403 and 'role' in r.json()['detail']


def test_missing_request_header_is_blocked(workspace):
    _, client, users, *_ = workspace
    sign_in(client, users)
    del client.headers['X-Argus-Request']
    assert client.post('/cases', json={'title': 't', 'request_key': 'k'}).status_code == 403
    assert client.post('/auth/login', json={'username': 'x', 'password': 'y'}).status_code == 403


def test_audit_rows_carry_the_session_user_not_the_body(workspace):
    _, client, users, _, preview = workspace
    sign_in(client, users, 'bob')
    case = client.post('/cases', json={'title': 'Review', 'actor': 'spoofed', 'request_key': 'k1'}).json()
    assert case['history'][0]['actor'] == 'bob'
    edited = client.patch('/cases/' + case['id'], json={'expected_version': 1, 'request_key': 'k2',
                                                        'changes': {'notes': 'checked'}}).json()
    assert edited['history'][-1]['actor'] == 'bob'
    rule = alert_store.create_alert('acct', 'rarity_spike', 'High', 'rule alert', {})['id']
    r = client.post(f'/findings/{rule}/status', json={'status': 'Acknowledged', 'analyst': 'spoofed', 'reason': 'looking'})
    assert r.status_code == 200
    with sqlite3.connect(preview) as con:
        assert con.execute('SELECT analyst FROM workspace_finding_audit').fetchall() == [('bob',)]
    assert client.get('/auth/me').json()['sign_in_since_utc']


def test_add_user_cli_prompts_twice_and_stores_only_a_scrypt_hash(tmp_path, monkeypatch, capsys):
    users = tmp_path / 'users.json'
    answers = iter([PASSWORD, PASSWORD + 'x'])
    monkeypatch.setattr(auth.getpass, 'getpass', lambda prompt: next(answers))
    assert auth.main(['add-user', 'carol', '--role', 'analyst', '--users-file', str(users)]) == 1
    assert not users.exists()
    answers = iter([PASSWORD, PASSWORD])
    assert auth.main(['add-user', 'carol', '--role', 'analyst', '--users-file', str(users)]) == 0
    text = users.read_text(encoding='utf-8')
    record = json.loads(text)['users']['carol']
    assert PASSWORD not in text and record['role'] == 'analyst' and len(record['salt']) == 32
    assert PASSWORD not in capsys.readouterr().out
    answers = iter(['short', 'short'])
    assert auth.main(['add-user', 'dave', '--role', 'viewer', '--users-file', str(users)]) == 1


def test_salts_differ_and_secret_is_created_once(tmp_path):
    a, b = auth.make_record(PASSWORD, 'viewer'), auth.make_record(PASSWORD, 'viewer')
    assert a['salt'] != b['salt'] and a['hash'] != b['hash']
    key = tmp_path / 'session.key'
    first = auth.load_or_create_secret(key)
    assert len(first) == 32 and auth.load_or_create_secret(key) == first
