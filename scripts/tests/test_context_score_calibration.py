"""Fixed scores/gates; synthetic profiles are not evidence of attack performance."""
from copy import deepcopy
import hashlib
import json

import pytest

from scripts import context_feature_diagnostic as context
from scripts import context_score_calibration as scoring
from scripts.resource_observability import token


def row(user, day, category=None, paths=1):
    category = token('synthetic', user) if category is None else category
    return {'user': user, 'date': f'2020-01-{day:02d}', 'event_count': max(1, paths), 'distinct_paths': paths,
            'coverage': dict.fromkeys(('invalid_resource_events', 'missing_required_paths', 'unknown_action_events'), 0),
            'views': {'action_mix': {category: max(1, paths)}, 'parent_depth1': {category: paths} if paths else {},
                      'parent_depth2': {category: paths} if paths else {}}}


@pytest.fixture
def reference():
    fitted = context.fit([row(u, d) for u in ('a', 'b', 'c', 'd') for d in range(1, 6)],
                         '2020-01-01', '2020-01-05')
    return scoring.load_reference(json.loads(json.dumps(fitted.document())))


def test_loaded_reference_is_immutable_and_roundtrip_exact(reference):
    restored = scoring.load_reference(reference.document())
    assert restored.document() == reference.document()
    with pytest.raises(TypeError):
        restored.centres['action_mix']['a']['x'] = 1
    before = restored.document()
    scoring.score(restored, row('a', 6, token('new')))
    assert restored.document() == before


def test_primary_is_max_action_parent1_and_never_uses_depth2(reference):
    sample = row('a', 6)
    sample['views']['parent_depth2'] = {token('new'): 1}
    result = scoring.score(reference, sample)
    assert result['scores']['parent_depth2'] == 1
    assert result['scores']['joint_primary'] == 0
    sample['views']['parent_depth1'] = {token('new'): 1}
    assert scoring.score(reference, sample)['scores']['joint_primary'] == 1


def test_primary_requires_resource_view_and_keeps_action_control(reference):
    result = scoring.score(reference, row('a', 6, paths=0))
    assert result['scores']['action_mix'] == 0
    assert result['scores']['joint_primary'] is None
    assert result['statuses']['parent_depth1'] == 'no_resource_activity'


def test_unseen_categories_are_included_and_reported(reference):
    result = scoring.score(reference, row('a', 6, token('brand-new')))
    assert all(v == 1 for v in result['scores'].values())
    assert all(v == 1 for v in result['globally_unseen_category_mass'].values())


def test_unknown_and_unresolved_are_not_normal_scores(reference):
    assert scoring.score(reference, row('unknown', 6))['scores']['joint_primary'] is None
    sample = row('a', 6)
    sample['coverage']['invalid_resource_events'] = 1
    assert all(v is None for v in scoring.score(reference, sample)['scores'].values())
    with pytest.raises(ValueError, match='follow fitting'):
        scoring.score(reference, row('a', 5))


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(activated=True),
    lambda d: d.update(day_weighting='event_weighted'),
    lambda d: d['centres']['action_mix']['a'].update({token('synthetic', 'a'): .5}),
    lambda d: d['usable_fitting_dates']['parent_depth1'].update(a=4),
    lambda d: d['full_fitting_vocabulary']['parent_depth2'].clear(),
])
def test_reload_rejects_changed_contract_probabilities_or_eligibility(reference, mutation):
    doc = reference.document()
    mutation(doc)
    with pytest.raises(ValueError):
        scoring.load_reference(doc)


def test_primary_gate_not_replaced_by_passing_control(reference):
    rows = [row(u, d) for u in ('a', 'b', 'c') for d in (6, 7)]
    for r in rows:
        r['views']['parent_depth1'] = {token('new'): 1}
    report, scored = scoring.calibrate(reference, rows, '2020-01-06', '2020-01-07')
    assert report['joint_primary']['gate'] == 'near_ceiling_no_go'
    assert report['action_mix']['gate'] == 'ready_for_development_comparison'
    assert report['joint_primary']['normal_calibration_alerts'] == 0
    assert report['joint_primary']['exact_threshold_ties'] == 6
    assert len(scored) == 6


def test_near_ceiling_is_gate_only_not_threshold_lowering(reference, monkeypatch):
    rows = [row(u, d) for u in ('a', 'b', 'c') for d in (6, 7)]
    original = scoring.score
    def almost_one(ref, r):
        result = original(ref, r)
        result['scores'] = {m: 1 - 5e-13 for m in scoring.MODES}
        return result
    monkeypatch.setattr(scoring, 'score', almost_one)
    report, _ = scoring.calibrate(reference, rows, '2020-01-06', '2020-01-07')
    assert report['joint_primary']['gate'] == 'near_ceiling_no_go'
    assert report['joint_primary']['threshold'] == 1 - 5e-13
    assert report['joint_primary']['normal_calibration_alerts'] == 0


def test_calibration_minima_duplicate_and_overlap_checks(reference):
    report, _ = scoring.calibrate(reference, [row('a', 6)], '2020-01-06', '2020-01-06')
    assert report['joint_primary']['threshold'] is None
    assert report['joint_primary']['gate'] == 'insufficient_normal_calibration'
    with pytest.raises(ValueError):
        scoring.calibrate(reference, [row('a', 6), row('a', 6)], '2020-01-06', '2020-01-06')
    with pytest.raises(ValueError, match='overlaps'):
        scoring.calibrate(reference, [row('a', 5)], '2020-01-05', '2020-01-05')


def test_period_projector_matches_frozen_w8_views():
    from scripts.project_context_period import project
    from scripts.run_context_feature_diagnostic import project as frozen
    def event(day, path):
        return {'uid': 'a', 'uidType': 'name', 'time': day + 'T12:00:00Z', 'type': 'file_accessed', 'params': {'path': path}}
    events = [event('2017-07-01', '/before'), event('2017-07-13', '/team/a'), event('2017-07-13', '/team/a'),
              event('2017-07-14', '/team/b'), event('2017-08-10', '/after')]
    users = {hashlib.sha256(b'clue-7119953:a').hexdigest()}
    original = [{k: v for k, v in r.items() if k != 'exact_uid_parent_match_paths'} for r in frozen(events, users)]
    assert project(events, users, '2017-07-13', '2017-07-31') == original


def test_bad_report_binding_stops_before_native_read(tmp_path, monkeypatch):
    from scripts import calibrate_context_score as gate
    monkeypatch.setattr(gate, 'ROOT', tmp_path)
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    (inputs / 'diagnostic_report.json').write_text('{}')
    monkeypatch.setattr(gate, 'Prefix', lambda *a: pytest.fail('Read native data before binding check'))
    with pytest.raises(ValueError, match='frozen W8 report'):
        gate.run(inputs, 'dataset', 'manifest', 'prefix', tmp_path / 'data/processed/new')
