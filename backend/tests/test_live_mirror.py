"""Live mirror and live feed: read-only source, study guard, idempotence, analyst state wins. Temp SQLite only."""
from datetime import datetime, timezone
import hashlib
import json
import sqlite3

import pytest

from backend import alert_store, event_store as events
from backend.tests.test_baseline_alerts import put, history_rows
from workspace_next import case_store as cases, live_mirror as lm

BEFORE_GUARD = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
AFTER_GUARD = datetime(2026, 11, 16, 1, tzinfo=lm.MYT)


def build(monkeypatch, tmp_path, name, rows=(), marker=False):
    folder = tmp_path / name
    folder.mkdir()
    path = folder / ('preview.db' if marker else 'events.db')
    monkeypatch.setattr(events, 'DB_PATH', path)
    events.init_db(); alert_store.init_alerts_db(); cases.init_db()
    put(list(rows))
    if marker:
        (folder / 'workspace-copy.json').write_text(json.dumps({'not_live': True, 'copy_db': str(path)}))
    return path


@pytest.fixture
def pair(monkeypatch, tmp_path):
    assert not events._PG, 'Run with DATABASE_URL=sqlite-local'
    rows = history_rows() + [('a', '2026-10-10T02:00:00Z', 'Read', 'secretsmanager/prod-key')] * 4
    source = build(monkeypatch, tmp_path, 'source', rows)
    dest = build(monkeypatch, tmp_path, 'dest', marker=True)
    monkeypatch.setattr(events, 'DB_PATH', source)  # put() in tests seeds the source
    return source, dest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count(path, sql):
    with sqlite3.connect(path) as con:
        return con.execute(sql).fetchone()[0]


def test_pass_copies_new_rows_second_pass_adds_none_and_source_untouched(pair):
    source, dest = pair
    before = digest(source)
    first = lm.run_pass(source, dest, BEFORE_GUARD, tick_snapshot=False)
    assert first['events_added'] == 28 and first['guard_active'] is True
    assert count(dest, 'SELECT COUNT(*) FROM events') == 28
    assert count(dest, 'SELECT COUNT(*) FROM workspace_baseline_alerts') == 1  # sync ran
    second = lm.run_pass(source, dest, BEFORE_GUARD, tick_snapshot=False)
    assert second['events_added'] == 0 and second['alerts_added'] == 0
    assert digest(source) == before
    assert json.loads((dest.parent / lm.STATUS_FILE).read_text())['events_added'] == 0


def test_study_guard_skips_events_and_alerts_from_14_nov_myt(pair):
    source, dest = pair
    put([('a', '2026-11-13T15:59:59Z', 'Read', 'toy'), ('a', '2026-11-13T16:00:00Z', 'Read', 'toy'), ('a', '2026-11-20T00:00:00Z', 'Read', 'toy')])
    with sqlite3.connect(source) as con:
        con.execute("INSERT INTO alerts (user_id,alert_type,severity,title,created_at) VALUES ('a','new_user','Low','late','2026-11-14T00:00:01+08:00')")
        con.execute("INSERT INTO alerts (user_id,alert_type,severity,title,created_at) VALUES ('a','new_user','Low','ok','2026-11-13T23:59:00+08:00')")
    status = lm.run_pass(source, dest, BEFORE_GUARD, tick_snapshot=False)
    assert status['alerts_added'] == 1
    assert count(dest, "SELECT COUNT(*) FROM events WHERE timestamp >= '2026-11-13T16:00:00Z'") == 0
    assert count(dest, "SELECT COUNT(*) FROM events WHERE timestamp = '2026-11-13T15:59:59Z'") == 1
    assert lm.run_pass(source, dest, AFTER_GUARD, tick_snapshot=False)['guard_active'] is False
    assert count(dest, "SELECT COUNT(*) FROM events WHERE timestamp >= '2026-11-13T16:00:00Z'") == 2


def test_guard_constants_and_boundaries():
    assert lm.GUARD_START.isoformat() == '2026-11-14T00:00:00+08:00' and lm.GUARD_END.isoformat() == '2026-11-16T00:00:00+08:00'
    assert lm.blocked('2026-11-14T00:00:00+08:00', BEFORE_GUARD) and not lm.blocked('2026-11-13T23:59:59+08:00', BEFORE_GUARD)
    assert lm.blocked('garbage', BEFORE_GUARD) and not lm.blocked('2026-11-20T00:00:00Z', AFTER_GUARD)


def test_existing_copy_rows_and_analyst_state_are_never_overwritten(pair):
    source, dest = pair
    lm.run_pass(source, dest, BEFORE_GUARD, tick_snapshot=False)
    with sqlite3.connect(source) as con:
        con.execute("INSERT INTO alerts (id,user_id,alert_type,severity,title,created_at) VALUES (5,'a','new_user','Low','t','2026-10-01T00:00:00Z')")
    lm.run_pass(source, dest, BEFORE_GUARD, tick_snapshot=False)
    with sqlite3.connect(dest) as con:
        con.execute("UPDATE alerts SET status='Resolved' WHERE id=5")
        con.execute("UPDATE workspace_baseline_alerts SET status='False Positive'")
    with sqlite3.connect(source) as con:
        con.execute("UPDATE alerts SET status='Open',title='changed' WHERE id=5")
    lm.run_pass(source, dest, BEFORE_GUARD, tick_snapshot=False)
    assert count(dest, "SELECT COUNT(*) FROM alerts WHERE id=5 AND status='Resolved' AND title='t'") == 1
    assert count(dest, "SELECT COUNT(*) FROM workspace_baseline_alerts WHERE status='False Positive'") == 1


def test_refuses_unmarked_or_live_dest(pair, tmp_path):
    source, dest = pair
    with pytest.raises(SystemExit):
        lm.run_pass(source, source, BEFORE_GUARD, tick_snapshot=False)
    (dest.parent / 'workspace-copy.json').write_text(json.dumps({'not_live': False, 'copy_db': str(dest)}))
    with pytest.raises(SystemExit):
        lm.run_pass(source, dest, BEFORE_GUARD, tick_snapshot=False)


def test_locked_source_skips_the_pass(pair, monkeypatch):
    source, dest = pair
    def boom(*a, **k): raise sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(lm, '_new_rows', boom)
    assert lm.run_pass(source, dest, BEFORE_GUARD, tick_snapshot=False) is None
    assert count(dest, 'SELECT COUNT(*) FROM events') == 0


def test_feed_has_sources_and_hides_emails_and_account_numbers(pair, tmp_path):
    source, dest = pair
    put([('b', '2026-11-10T11:30:00Z', 'ConsoleLogin', 'x')])
    with sqlite3.connect(source) as con:
        con.execute("UPDATE events SET account_label='someone@example.com 123456789012' WHERE account_key='b'")
    lm.run_pass(source, dest, BEFORE_GUARD, tick_snapshot=False)
    tick = tmp_path / 'tick.json'
    tick.write_text(json.dumps({'at_utc': '2026-11-10T11:55:00+00:00', 'ok': True}))
    out = lm.feed(dest, dest.parent, BEFORE_GUARD, tick_path=tick)
    text = json.dumps(out)
    assert set(out['sources']) == set(lm.SOURCES) and out['sources']['aws_cloudtrail']['events_last_hour'] >= 1
    assert '@example.com' not in text and '123456789012' not in text and '[email hidden]' in text
    assert out['collector']['ok'] is True and out['mirror']['events_added'] == 29
    assert 1 <= len(out['sources']['aws_cloudtrail']['newest']) <= 8  # repeats collapse
    assert 'ip_address' not in text
