"""Synthetic database fixtures only; never adopted as pilot evidence."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from scripts import live_history_readiness as readiness

ACCOUNT, STACK = '123456789012', 'argus-ueba-actors'
NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)


@pytest.fixture
def study(tmp_path):
    ledger, native = tmp_path / 'ledger.db', tmp_path / 'events.db'
    plans = readiness.expected_actions(ACCOUNT, STACK)
    with sqlite3.connect(ledger) as db:
        db.execute('CREATE TABLE scope(id INTEGER,contract TEXT)')
        db.execute('INSERT INTO scope VALUES(1,?)', (json.dumps([ACCOUNT, STACK, readiness.PROFILE_SHA]),))
        db.execute('''CREATE TABLE actions(action_id TEXT,day TEXT,persona TEXT,plan TEXT,
                      status TEXT,request_id TEXT,principal_id TEXT,native_event_id TEXT)''')
        for i, (action_id, plan) in enumerate(plans.items()):
            db.execute('INSERT INTO actions VALUES(?,?,?,?,?,?,?,?)', (action_id, plan['day'], plan['persona'],
                       json.dumps(plan), 'provider_verified', f'request-{i}', f'principal-{i}', f'native-{i}'))
        # Bad excluded commissioning/warm-up row must not influence study gates.
        db.execute("INSERT INTO actions VALUES('excluded','2026-10-29','persona-01','{}','claimed_unknown',NULL,NULL,NULL)")
    with sqlite3.connect(native) as db:
        db.execute('''CREATE TABLE events(source TEXT,source_account_id TEXT,event_id TEXT,
            timestamp TEXT,action TEXT,resource TEXT,metadata TEXT)''')
        for i, plan in enumerate(plans.values()):
            stamp = datetime.fromisoformat(plan['planned_utc']) + timedelta(seconds=30)
            metadata = {'requestID': f'request-{i}', 'userIdentity': {'principalId': f'principal-{i}',
                        'type': 'AssumedRole', 'arn': f"arn:aws:sts::{ACCOUNT}:assumed-role/{STACK}-{plan['persona']}/argus-{plan['persona']}"}}
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)', ('aws_cloudtrail', ACCOUNT, f'native-{i}',
                       stamp.isoformat(), plan['operation'], plan['bucket'], json.dumps(metadata)))
    return ledger, native


def check(study, now=NOW):
    return readiness.evaluate(*study, ACCOUNT, STACK, now)


def test_complete_history_gates_and_no_warmup_or_score_claim(study):
    before = [p.read_bytes() for p in study]
    report = check(study)
    assert report['history_gates_pass'] is True
    assert report['eligible_roles'] == 6 and report['eligible_calibration_account_days'] == 18
    assert len(report['days']) == 72 and all(r['status'] == 'usable' for r in report['days'])
    assert report['model_activated'] is False and report['model_release_evaluated'] is False
    assert before == [p.read_bytes() for p in study]
    assert ACCOUNT not in json.dumps(report) and 'principal-' not in json.dumps(report)


def test_current_my_day_never_usable_despite_all_receipts(study):
    # 10Nov16:00UTC is exactly midnight11NovMY; just before it calibration10Nov is open.
    report = check(study, datetime(2026, 11, 10, 15, 59, tzinfo=timezone.utc))
    assert all(r['status'] == 'current_partial' for r in report['days'] if r['day'] == '2026-11-10')
    assert not report['pooled_calibration_history_pass']


@pytest.mark.parametrize('fault', ['missing_native', 'wrong_account', 'wrong_principal', 'wrong_role', 'error', 'pending', 'missing_action'])
def test_status_alone_never_proves_usable_day(study, fault):
    ledger, native = study
    with sqlite3.connect(ledger) as db:
        target, day, persona, event_id = db.execute('SELECT action_id,day,persona,native_event_id FROM actions WHERE day>=? LIMIT 1', ('2026-10-30',)).fetchone()
        if fault == 'pending':
            db.execute("UPDATE actions SET status='api_ok_audit_pending' WHERE action_id=?", (target,))
        elif fault == 'missing_action':
            db.execute('DELETE FROM actions WHERE action_id=?', (target,))
    with sqlite3.connect(native) as db:
        if fault == 'missing_native':
            db.execute('DELETE FROM events WHERE event_id=?', (event_id,))
        elif fault == 'wrong_account':
            db.execute("UPDATE events SET source_account_id='999999999999' WHERE event_id=?", (event_id,))
        elif fault in ('wrong_principal', 'wrong_role', 'error'):
            metadata = json.loads(db.execute('SELECT metadata FROM events WHERE event_id=?', (event_id,)).fetchone()[0])
            if fault == 'error': metadata['errorCode'] = 'AccessDenied'
            elif fault == 'wrong_role': metadata['userIdentity']['arn'] = 'arn:aws:iam::123456789012:root'
            else: metadata['userIdentity']['principalId'] = 'wrong-principal'
            db.execute('UPDATE events SET metadata=? WHERE event_id=?', (json.dumps(metadata), event_id))
    row = next(r for r in check(study)['days'] if r['day'] == day and r['persona'] == persona)
    assert row['status'] == 'incomplete'
    assert row['verified'] < row['planned']


def test_scope_and_stored_plan_drift_rejected(study):
    with sqlite3.connect(study[0]) as db:
        original = db.execute('SELECT contract FROM scope').fetchone()[0]
        db.execute("UPDATE scope SET contract='[]'")
    with pytest.raises(ValueError, match='scope'):
        check(study)
    with sqlite3.connect(study[0]) as db:
        db.execute('UPDATE scope SET contract=?', (original,))
        db.execute("UPDATE actions SET plan='{}' WHERE day='2026-10-30'")
    with pytest.raises(ValueError, match='frozen plan'):
        check(study)


def test_early_report_does_not_mistake_future_for_normal(study):
    # Empty study ledger represents the actual before-history state.
    with sqlite3.connect(study[0]) as db:
        db.execute("DELETE FROM actions WHERE day>'2026-10-29'")
    report = check(study, datetime(2026, 10, 29, 0, tzinfo=timezone.utc))
    assert all(r['status'] == 'future' for r in report['days'])
    assert report['status'] == 'history_pending' and report['eligible_roles'] == 0


def test_five_fit_days_must_span_seven_calendar_days(study):
    with sqlite3.connect(study[0]) as db:
        db.execute("DELETE FROM actions WHERE day IN ('2026-11-04','2026-11-05')")
    report = check(study)
    assert all(len(r['usable_dates']['fit']) == 5 for r in report['roles'])
    assert all(not r['fitting_history_pass'] for r in report['roles'])
    assert not report['history_gates_pass']
