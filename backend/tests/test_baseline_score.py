"""Baseline risk score v1: signals, tiers, MYT day boundary, finding context. Temp SQLite only."""
from datetime import date, datetime, timedelta, timezone
import sqlite3

import pytest

from backend import alert_store, event_store as events
from workspace_next import baseline_score as bs, case_store, queries

DAY = date(2026, 10, 10)  # scored day (MYT)


def make_db(path, rows):
    """rows: (account_key, utc timestamp, source, action, resource)."""
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, account_key TEXT, account_label TEXT, '
                    'account_kind TEXT, timestamp TEXT, source TEXT, action TEXT, resource TEXT)')
        con.executemany("INSERT INTO events (account_key,account_label,account_kind,timestamp,source,action,resource) "
                        "VALUES (?,?,'role',?,?,?,?)", [(r[0], r[0], *r[1:]) for r in rows])
    return path


def history(n=6, acct='a', per_day=4, action='Read', resource='toy'):
    # 02:00 UTC = 10:00 MYT, so every history event sits in one usual hour
    return [(acct, f'2026-10-{DAY.day - i:02d}T02:00:00Z', 'aws_cloudtrail', action, resource)
            for i in range(1, n + 1) for _ in range(per_day)]


def today(n=4, action='Read', resource='toy', hour=2):
    return [('a', f'2026-10-{DAY.day:02d}T{hour:02d}:00:00Z', 'aws_cloudtrail', action, resource)] * n


def result(tmp_path, rows, name='e.db'):
    db = make_db(tmp_path / name, rows)
    return bs.account_days(db, 'a', 14)[0]


def test_cold_start_is_learning(tmp_path):
    r = result(tmp_path, history(4) + today())
    assert r['tier'] == 'Learning' and r['score'] is None
    assert r['facts'] == ['4 of 5 days of history']


def test_quiet_normal_day_is_low(tmp_path):
    r = result(tmp_path, history() + today())
    assert r['tier'] == 'Low' and r['score'] == 0 and r['facts'] == []
    assert r['history_days'] == 6 and r['events_today'] == 4


def test_one_new_action(tmp_path):
    r = result(tmp_path, history() + today(action='Write'))
    assert r['signals']['new_action'] == 0.6
    assert any('never seen' in f and 'Write' in f for f in r['facts'])


def test_new_sensitive_resource_reaches_medium(tmp_path):
    r = result(tmp_path, history() + today(resource='secretsmanager/prod-key'))
    assert r['signals']['sensitive_new'] == 1.0
    assert r['tier'] in ('Medium', 'High')


def test_volume_8x(tmp_path):
    r = result(tmp_path, history() + today(n=32))
    assert r['signals']['volume'] == 1.0


def test_volume_drop_is_zero(tmp_path):
    assert result(tmp_path, history(per_day=8) + today(n=1))['signals']['volume'] == 0.0


def test_unusual_hours(tmp_path):
    r = result(tmp_path, history() + today(hour=20))  # 04:00 MYT, outside usual 10:00
    assert r['signals']['unusual_hours'] == 1.0


def test_usual_hours_widened_by_one_hour(tmp_path):
    # history at 10:00 MYT; an event at 11:00 MYT (03:00 UTC) is still usual, 12:00 MYT is not
    assert result(tmp_path, history() + today(hour=3))['signals']['unusual_hours'] == 0.0
    assert result(tmp_path, history() + today(hour=4), 'f.db')['signals']['unusual_hours'] == 1.0


def test_usual_hours_wrap_midnight(tmp_path):
    hist = [('a', f'2026-10-{DAY.day - i:02d}T15:00:00Z', 'aws_cloudtrail', 'Read', 'toy') for i in range(2, 8) for _ in range(4)]
    r = result(tmp_path, hist + [('a', '2026-10-09T16:00:00Z', 'aws_cloudtrail', 'Read', 'toy')])  # 00:00 MYT Oct 10
    assert r['day'] == '2026-10-10' and r['signals']['unusual_hours'] == 0.0


