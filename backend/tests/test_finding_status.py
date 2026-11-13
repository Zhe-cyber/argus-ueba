"""POST /findings/{id}/status for rule and baseline findings. Temp SQLite only."""
import sqlite3

import pytest
from fastapi import FastAPI

from backend import alert_store, event_store as events
from workspace_next import case_store as cases
from workspace_next.case_api import router
from backend.tests.auth_helpers import signed_in_client
from backend.tests.test_baseline_alerts import put, history_rows, sync, base_id


@pytest.fixture
def env(monkeypatch, tmp_path):
    assert not events._PG, 'Run with DATABASE_URL=sqlite-local'
    monkeypatch.setattr(events, 'DB_PATH', tmp_path / 'events.db')
    events.init_db(); alert_store.init_alerts_db(); cases.init_db()
    put(history_rows() + [('a', '2026-10-10T02:00:00Z', 'Read', 'secretsmanager/prod-key')] * 4)
    sync()
    rule = alert_store.create_alert('a', 'rarity_spike', 'High', 'rule alert', {})['id']
    app = FastAPI(); app.include_router(router)
    with signed_in_client(app, tmp_path) as c:
        yield c, rule, base_id(events.DB_PATH)


def post(c, fid, **over):
    body = {'status': 'Resolved', 'analyst': 'me', 'reason': 'checked'} | over
    return c.post(f'/findings/{fid}/status', json=body)


def test_status_change_filters_and_audits_for_both_kinds(env):
    c, rule, base = env
    for fid in (rule, base):
        assert post(c, fid, status='False Positive').status_code == 200
    found = {r['id'] for r in c.get('/findings?status=False Positive&category=all&limit=100').json()['findings']}
    assert {rule, base} <= found
    assert not {rule, base} & {r['id'] for r in c.get('/findings?status=Open&category=all').json()['findings']}
    with sqlite3.connect(events.DB_PATH) as con:
        assert con.execute('SELECT COUNT(*) FROM workspace_finding_audit').fetchone()[0] == 2
        # the session names the analyst for rule AND backend baseline findings; the body's 'me' is ignored
        assert {r[0] for r in con.execute('SELECT analyst FROM workspace_finding_audit')} == {'fixture-analyst'}
        assert con.execute('SELECT resolved_at IS NOT NULL FROM alerts WHERE id=?', (rule,)).fetchone()[0] == 1
    assert post(c, rule, status='Open').status_code == 200
    with sqlite3.connect(events.DB_PATH) as con:
        assert con.execute('SELECT resolved_at FROM alerts WHERE id=?', (rule,)).fetchone()[0] is None


@pytest.mark.parametrize('over,text', [({'reason': ''}, 'Reason'), ({'status': 'Bogus'}, 'Status')])
def test_validation_messages(env, over, text):
    c, rule, _ = env
    r = post(c, rule, **over)
    assert r.status_code == 422 and text in r.json()['detail']


def test_unknown_finding_is_404(env):
    c, _, _ = env
    assert post(c, 999).status_code == 404 and post(c, 1_000_099).status_code == 404
