from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from scripts import reserved_study as reserved, evaluate_reserved_study as evaluator
from scripts import run_persona_history as history, train_live_daily as trainer
from scripts.tests.test_live_daily_training import dataset
from scripts.tests.test_live_daily_export import export_study
from scripts.tests.test_live_history_readiness import study, ACCOUNT, STACK, NOW
from scripts.tests.test_persona_history import clock, provider
from scripts.tests.test_local_pilot import cfg, mocked

FINAL = reserved.EVALUATE_FROM + timedelta(minutes=1)


@pytest.mark.parametrize('day', list(reserved.CASES))
def test_substitution_exactly_two_first_reads_preserves_everything_else(day, monkeypatch):
    instant = datetime.fromisoformat(day).replace(tzinfo=reserved.MALAYSIA)
    monkeypatch.setattr(history, 'utc_now', lambda: instant)
    ordinary = history.plan_today(ACCOUNT, STACK)
    changed = reserved.plan_for_date(ACCOUNT, STACK, day, instant)
    assert len(changed['actions']) == len(ordinary['actions'])
    originals = {r['action_id']: r for r in ordinary['actions']}
    substitutions = []
    for row in changed['actions']:
        before = originals[row['action_id']]
        if 'case_slot' in row:
            substitutions.append(row)
            assert row['operation'] == before['operation'] == 'GetObject'
            assert row['planned_utc'] == before['planned_utc']
            assert row['bucket'].endswith('-p06') and before['bucket'] != row['bucket']
            assert {k: v for k, v in row.items() if k not in ('bucket', 'symbolic_bucket', 'purpose', 'case_slot')} == {
                k: v for k, v in before.items() if k not in ('bucket', 'symbolic_bucket', 'purpose', 'case_slot')}
            candidates = [r for r in ordinary['actions'] if r['persona'] == row['persona'] and r['operation'] == 'GetObject']
            assert row['planned_utc'] == min(r['planned_utc'] for r in candidates)
        else:
            assert row == before
    assert {r['persona'] for r in substitutions} == {s['persona'] for s in changed['case_availability'] if s['status'] == 'available'}