def test_novelty_discount_crawler_vs_stable(tmp_path):
    crawler = [('a', f'2026-10-{DAY.day - i:02d}T02:00:00Z', 'aws_cloudtrail', f'Act{i}', 'toy') for i in range(1, 8)]
    r = result(tmp_path, crawler + today(action='NewAct'))
    assert r['rho_action'] == 1.0 and r['signals']['new_action'] == 0.0
    assert any('novelty is discounted' in f for f in r['facts'])
    stable = result(tmp_path, history() + today(action='Write'), 's.db')  # one first-ever action
    assert stable['rho_action'] == 0.0 and stable['signals']['new_action'] == 0.6


def test_fact_hygiene():
    assert bs._name('role/123456789012/x') == 'role/<account>/x'
    assert bs._name('{"bucketName": "b", "key": "k"}') == 'bucketName'
    assert len(bs._name('x' * 100)) == 60
    assert bs._short(['a', 'b', 'c', 'd', 'e']) == 'a, b, c, +2 more'


def test_no_resource_day_renormalises(tmp_path):
    r = result(tmp_path, history() + today(action='Write', resource=''))
    assert r['signals']['new_resource'] is None
    # new_action 0.6 * 0.25 over total weight 0.75 (new_resource excluded)
    assert r['score'] == round(100 * (0.25 * 0.6) / 0.75)


def test_myt_day_boundary(tmp_path):
    # 16:30 UTC on Oct 10 is 00:30 MYT on Oct 11
    db = make_db(tmp_path / 'e.db', history() + [('a', '2026-10-10T16:30:00Z', 'aws_cloudtrail', 'Read', 'toy')])
    assert bs.account_days(db, 'a', 14)[0]['day'] == '2026-10-11'


def test_null_account_key_ignored(tmp_path):
    db = make_db(tmp_path / 'e.db', history() + today() + [(None, '2026-10-10T02:00:00Z', 'x', 'Read', 'toy')])
    assert set(bs.load(db)) == {'a'}


def test_api_functions_newest_first_and_summary(tmp_path):
    db = make_db(tmp_path / 'e.db', history() + today())
    days = [r['day'] for r in bs.account_days(db, 'a', 14)]
    assert days == sorted(days, reverse=True) and days[0] == DAY.isoformat()
    s = bs.summary(db)
    assert s['day'] == DAY.isoformat() and s['accounts'][0]['account_key'] == 'a'
    assert bs.summary(db, '2026-10-05')['accounts'][0]['tier'] == 'Learning'


def test_finding_context_carries_baseline(monkeypatch, tmp_path):
    assert not events._PG, 'Run with DATABASE_URL=sqlite-local'
    monkeypatch.setattr(events, 'DB_PATH', tmp_path / 'events.db')
    events.init_db(); alert_store.init_alerts_db(); case_store.init_db()
    now = datetime.now(timezone.utc)
    with events._db() as con:
        cur = events._cursor(con)
        for i in range(0, 7):  # six prior days plus today, so the finding's day is scored
            at = (now - timedelta(days=i)).strftime('%Y-%m-%dT%H:%M:%SZ')
            cur.execute('''INSERT INTO events ("user",timestamp,source,action,resource,ip_address,metadata,
                ingested_at,event_id,source_account_id,payload_digest,account_key,account_label,account_kind,account_basis)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                ('acct', at, 'aws_cloudtrail', 'Read', 'toy', '', '{}', at, f'n{i}', 'ns', f'd{i}',
                 'acct', 'acct', 'role', 'native'))
    alert_store.create_alert('acct', 'rarity_spike', 'High', 'Rule facts')
    row = queries.findings(category='all')['findings'][0]
    assert row['baseline']['tier'] in ('Low', 'Medium', 'High') and 'score' in row['baseline']
    assert queries.finding(row['id'])['baseline'] == row['baseline']
    # an account with no events falls back to Learning
    alert_store.create_alert('ghost', 'rarity_spike', 'High', 'Rule facts')
    ghost = [r for r in queries.findings(category='all')['findings'] if r['user_id'] == 'ghost'][0]
    assert ghost['baseline'] == {'tier': 'Learning'}
