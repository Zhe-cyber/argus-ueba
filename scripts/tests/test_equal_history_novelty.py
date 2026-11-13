"""Fixed-history novelty gate on synthetic resources only."""
from copy import deepcopy
import json

import pytest

from scripts import equal_history_novelty as model
from scripts.resource_observability import token


def row(user, day, paths=None):
    paths = [f'{user}-{day}'] if paths is None else paths
    return {'user': user, 'date': f'2020-01-{day:02d}', 'capture_boundary': False,
            'event_count': max(1, len(paths)), 'path_event_count': len(paths),
            'resources': sorted(token('path', p) for p in paths), 'actions': [token('action', 'read')],
            'coverage': dict.fromkeys(('invalid_resource_events', 'missing_required_paths', 'unknown_action_events'), 0)}


@pytest.fixture
def reference():
    return model.fit([row(u, d) for u in ('a', 'b', 'c') for d in range(1, 8)], '2020-01-01', '2020-01-07')


def test_exact_last_five_dates_and_full_fit_global_flag(reference):
    assert reference.selected_dates['a'] == tuple(f'2020-01-{d:02d}' for d in range(3, 8))
    old = model.score(reference, row('a', 8, ['a-1']))
    assert old['score'] == 1 and old['globally_unseen_fraction'] == 0
    assert model.score(reference, row('a', 8, ['a-7']))['score'] == 0


def test_globally_new_resources_are_scored_and_do_not_update_reference(reference):
    before = reference.document()
    sample = row('a', 8, ['never-seen'])
    assert model.score(reference, sample)['score'] == 1
    assert model.score(reference, sample)['globally_unseen_fraction'] == 1
    assert model.score(reference, sample)['score'] == 1
    assert reference.document() == before


def test_no_resource_activity_is_distinct_from_sparse_unknown_history(reference):
    assert model.score(reference, row('unknown', 8, []))['status'] == 'no_resource_activity'
    assert model.score(reference, row('unknown', 8))['status'] == 'unknown_account'
    sparse = model.fit([row('a', d) for d in range(1, 5)], '2020-01-01', '2020-01-07')
    assert model.score(sparse, row('a', 8))['status'] == 'insufficient_fitting_resource_dates'


def test_json_roundtrip_and_immutability(reference):
    document = reference.document()
    restored = model.load_reference(json.loads(json.dumps(document)))
    assert model.score(reference, row('a', 8)) == model.score(restored, row('a', 8))
    document['personal_resources']['a'].clear()
    assert restored.document() == reference.document()
    with pytest.raises(TypeError):
        restored.personal['a'] = frozenset()


def test_saturated_normal_calibration_rejects_candidate_without_threshold_changes(reference):
    calibration = model.calibrate(reference, [row(u, d) for u in ('a', 'b', 'c') for d in (8, 9)],
                                  '2020-01-08', '2020-01-09')
    assert calibration['threshold'] == 1
    assert calibration['normal_calibration_alerts'] == 0
    assert calibration['exact_threshold_ties'] == 6
    assert calibration['gate'] == 'saturated_no_go'
    assert calibration['switch_evaluation_status'] == 'not_run'


def test_unsaturated_gate_is_not_validation_or_activation(reference):
    calibration = model.calibrate(reference, [row(u, d, [f'{u}-7']) for u in ('a', 'b', 'c') for d in (8, 9)],
                                  '2020-01-08', '2020-01-09')
    assert calibration['threshold'] == 0
    assert calibration['gate'] == 'development_comparison_pending'


def test_coverage_and_wrong_dates_are_rejected(reference):
    sample = row('a', 8)
    sample['coverage']['missing_required_paths'] = 1
    assert model.score(reference, sample)['score'] is None
    with pytest.raises(ValueError, match='follow fitting'):
        model.score(reference, row('a', 7))
    rows = [row('a', d) for d in range(1, 7)]
    with pytest.raises(ValueError):
        model.fit(rows, '2020-01-01', '2020-01-05')
    with pytest.raises(ValueError):
        model.fit(rows + [deepcopy(rows[0])], '2020-01-01', '2020-01-07')
    with pytest.raises(ValueError):
        model.calibrate(reference, [row('a', 8)], '2020-01-08', '2020-01-09')


@pytest.mark.parametrize('field,value', [('reference_dates', 4), ('activated', True)])
def test_reload_rejects_changed_method(reference, field, value):
    doc = reference.document()
    doc[field] = value
    with pytest.raises(ValueError):
        model.load_reference(doc)


def test_wrong_original_report_stops_before_native_io(tmp_path, monkeypatch):
    from scripts import check_equal_history_calibration as gate
    monkeypatch.setattr(gate, 'ROOT', tmp_path)
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    (inputs / 'development_report.json').write_text('{}')
    monkeypatch.setattr(gate, 'Prefix', lambda *args: pytest.fail('Native I/O before pinned report verification'))
    with pytest.raises(ValueError, match='frozen W6 report'):
        gate.run(inputs, 'prefix', 'manifest', tmp_path / 'data/processed/new')
    assert not (tmp_path / 'data/processed/new').exists()