@pytest.fixture
def case_store(tmp_path):
    state = tmp_path / 'state'
    state.mkdir()
    ledger = state / 'ledger.db'
    events = tmp_path / 'case-events.db'
    with history.ledger(ledger) as db, sqlite3.connect(events) as native:
        db.execute('INSERT INTO scope VALUES (1,?)', (json.dumps([ACCOUNT, STACK, reserved.PROFILE_SHA]),))
        native.execute('''CREATE TABLE events (
            event_id TEXT, source TEXT, source_account_id TEXT, timestamp TEXT,
            action TEXT, resource TEXT, ip_address TEXT, metadata TEXT, ingested_at TEXT)''')
        i = 0
        for day in reserved.CASES:
            for row in reserved.plan_for_date(ACCOUNT, STACK, day)['actions']:
                planned = datetime.fromisoformat(row['planned_utc'])
                identity = f'{STACK}-{row["persona"]}/argus-{row["persona"]}'
                metadata = {'requestID': f'request-{i}', 'userIdentity': {
                    'principalId': f'principal-{i}', 'type': 'AssumedRole',
                    'arn': f'arn:aws:sts::{ACCOUNT}:assumed-role/{identity}'}}
                native_id = f'native-{i}'
                db.execute('''INSERT INTO actions
                    (action_id,day,persona,plan,status,attempted_at,request_id,principal_id,completed_at,native_event_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (row['action_id'], day, row['persona'], json.dumps(row), 'provider_verified',
                     (planned + timedelta(seconds=1)).isoformat(), f'request-{i}', f'principal-{i}',
                     (planned + timedelta(seconds=2)).isoformat(), native_id))
                native.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',
                    (native_id, 'aws_cloudtrail', ACCOUNT, (planned + timedelta(seconds=30)).isoformat(),
                     row['operation'], row['bucket'], '203.0.113.10', json.dumps(metadata),
                     (planned + timedelta(seconds=35)).isoformat()))
                i += 1
        db.commit()
    return ledger, events


def test_all_native_receipts_and_private_output_without_mutation(case_store):
    before = [p.read_bytes() for p in case_store]
    rows = evaluator.audit_days(*case_store, ACCOUNT, STACK, FINAL)
    assert len(rows) == 12
    assert sum(r['status'] == 'eligible_for_inference' for r in rows) == 11
    unavailable = next(r for r in rows if not r['slot_available'])
    assert (unavailable['date_local'], unavailable['persona'], unavailable['status']) == ('2026-11-15', 'persona-01', 'unavailable_no_planned_target_read')
    assert 'observation' not in unavailable
    assert sum(r['is_target_account_day'] for r in rows) == 4
    assert all(r['substitution_verified'] for r in rows if r['is_target_account_day'] and r['slot_available'])
    # Observations expose aggregates, not raw native identity/IP.
    text = json.dumps(rows)
    assert ACCOUNT not in text and '203.0.113.10' not in text and 'principal-' not in text
    assert before == [p.read_bytes() for p in case_store]


@pytest.mark.parametrize('fault', ['late', 'missing', 'wrong_role', 'wrong_request', 'wrong_bucket', 'failed',
                                 'missing_ip', 'invalid_ip', 'pending', 'missed', 'missing_claim'])
def test_claims_cannot_replace_exact_native_coverage(case_store, fault):
    ledger, events = case_store
    plan = reserved.plan_for_date(ACCOUNT, STACK, '2026-11-14')
    selected = next(r for r in plan['actions'] if r.get('case_slot') == '2026-11-14/persona-01')
    with sqlite3.connect(ledger) as db:
        native_id = db.execute('SELECT native_event_id FROM actions WHERE action_id=?', (selected['action_id'],)).fetchone()[0]
        if fault == 'pending':
            db.execute("UPDATE actions SET status='api_ok_audit_pending' WHERE action_id=?", (selected['action_id'],))
        elif fault == 'missed':
            db.execute("UPDATE actions SET status='missed',request_id=NULL,native_event_id=NULL WHERE action_id=?", (selected['action_id'],))
        elif fault == 'missing_claim':
            db.execute('DELETE FROM actions WHERE action_id=?', (selected['action_id'],))
    with sqlite3.connect(events) as db:
        if fault == 'late':
            db.execute('UPDATE events SET ingested_at=? WHERE event_id=?', ((reserved.CUTOFF + timedelta(seconds=1)).isoformat(), native_id))
        elif fault == 'missing':
            db.execute('DELETE FROM events WHERE event_id=?', (native_id,))
        elif fault in ('missing_ip', 'invalid_ip'):
            db.execute('UPDATE events SET ip_address=? WHERE event_id=?', ('' if fault == 'missing_ip' else 'bad', native_id))
        elif fault == 'wrong_bucket':
            db.execute("UPDATE events SET resource='wrong-bucket' WHERE event_id=?", (native_id,))
        elif fault in ('wrong_role', 'wrong_request', 'failed'):
            metadata = json.loads(db.execute('SELECT metadata FROM events WHERE event_id=?', (native_id,)).fetchone()[0])
            if fault == 'wrong_role': metadata['userIdentity']['arn'] += '-other'
            elif fault == 'wrong_request': metadata['requestID'] = 'wrong'
            else: metadata['errorCode'] = 'AccessDenied'
            db.execute('UPDATE events SET metadata=? WHERE event_id=?', (json.dumps(metadata), native_id))
    rows = evaluator.audit_days(*case_store, ACCOUNT, STACK, FINAL)
    own = next(r for r in rows if r['date_local'] == '2026-11-14' and r['persona'] == 'persona-01')
    assert own['status'].startswith('unscored')
    assert 'observation' not in own


def test_cutoff_and_freeze_date_are_hard_guards(case_store, tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='cutoff'):
        evaluator.audit_days(*case_store, ACCOUNT, STACK, reserved.CUTOFF - timedelta(seconds=1))
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 29, tzinfo=timezone.utc)
    monkeypatch.setattr(reserved, 'datetime', Clock)
    with pytest.raises(ValueError, match='13 November'):
        reserved.freeze(tmp_path / 'absent', tmp_path / 'release.json', ACCOUNT, STACK)


def test_missing_release_refuses_before_ledger_or_provider_io(tmp_path, monkeypatch):
    instant = datetime(2026, 11, 14, 8, tzinfo=reserved.MALAYSIA)
    monkeypatch.setattr(history, 'utc_now', lambda: instant)
    plan = reserved.plan_for_date(ACCOUNT, STACK, '2026-11-14', instant)
    monkeypatch.setattr(history, 'ledger', lambda *_: pytest.fail('Claims before valid release'))
    with pytest.raises((ValueError, FileNotFoundError)):
        history.execute(plan, tmp_path, reserved=True)
    assert not list(tmp_path.iterdir())


def test_ordinary_executor_cannot_bypass_reserved_day(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'utc_now', lambda: datetime(2026, 11, 14, 8, tzinfo=reserved.MALAYSIA))
    plan = history.plan_today(ACCOUNT, STACK)
    monkeypatch.setattr(history, 'ledger', lambda *_: pytest.fail('Claim before date guard'))
    with pytest.raises(ValueError, match='reserved'):
        history.execute(plan, tmp_path)


@pytest.mark.parametrize('day', list(reserved.CASES))
def test_reserved_executor_uses_existing_budget_claims_and_never_retries(day, clock, provider, tmp_path, monkeypatch):
    monkeypatch.setattr(reserved, 'validate_release', lambda *args, **kwargs: None)
    plan = reserved.plan_for_date(ACCOUNT, STACK, day)
    for row in plan['actions']:
        clock.now = datetime.fromisoformat(row['planned_utc'])
        current = reserved.plan_for_date(ACCOUNT, STACK, day, clock.now)
        history.execute(current, tmp_path, reserved=True)
        count = len(provider.calls)
        assert history.execute(current, tmp_path, reserved=True)['status'] == 'no_due_actions'
        assert len(provider.calls) == count
    persona, changed = None, []
    for name, kwargs in provider.calls:
        if name == 'assume_role':
            persona = kwargs['RoleSessionName'].removeprefix('argus-')
        if name == 'get_object' and persona in reserved.TARGETS and kwargs['Bucket'].endswith('-p06'):
            changed.append(persona)
            assert kwargs['ExpectedBucketOwner'] == ACCOUNT and kwargs['Key'] == 'fixture.txt'
    assert sorted(changed) == [s['persona'] for s in plan['case_availability'] if s['status'] == 'available']
    with history.ledger(tmp_path / 'ledger.db') as db:
        assert db.execute('SELECT count(*) FROM actions').fetchone()[0] == len(plan['actions'])
        assert db.execute('SELECT sum(reserved_calls) FROM runs').fetchone()[0] <= history.MAX_DAY_CALLS
        assert dict(db.execute('SELECT status,count(*) FROM actions GROUP BY status')) == {'api_ok_audit_pending': len(plan['actions'])}


@pytest.mark.parametrize('day', list(reserved.CASES))
def test_pilot_routes_only_reserved_dates_to_guarded_wrapper(day, cfg, monkeypatch):
    from scripts import local_pilot as pilot
    calls = mocked(cfg, monkeypatch)
    result = pilot.tick(cfg, datetime.fromisoformat(day).replace(tzinfo=reserved.MALAYSIA))
    assert result['ok']
    assert [script for script, args in calls if '--execute' in args] == ['run_reserved_study.py']


def test_real_bundle_loader_rejects_synthetic_release(dataset, case_store, tmp_path):
    pytest.importorskip('torch')
    bundle = tmp_path / 'synthetic-bundle'
    trainer.train(dataset, bundle, NOW, synthetic=True)
    refs = json.loads((bundle / 'references.json').read_text())
    calibration = reserved.check_calibration(bundle, refs)
    release = tmp_path / 'release.json'
    frozen = {'schema': reserved.protocol.RELEASE_SCHEMA, 'study': reserved.protocol.binding(), 'study_sha256': reserved.protocol.binding_sha256(), 'case_availability': reserved.case_availability(ACCOUNT, STACK), 'frozen_at_utc': '2026-11-13T04:00:00+00:00',
              'scope_sha256': reserved.digest([ACCOUNT, STACK]), 'profile_sha256': reserved.PROFILE_SHA,
              'source_sha256': reserved.source_hashes(), 'cases': reserved.CASES, 'targets': list(reserved.TARGETS),
              'receipt_cutoff_my': reserved.CUTOFF.isoformat(), 'bundle': str(bundle),
              'bundle_sha256': {name: reserved.sha(bundle / name) for name in reserved.BUNDLE_FILES},
              'calibration': calibration}
    release.write_text(json.dumps(frozen))
    with pytest.raises(trainer.Refusal, match='Synthetic'):
        reserved.validate_release(release, ACCOUNT, STACK)
    report = evaluator.evaluate(release, *case_store, ACCOUNT, STACK, FINAL, allow_synthetic=True)
    assert report['run_kind'] == 'synthetic_contract_test' and report['activated'] is False
    assert report['summary']['unannounced_controlled_change']['planned_account_days'] == 2
    assert report['summary']['approved_legitimate_change']['planned_account_days'] == 2
    assert sum(r['status'] == 'scored' for r in report['rows']) == 11
    assert report['summary']['approved_legitimate_change']['unavailable_slots'] == 1
    captured = []
    original = trainer.score_rows
    from unittest.mock import patch
    def spy(model, scaler, references, rows):
        captured.extend(deepcopy(rows))
        return original(model, scaler, references, rows)
    with patch.object(trainer, 'score_rows', spy):
        evaluator.evaluate(release, *case_store, ACCOUNT, STACK, FINAL, allow_synthetic=True)
    assert captured and all('analyst_context' not in r and 'case_slot' not in r for r in captured)
    frozen['calibration']['components']['personal']['threshold'] += 1
    release.write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match='thresholds'):
        reserved.validate_release(release, ACCOUNT, STACK, allow_synthetic=True)
