"""Baseline findings: Medium/High account-days become alerts rows (alert_type='baseline_risk') written by the backend
scorer; analyst state survives a re-score. Temp SQLite only. (L8: was workspace_next.baseline_alerts.sync on a
copy-only table with 1_000_000-offset ids; the rules are unchanged, the storage and ids moved to `alerts`.)"""
import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import alert_store, baseline_scorer, event_store as events
from workspace_next import case_store as cases, queries
from workspace_next.case_api import router
from backend.tests.auth_helpers import signed_in_client


def put(rows):
    with events._db() as con:
        cur = events._cursor(con)
        for key, ts, action, resource in rows:
            i = uuid4().hex
            cur.execute('''INSERT INTO events ("user",timestamp,source,action,resource,ip_address,metadata,ingested_at,
                event_id,source_account_id,payload_digest,account_key,account_label,account_kind,account_basis)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (key, ts, 'aws_cloudtrail', action, resource, '', '{}', ts, f'e{i}', 's', f'd{i}', key, 'acct-label', 'role', 'x'))


def history_rows(n=6):
    return [('a', f'2026-10-{10 - i:02d}T02:00:00Z', 'Read', 'toy') for i in range(1, n + 1) for _ in range(4)]


def sync():
    baseline_scorer.ensure_schema()
    return baseline_scorer.backfill()


@pytest.fixture
def db(monkeypatch, tmp_path):
    assert not events._PG, 'Run with DATABASE_URL=sqlite-local'
    monkeypatch.setattr(events, 'DB_PATH', tmp_path / 'events.db')
    events.init_db(); alert_store.init_alerts_db(); cases.init_db()
    return events.DB_PATH


@pytest.fixture
def client(db, tmp_path):
    app = FastAPI(); app.include_router(router)
    with signed_in_client(app, tmp_path) as c:
        yield c


def risky(db):
    put(history_rows() + [('a', '2026-10-10T02:00:00Z', 'Read', 'secretsmanager/prod-key')] * 4)
    return sync()


def rows(db):
    with sqlite3.connect(db) as con:
        return con.execute("SELECT id,status,severity,title,details,day FROM alerts WHERE alert_type='baseline_risk'").fetchall()


def base_id(db):
    return rows(db)[0][0]


def test_sync_creates_one_row_per_account_day_and_is_idempotent(db):
    risky(db)
    sync()
    assert len(rows(db)) == 1
    _, status, severity, title, details, day = rows(db)[0]
    assert status == 'Open' and severity in ('Medium', 'High') and title.startswith('Baseline risk ')
    assert json.loads(details)['day'] == '2026-10-10' == day


def test_unique_guard_per_type_account_day(db):
    risky(db)
    with pytest.raises(sqlite3.IntegrityError), sqlite3.connect(db) as con:
        con.execute("INSERT INTO alerts (user_id,alert_type,severity,title,created_at,day) "
                    "VALUES ('a','baseline_risk','High','dup','2026-10-10T00:00:00Z','2026-10-10')")
    for _ in range(2):  # rule alerts keep day NULL and never collide
        alert_store.create_alert('a', 'rarity_spike', 'High', 'rule', {})


def test_quiet_day_makes_no_alert(db):
    put(history_rows() + [('a', '2026-10-10T02:00:00Z', 'Read', 'toy')] * 4)
    sync()
    assert rows(db) == []


def test_findings_list_and_detail_include_baseline(db):
    risky(db)
    listing = queries.findings(status='All', limit=50)['findings']
    base = [r for r in listing if r['origin'] == 'baseline']
    assert len(base) == 1 and base[0]['id'] == base_id(db)
    assert base[0]['baseline']['score'] is not None
    assert queries.finding(base[0]['id'])['origin'] == 'baseline'


def test_high_tier_is_review_first(db):
    put(history_rows() + [('a', '2026-10-10T02:00:00Z', 'Delete', 'secretsmanager/prod-key')] * 40)
    sync()
    row = [r for r in queries.findings(status='All')['findings'] if r['origin'] == 'baseline'][0]
    assert row['severity'] == 'High' and row['triage'] == 'review_first'


def test_below_medium_auto_resolves_open_rows_and_reopens(db):
    risky(db)
    with sqlite3.connect(db) as con:  # simulate a re-score that falls below Medium
        con.execute("UPDATE events SET resource='toy' WHERE resource LIKE 'secretsmanager%'")
    sync()
    row = rows(db)[0]
    assert row[1] == 'Resolved' and json.loads(row[4])['auto_resolved'] == 'score fell below Medium'
    with sqlite3.connect(db) as con:
        con.execute("UPDATE events SET resource='secretsmanager/prod-key' WHERE timestamp='2026-10-10T02:00:00Z'")
    sync()
    assert rows(db)[0][1] == 'Open'


def test_day_without_events_is_retired(db):
    risky(db)
    with sqlite3.connect(db) as con:
        con.execute("DELETE FROM events WHERE timestamp='2026-10-10T02:00:00Z'")
    sync()
    assert rows(db)[0][1] == 'Resolved'
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM baseline_scores WHERE day='2026-10-10'").fetchone()[0] == 0


def test_analyst_status_is_not_reverted_by_sync(db, client):
    risky(db)
    fid = base_id(db)
    assert client.post(f'/findings/{fid}/status', json={'status': 'Acknowledged', 'analyst': 'me', 'reason': 'looking'}).status_code == 200
    sync()
    assert rows(db)[0][1] == 'Acknowledged'
    assert client.post(f'/findings/{fid}/status', json={'status': 'Open', 'analyst': 'me', 'reason': 'again'}).status_code == 200
    with sqlite3.connect(db) as con:  # below Medium now, but an analyst reopened it: their decision stands
        con.execute("UPDATE events SET resource='toy' WHERE resource LIKE 'secretsmanager%'")
    sync()
    assert rows(db)[0][1] == 'Open'


def test_case_can_be_created_from_baseline_finding(db, client):
    risky(db)
    r = client.post('/cases/from-finding', json={'title': 't', 'owner': '', 'actor': 'me', 'request_key': 'k1',
                                                  'finding_id': base_id(db), 'reason': 'x', 'include_account': True})
    assert r.status_code == 201, r.text
    assert {'finding', 'account'} <= {link['kind'] for link in r.json()['links']}
    assert client.get(f"/cases/{r.json()['id']}/timeline").json()['events']
