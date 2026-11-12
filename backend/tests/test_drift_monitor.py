"""Drift monitor (L13): observations only. Synthetic events in a temp SQLite; no live data.
Key demonstration: a slow 15%/day volume increase never leaves Low in the rolling baseline score, but the
drift monitor flags it. The baseline outputs and the security finding counts are unchanged by a run."""
from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
from uuid import uuid4

import pytest

from backend import alert_store, baseline_scorer, drift_monitor as dm, event_store as events
from workspace_next import case_store as cases, operations, queries

DAY = date(2026, 11, 10)
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)  # 20:00 MYT on DAY


def put(key, day, hour, action='Read', resource='toy', source='aws_cloudtrail', kind='role', label='acct-label'):
    """One event at <hour> UTC on <day> (hour 2 = 10:00 MYT)."""
    ts = f'{day.isoformat()}T{hour:02d}:00:00Z'
    i = uuid4().hex
    with events._db() as con:
        events._cursor(con).execute('''INSERT INTO events ("user",timestamp,source,action,resource,ip_address,metadata,
            ingested_at,event_id,source_account_id,payload_digest,account_key,account_label,account_kind,account_basis)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (key, ts, source, action, resource, '', '{}', ts, f'e{i}', 's', f'd{i}', key, label, kind, 'x'))


def daily(key, counts, end=DAY, **kw):
    """counts oldest first, one entry per consecutive calendar day ending at `end`; 0 = inactive day."""
    for i, n in enumerate(counts):
        d = end - timedelta(days=len(counts) - 1 - i)
        for j in range(n):
            put(key, d, (3 * j) % 12, **kw)  # spread over 08:00-20:00 MYT


def observations(kind=None):
    with sqlite3.connect(events.DB_PATH) as con:
        q, a = 'SELECT user_id,alert_type,severity,status,day,details FROM alerts WHERE alert_type IN (?,?)', list(dm.TYPES)
        if kind:
            q, a = q.replace('IN (?,?)', '=?'), [kind]
        return con.execute(q, a).fetchall()


def baseline_snapshot():
    with sqlite3.connect(events.DB_PATH) as con:
        return (con.execute('SELECT * FROM baseline_scores ORDER BY 1,2').fetchall(),
                con.execute("SELECT * FROM alerts WHERE alert_type='baseline_risk' ORDER BY id").fetchall())


@pytest.fixture
def db(monkeypatch, tmp_path):
    assert not events._PG, 'Run with DATABASE_URL=sqlite-local'
    monkeypatch.setattr(events, 'DB_PATH', tmp_path / 'events.db')
    events.init_db(); alert_store.init_alerts_db(); cases.init_db()
    baseline_scorer.ensure_schema()
    return events.DB_PATH


def test_stable_account_is_not_flagged(db):
    daily('a', [4] * 35)
    out = dm.run_once(DAY, NOW)
    assert out['accounts_evaluated'] == 1 and out['accounts_flagged'] == 0 and not observations()


def test_slow_insider_absorbed_by_baseline_but_caught_by_drift(db):
    counts = [4] * 14 + [round(4 * 1.15 ** k) for k in range(1, 22)]  # +15% a day for 21 days (about 19x)
    daily('a', counts)
    baseline_scorer.backfill(NOW)
    before = baseline_snapshot()
    tiers = {r[3] for r in before[0]}
    assert tiers <= {'Learning', 'Low'}, tiers            # the rolling score never leaves Low ...
    assert max(r[2] for r in before[0] if r[2] is not None) < 30 and not before[1]  # ... and raises no finding
    out = dm.run_once(DAY, NOW)
    assert out['accounts_flagged'] == 1                   # ... but the drift monitor flags the account
    (user, kind, sev, status, day, details), = observations('behaviour_drift')
    d = json.loads(details)
    assert (user, sev, status, day) == ('a', 'Info', 'Open', DAY.isoformat()) and 'volume' in d['fired']
    assert d['measures']['volume_shift_log2'] >= 1.0 and 'Median daily events rose from' in d['facts'][0]
    assert d['windows']['recent'] == ['2026-11-04', '2026-11-10'] and d['thresholds']['volume_shift_log2'] == 1.0
    assert baseline_snapshot() == before                  # observation only: baseline untouched


def test_new_resource_mix_is_flagged(db):
    daily('a', [4] * 28)
    for d in range(7):
        for j in range(4):
            put('a', DAY - timedelta(days=d), 2 + j % 3, action='Write', resource=f'new-{j}')
    # replace the recent days' usual events: only the new mix in the last 7 days
    with sqlite3.connect(events.DB_PATH) as con:
        con.execute("DELETE FROM events WHERE resource='toy' AND timestamp >= ?", ('2026-11-04',))
    dm.run_once(DAY, NOW)
    (_, _, _, _, _, details), = observations('behaviour_drift')
    d = json.loads(details)
    assert {'resource_mix', 'new_items'} <= set(d['fired']) and d['measures']['new_item_share'] >= 0.5


def test_fewer_than_14_active_days_not_evaluated(db):
    daily('a', [4] * 10 + [40] * 3)  # an obvious jump, but only 13 active days
    out = dm.run_once(DAY, NOW)
    assert out['accounts_evaluated'] == 0 and out['accounts_not_evaluated'] == 1 and not observations()


def test_source_drop_and_silence_are_flagged(db):
    for i in range(1, 15):
        for h in range(0, 12):
            put('a', DAY - timedelta(days=i), h)          # 12 a day across the whole 08:00-20:00 MYT window
    put('a', DAY, 0); put('a', DAY, 1)                     # today: two events, early
    out = dm.run_once(DAY, datetime(2026, 11, 10, 11, 0, tzinfo=timezone.utc))  # 19:00 MYT
    assert out['sources_flagged'] == 1
    (user, _, sev, _, _, details), = observations('source_drift')
    assert (user, sev) == ('aws_cloudtrail', 'Info') and json.loads(details)['fired'] == ['low_volume', 'silent_gap']
    # 14:30 MYT: below 18:00, so no low-volume check; silence is judged only up to now
    day_before = DAY - timedelta(days=1)
    stamps = [datetime.combine(day_before - timedelta(days=i), datetime.min.time(), tzinfo=dm.MYT) + timedelta(hours=9 + h)
              for i in range(14) for h in range(10)]
    cfg = dm.load_config()
    early = datetime.combine(DAY, datetime.min.time(), tzinfo=dm.MYT) + timedelta(hours=14, minutes=30)
    healthy = stamps + [datetime.combine(DAY, datetime.min.time(), tzinfo=dm.MYT) + timedelta(hours=h) for h in (8, 9, 10, 11, 12, 13, 14)]
    r = dm.source_drift(healthy, DAY, early, cfg)
    assert r and not r['flagged']
    quiet = stamps + [datetime.combine(DAY, datetime.min.time(), tzinfo=dm.MYT) + timedelta(hours=8, minutes=30)] * 9
    r = dm.source_drift(quiet, DAY, early.replace(hour=15), cfg)
    assert r['fired'] == ['silent_gap']


def test_one_observation_per_subject_per_day(db):
    daily('a', [4] * 14 + [30] * 7)
    for _ in range(3):
        dm.run_once(DAY, NOW)
    assert len(observations('behaviour_drift')) == 1
    dm.run_once(DAY + timedelta(days=1), NOW + timedelta(days=1))  # a new MYT day: new row only if still flagged
    assert len(observations('behaviour_drift')) <= 2


def test_infrastructure_account_is_labelled(db):
    daily('svc', [4] * 14 + [30] * 7, kind='service', label='collector-bot')
    dm.run_once(DAY, NOW)
    (_, _, _, _, _, details), = observations('behaviour_drift')
    assert json.loads(details)['monitoring_infrastructure'] is True


def test_observations_are_not_security_findings(db):
    daily('a', [4] * 14 + [30] * 7)
    security = lambda: queries.findings(limit=500, category='security', status='All')['matched_in_scan']
    open_sec = lambda: operations.overview(tmp_snapshot)['open_security_findings']
    tmp_snapshot = db.parent / 'none.json'
    before = security(), open_sec()
    dm.run_once(DAY, NOW)
    assert (security(), open_sec()) == before
    obs = queries.findings(limit=500, category='observation', status='All')['findings']
    assert [o['alert_type'] for o in obs] == ['behaviour_drift'] and obs[0]['origin'] == 'observation'
    assert queries.findings(limit=500, category='unverified', status='All')['matched_in_scan'] == 0
    assert operations.overview(tmp_snapshot)['open_observations'] == 1
