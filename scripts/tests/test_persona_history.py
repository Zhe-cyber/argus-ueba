"""Guarded incremental histories: fake providers and isolated ledgers only."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
import sqlite3
from types import SimpleNamespace

import pytest

from scripts import run_persona_history as history
from scripts.simulation_lab import FIXTURE, buckets

ACCOUNT, STACK = '123456789012', 'argus-ueba-actors'


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(now=datetime(2026, 10, 29, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(history, 'utc_now', lambda: clock.now)
    return clock


@pytest.fixture
def provider(monkeypatch):
    import boto3
    state = SimpleNamespace(calls=[], root=False, logging=True, covered=True, fail=False, retry=False)

    class Client:
        def __init__(self, service):
            self.service = service
            self.handler = None
            self.meta = SimpleNamespace(events=SimpleNamespace(register=self.register))

        def register(self, event, handler):
            assert event == 'before-send.*.*'
            self.handler = handler

        def close(self):
            pass

        def __getattr__(self, name):
            def call(**kwargs):
                self.handler()
                state.calls.append((name, kwargs))
                if name == 'get_caller_identity':
                    return {'Account': ACCOUNT, 'Arn': f'arn:aws:iam::{ACCOUNT}:root' if state.root else f'arn:aws:iam::{ACCOUNT}:user/argus-lab/{STACK}-runner'}
                if name == 'get_trail_status':
                    return {'IsLogging': state.logging}
                if name == 'get_event_selectors':
                    return {'EventSelectors': [{'ReadWriteType': 'ReadOnly', 'DataResources': [{'Type': 'AWS::S3::Object',
                        'Values': [f'arn:aws:s3:::{b}/' for b in buckets(ACCOUNT, STACK)] if state.covered else []}]}]}
                if name == 'assume_role':
                    persona = kwargs['RoleSessionName'].removeprefix('argus-')
                    return {'AssumedRoleUser': {'Arn': f'arn:aws:sts::{ACCOUNT}:assumed-role/{STACK}-{persona}/argus-{persona}',
                                                'AssumedRoleId': f'FAKE-{persona}'},
                            'Credentials': {'AccessKeyId': 'DUMMY', 'SecretAccessKey': 'DUMMYSECRET', 'SessionToken': 'DUMMYTOKEN'}}
                if state.fail:
                    raise RuntimeError('DUMMYSECRET')
                if state.retry:
                    for _ in range(100):
                        self.handler()  # Simulate SDK sends hidden from the outer method call.
                response = {'ResponseMetadata': {'RequestId': f'request-{len(state.calls)}'}}
                if name != 'get_bucket_location':
                    response.update(Metadata={'argus-lab': STACK}, ContentLength=len(FIXTURE))
                if name == 'get_object':
                    response['Body'] = io.BytesIO(FIXTURE)
                return response
            return call

    monkeypatch.setattr(boto3, 'Session', lambda **kw: SimpleNamespace(client=lambda name, **kwargs: Client(name)))
    return state


def due_plan(clock):
    plan = history.plan_today(ACCOUNT, STACK)
    clock.now = datetime.fromisoformat(plan['actions'][0]['planned_utc'])
    return history.plan_today(ACCOUNT, STACK)


def test_offline_default_has_no_clients_or_ledger(clock, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(history, 'execute', lambda *a: pytest.fail('Offline command executed'))
    monkeypatch.setattr('sys.argv', ['history', '--account-id', ACCOUNT, '--state-dir', str(tmp_path)])
    assert history.main() == 0
    assert json.loads(capsys.readouterr().out)['executed'] is False
    assert not list(tmp_path.iterdir())


def test_same_plan_is_reproducible_and_changed_targets_fail_before_io(clock, provider, tmp_path):
    plan = due_plan(clock)
    assert plan == history.plan_today(ACCOUNT, STACK)
    plan['actions'][0]['bucket'] = 'production-bucket'
    with pytest.raises(ValueError, match='Plan changed'):
        history.execute(plan, tmp_path)
    assert not provider.calls and not list(tmp_path.iterdir())


def test_only_due_actions_run_and_repeat_is_noop(clock, provider, tmp_path):
    plan = due_plan(clock)
    first = history.execute(plan, tmp_path)
    before = deepcopy(provider.calls)
    assert first['new_actions'] > 0 and first['coverage'] == 'provider_receipt_audit_pending'
    assert history.execute(plan, tmp_path)['status'] == 'no_due_actions'
    assert provider.calls == before
    assert all(kw['ExpectedBucketOwner'] == ACCOUNT for method, kw in before if method in ('get_object', 'head_object', 'get_bucket_location'))
    with sqlite3.connect(tmp_path / 'ledger.db') as db:
        assert 'DUMMYSECRET' not in str(db.execute('SELECT * FROM actions').fetchall())
        assert db.execute('SELECT sum(reserved_calls) FROM runs').fetchone()[0] <= 48


def test_missed_actions_are_not_backfilled(clock, provider, tmp_path):
    clock.now = datetime(2026, 10, 29, 15, tzinfo=timezone.utc)  # 23:00 Malaysia.
    result = history.execute(history.plan_today(ACCOUNT, STACK), tmp_path)
    assert result['status'] == 'no_due_actions'
    assert result['action_states']['missed'] > 0
    assert provider.calls == []


def test_commissioning_is_fixed_one_read_excluded_and_claimed_once(clock, provider, tmp_path):
    plan = history.commissioning_plan(ACCOUNT, STACK)
    with pytest.raises(ValueError, match='Plan changed'):
        history.execute(plan, tmp_path)
    assert provider.calls == []
    result = history.execute(plan, tmp_path, commissioning=True)
    assert result['new_actions'] == 1
    assert result['purpose'] == 'commissioning_exclude_from_baseline'
    assert len(provider.calls) == 5
    assert provider.calls[-1][0] == 'get_object'
    assert provider.calls[-1][1]['Bucket'] == buckets(ACCOUNT, STACK)[0]
    clock.now += timedelta(days=1)
    assert history.execute(history.commissioning_plan(ACCOUNT, STACK), tmp_path, commissioning=True)['status'] == 'no_due_actions'
    assert len(provider.calls) == 5


def test_commissioning_tamper_and_stale_request_fail_before_cloud(clock, provider, tmp_path):
    plan = history.commissioning_plan(ACCOUNT, STACK)
    plan['actions'][0]['bucket'] = 'production'
    with pytest.raises(ValueError, match='Plan changed'):
        history.execute(plan, tmp_path, commissioning=True)
    plan = history.commissioning_plan(ACCOUNT, STACK)
    clock.now += timedelta(minutes=16)
    with pytest.raises(ValueError, match='stale'):
        history.execute(plan, tmp_path, commissioning=True)
    assert provider.calls == []


@pytest.mark.parametrize('fault', ['root', 'logging', 'covered', 'fail', 'retry'])
def test_uncertain_failure_is_durable_and_never_retried(clock, provider, tmp_path, fault):
    setattr(provider, fault, fault not in ('logging', 'covered'))
    plan = due_plan(clock)
    with pytest.raises((RuntimeError, ValueError)):
        history.execute(plan, tmp_path)
    before = deepcopy(provider.calls)
    assert history.execute(plan, tmp_path)['status'] == 'no_due_actions'
    assert provider.calls == before
    if fault in ('root', 'logging', 'covered'):
        assert not any(method in ('assume_role', 'get_object', 'head_object') for method, _ in before)


def test_budget_rollback_and_scope_pinning(clock, tmp_path):
    plan = due_plan(clock)
    with history.ledger(tmp_path / 'ledger.db') as db:
        db.execute('INSERT INTO runs VALUES(?,?,?)', ('earlier', plan['date_local'], history.MAX_DAY_CALLS))
        db.commit()
        with pytest.raises(ValueError, match='budget'):
            history.claim(db, plan)
        assert db.execute('SELECT count(*) FROM actions').fetchone()[0] == 0
        db.execute('DELETE FROM runs')
        db.commit()
        history.claim(db, plan)
        plan['profile_sha256'] = 'changed'
        with pytest.raises(ValueError, match='scope/profile'):
            history.claim(db, plan)


def test_concurrent_invocations_claim_each_due_action_once(clock, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    plan = due_plan(clock)
    path = tmp_path / 'ledger.db'
    with history.ledger(path):
        pass

    def worker():
        with history.ledger(path) as db:
            return history.claim(db, plan)[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    identifiers = [row['action_id'] for group in results for row in group]
    assert identifiers and len(identifiers) == len(set(identifiers))


def test_old_day_is_rejected_without_ledger_claims(clock, tmp_path):
    plan = due_plan(clock)
    clock.now += timedelta(days=1)
    with history.ledger(tmp_path / 'ledger.db') as db:
        with pytest.raises(ValueError, match='another local date'):
            history.claim(db, plan)
        assert db.execute('SELECT count(*) FROM actions').fetchone()[0] == 0


def test_pilot_plans_fit_reservations_even_when_every_action_is_separate():
    from datetime import date
    from scripts.persona_history_plan import make_plan
    profiles = json.loads(history.PROFILE.read_text())
    counts = [len(make_plan(profiles, date(2026, 10, 28) + timedelta(days=i))['actions']) for i in range(28)]
    # Each separate invocation: identity + two audit reads + assume + S3.
    # Include the one-time five-call commissioning probe conservatively.
    assert max(counts) * 5 + 5 <= history.MAX_DAY_CALLS
    assert sum(counts) * 5 + 5 <= history.MAX_PILOT_CALLS


def test_audit_requires_native_identity_request_action_resource_and_no_error(clock, provider, tmp_path):
    history.execute(due_plan(clock), tmp_path)
    events = tmp_path / 'native.db'
    with sqlite3.connect(events) as native:
        native.execute('CREATE TABLE events(source,source_account_id,event_id,timestamp,action,resource,metadata)')
    assert history.audit(tmp_path, events)['newly_provider_verified'] == 0
    with sqlite3.connect(tmp_path / 'ledger.db') as db:
        rows = db.execute('SELECT plan,request_id,principal_id FROM actions').fetchall()
    with sqlite3.connect(events) as native:
        for i, (raw, request, principal) in enumerate(rows):
            row = json.loads(raw)
            meta = {'requestID': request, 'userIdentity': {'principalId': 'wrong'}}
            native.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',
                           ('aws_cloudtrail', ACCOUNT, f'event-{i}', '2026-10-29T01:00:00Z', row['operation'], row['bucket'], json.dumps(meta)))
    assert history.audit(tmp_path, events)['newly_provider_verified'] == 0
    with sqlite3.connect(events) as native:
        for i, (_, request, principal) in enumerate(rows):
            native.execute('UPDATE events SET metadata=? WHERE event_id=?',
                           (json.dumps({'requestID': request, 'userIdentity': {'principalId': principal}}), f'event-{i}'))
    assert history.audit(tmp_path, events)['newly_provider_verified'] == len(rows)
    assert history.audit(tmp_path, events)['newly_provider_verified'] == 0
