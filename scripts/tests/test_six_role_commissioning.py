"""All AWS I/O stubbed; actual commissioning is separately receipt-audited."""
from copy import deepcopy
from datetime import timedelta
import json

import pytest

from scripts import commission_six_roles as probe, run_persona_history as history
from scripts.tests.test_persona_history import clock, provider, ACCOUNT, STACK


def test_exact_plan_is_bounded_one_time_and_excluded(clock):
    plan = probe.make_plan(ACCOUNT, STACK)
    assert len(plan['actions']) == 18
    assert len({r['action_id'] for r in plan['actions']}) == 18
    assert all(r['purpose'] == probe.PURPOSE for r in plan['actions'])
    for role in probe.PERSONAS:
        assert {r['operation'] for r in plan['actions'] if r['persona'] == role} == set(probe.METHODS)
    clock.now += timedelta(days=1)
    with pytest.raises(ValueError): probe.make_plan(ACCOUNT, STACK)


def test_all_roles_operations_budget_receipts_and_no_retry(clock, provider, tmp_path):
    plan = probe.make_plan(ACCOUNT, STACK)
    result = probe.execute(plan, tmp_path)
    assert result['new_actions'] == 18 and result['sdk_calls_used'] == 27 and result['http_sends'] == 27
    assert len(provider.calls) == 27
    assert all(kwargs['ExpectedBucketOwner'] == ACCOUNT for op, kwargs in provider.calls if op in probe.METHODS.values())
    with history.ledger(tmp_path / 'ledger.db') as db:
        assert db.execute('SELECT sum(reserved_calls) FROM runs').fetchone()[0] == 27
        assert db.execute("SELECT count(*) FROM actions WHERE status='api_ok_audit_pending'").fetchone()[0] == 18
        assert all(json.loads(r[0])['purpose'] == probe.PURPOSE for r in db.execute('SELECT plan FROM actions'))
    before = deepcopy(provider.calls)
    assert probe.execute(plan, tmp_path)['new_actions'] == 0
    assert provider.calls == before


@pytest.mark.parametrize('fault', ['root', 'logging', 'covered', 'fail', 'retry'])
def test_uncertain_failure_retained_and_never_retried(clock, provider, tmp_path, fault):
    setattr(provider, fault, fault not in ('logging', 'covered'))
    plan = probe.make_plan(ACCOUNT, STACK)
    with pytest.raises((ValueError, RuntimeError)):
        probe.execute(plan, tmp_path)
    before = deepcopy(provider.calls)
    assert probe.execute(plan, tmp_path)['new_actions'] == 0
    assert provider.calls == before
    with history.ledger(tmp_path / 'ledger.db') as db:
        assert db.execute("SELECT count(*) FROM actions WHERE status='claimed_unknown'").fetchone()[0] > 0


def test_tampered_scope_target_never_sent(clock, provider, tmp_path):
    plan = probe.make_plan(ACCOUNT, STACK)
    plan['actions'][0]['bucket'] = 'not-the-toy-fixture'
    with pytest.raises(ValueError): probe.execute(plan, tmp_path)
    assert not provider.calls
