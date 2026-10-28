"""Prospective schedule and immutable ledger migration; no cloud calls."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import sqlite3

import pytest

from scripts import local_pilot as pilot, run_persona_history as history
from scripts.migrate_pilot_v2 import migrate_scope
from scripts.persona_history_plan import make_plan


def test_v1_frozen_v2_only_daily_activity_and_provenance_change():
    old = history.PROFILE.with_name('persona_profiles_v1.json')
    assert hashlib.sha256(old.read_bytes()).hexdigest() == pilot.LEGACY_PROFILE_SHA
    assert hashlib.sha256(history.PROFILE.read_bytes()).hexdigest() == pilot.PROFILE_SHA
    v1, v2 = json.loads(old.read_bytes()), json.loads(history.PROFILE.read_bytes())
    for key in ('schema', 'status', 'parameter_provenance'):
        v1.pop(key); v2.pop(key)
    for a, b in zip(v1['personas'], v2['personas']):
        for key in ('weekday_active_probability', 'weekend_active_probability'):
            assert b[key] == 1.0
            a.pop(key); b.pop(key)
    assert v1 == v2


def test_daily_coverage_budget_and_reserved_case_reads():
    profiles = json.loads(history.PROFILE.read_bytes())
    plans = [make_plan(profiles, date(2026, 10, 29) + timedelta(days=i)) for i in range(16)]
    assert all(len({r['persona'] for r in p['actions']}) == 6 for p in plans)
    assert sum(p['planned_actions'] for p in plans) == 292
    assert max(p['planned_actions'] * 5 for p in plans) == 115
    assert sum(p['planned_actions'] * 5 for p in plans) + 5 == 1465 < history.MAX_PILOT_CALLS
    for p in plans[-2:]:
        for target in ('persona-01', 'persona-02'):
            assert any(r['persona'] == target and r['operation'] == 'GetObject' for r in p['actions'])


def probe_db():
    db = sqlite3.connect(':memory:')
    account, stack = '123456789012', 'argus-ueba-actors'
    identity = hashlib.sha256(f'{pilot.LEGACY_PROFILE_SHA}|commissioning-v1|{account}|{stack}'.encode()).hexdigest()
    db.execute('CREATE TABLE scope(id INTEGER,contract TEXT)')
    db.execute('INSERT INTO scope VALUES(1,?)', (json.dumps([account, stack, pilot.LEGACY_PROFILE_SHA], separators=(',', ':')),))
    db.execute('CREATE TABLE actions(action_id TEXT,day TEXT,status TEXT,plan TEXT,native_event_id TEXT)')
    db.execute('INSERT INTO actions VALUES(?,?,?,?,?)', (identity, '2026-10-28', 'provider_verified',
               json.dumps({'purpose': 'commissioning_exclude_from_baseline', 'ordinal': 0}), 'native-original'))
    db.execute('CREATE TABLE runs(day TEXT,reserved_calls INTEGER)')
    db.execute("INSERT INTO runs VALUES('2026-10-28',5)")
    db.commit()
    return db, account, stack


def test_migration_keeps_probe_receipt_runs_and_is_recoverable():
    db, account, stack = probe_db()
    before = db.execute('SELECT * FROM actions').fetchall(), db.execute('SELECT * FROM runs').fetchall()
    migrate_scope(db, account, stack)
    migrate_scope(db, account, stack)  # interrupted config write may resume; no new history
    assert before == (db.execute('SELECT * FROM actions').fetchall(), db.execute('SELECT * FROM runs').fetchall())
    assert json.loads(db.execute('SELECT contract FROM scope').fetchone()[0])[-1] == pilot.PROFILE_SHA
    assert db.execute('SELECT count(*) FROM scope_migrations').fetchone()[0] == 1
    db.close()


@pytest.mark.parametrize('change', ['ordinary', 'unverified', 'budget', 'scope'])
def test_migration_refuses_changed_history_atomically(change):
    db, account, stack = probe_db()
    if change == 'ordinary':
        db.execute("INSERT INTO actions VALUES('ordinary','2026-10-29','missed','{}',NULL)")
    elif change == 'unverified':
        db.execute("UPDATE actions SET status='claimed_unknown'")
    elif change == 'budget':
        db.execute('UPDATE runs SET reserved_calls=6')
    else:
        db.execute("UPDATE scope SET contract='other'")
    db.commit()
    original = db.execute('SELECT contract FROM scope').fetchone()
    with pytest.raises(ValueError):
        migrate_scope(db, account, stack)
    assert db.execute('SELECT contract FROM scope').fetchone() == original
    db.close()
