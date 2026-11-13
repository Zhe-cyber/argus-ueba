"""V3 amendment regressions; synthetic plans and bundles, no provider traffic."""
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from scripts import aws_study_v3 as policy, reserved_study as study
from scripts import live_history_readiness as readiness, run_persona_history as runner
from scripts import train_live_daily as trainer

ACCOUNT, STACK = '123456789012', 'argus-ueba-actors'


def test_calendar_has_no_overlap_or_early_evaluation():
    assert readiness.WINDOWS == policy.WINDOWS
    assert policy.WINDOWS == {'fit': ('2026-11-01', '2026-11-07'),
                              'validation': ('2026-11-08', '2026-11-09'),
                              'normal_calibration': ('2026-11-10', '2026-11-12')}
    assert study.CUTOFF == datetime(2026, 11, 15, 20, tzinfo=policy.MALAYSIA)
    assert study.EVALUATE_FROM == datetime(2026, 11, 16, tzinfo=policy.MALAYSIA)
    assert policy.SERVICE_EXPIRES == datetime(2026, 11, 17, tzinfo=policy.MALAYSIA)


@pytest.mark.parametrize('day', range(1, 8))
def test_fitting_actions_equal_unchanged_generator_and_readiness(day, monkeypatch):
    stamp = datetime(2026, 11, day, tzinfo=policy.MALAYSIA)
    monkeypatch.setattr(runner, 'utc_now', lambda: stamp)
    ordinary = runner.plan_today(ACCOUNT, STACK)
    assert ordinary['date_local'] not in study.CASES
    expected = readiness.expected_actions(ACCOUNT, STACK)
    for action in ordinary['actions']:
        match = expected[action['action_id']]
        assert match['partition'] == 'fit'
        assert match['day'] == ordinary['date_local']
        assert {k: v for k, v in match.items() if k not in ('day', 'partition')} == action
    assert (runner.MAX_RUN_CALLS, runner.MAX_DAY_CALLS, runner.MAX_PILOT_CALLS) == (48, 128, 1792)


def test_bound_sources_exclude_independent_claude_diagnostics():
    assert 'scripts/aws_study_v3.py' in study.SOURCE_FILES
    assert 'docs/LIVE_EVALUATION_PROTOCOL_V3.md' in study.SOURCE_FILES
    assert 'specs/W34-aws-study-v3.md' in study.SOURCE_FILES
    assert not set(study.SOURCE_FILES) & {
        'scripts/live_coverage_policy.py', 'scripts/live_receipts_clue_v2.py',
        'scripts/audit_clue_v2_live.py', 'scripts/explain_clue_v2.py'}
    assert not any('clue' in name.lower() or '/tests/' in name for name in study.SOURCE_FILES)


@pytest.mark.parametrize('mutation', ['absent', 'hash', 'windows'])
def test_old_or_changed_artifact_policy_is_rejected(mutation):
    value = {'study': policy.binding(), 'study_sha256': policy.binding_sha256()}
    policy.require_binding(value)
    value = deepcopy(value)
    if mutation == 'absent':
        value.pop('study')
    elif mutation == 'hash':
        value['study_sha256'] = '0' * 64
    else:
        value['study']['windows']['fit'][0] = '2026-10-30'
    with pytest.raises(ValueError, match='V3'):
        policy.require_binding(value)


@pytest.mark.parametrize('when', [study.CUTOFF, study.EVALUATE_FROM - timedelta(microseconds=1)])
def test_receipt_cutoff_does_not_unlock_evaluation(when, tmp_path):
    from scripts.evaluate_reserved_study import evaluate
    with pytest.raises(ValueError, match='16 November'):
        evaluate(tmp_path / 'absent', tmp_path / 'ledger', tmp_path / 'events', ACCOUNT, STACK, when)


@pytest.mark.parametrize('offset,allowed', [(-1, True), (0, False), (1, False)])
def test_source_commit_cutoff_is_strict(offset, allowed, monkeypatch, tmp_path):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 13, 12, tzinfo=policy.MALAYSIA)
    monkeypatch.setattr(study, 'datetime', Clock)
    manifest = {'history_gates': {'history_gates_pass': True, 'eligible_roles': 6},
                'partition_rows': {'fit': 42, 'validation': 12, 'normal_calibration': 18}}
    monkeypatch.setattr(trainer, 'load_bundle', lambda *a, **k: (None, None, {}, manifest))
    monkeypatch.setattr(study, 'check_calibration', lambda *a: {})
    def git(args, **kwargs):
        if 'status' in args:
            return SimpleNamespace(stdout='')
        if 'rev-parse' in args:
            return SimpleNamespace(stdout='a' * 40)
        return SimpleNamespace(stdout=str(int(policy.SOURCE_COMMIT_BEFORE.timestamp()) + offset))
    monkeypatch.setattr(study.subprocess, 'run', git)
    monkeypatch.setattr(study, 'sha', lambda *a: 'b' * 64)
    monkeypatch.setattr(study, 'validate_release', lambda *a: None)
    output = tmp_path / 'release.json'
    if allowed:
        assert study.freeze(tmp_path, output, ACCOUNT, STACK)['frozen']
    else:
        with pytest.raises(ValueError, match='before calibration'):
            study.freeze(tmp_path, output, ACCOUNT, STACK)
        assert not output.exists()
