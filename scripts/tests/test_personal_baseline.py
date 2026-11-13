"""Statistical reference and native projection isolation. Synthetic fixtures only."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import math

import pytest

from scripts import personal_baseline as personal
from scripts import evaluate_personal_baseline as comparison
from scripts.clue_native_projection import project_rows
from scripts.clue_features import FEATURES


def row(user, day, count=1):
    values = dict.fromkeys(FEATURES, 0)
    values.update(event_count=count, unique_actions=1)
    return {'user': user, 'date': day, 'features': values, 'capture_boundary': False,
            'coverage': {'missing_required_paths': 0, 'unknown_action_events': 0}}


@pytest.fixture
def fitting():
    return [row(user, f'2020-01-{day:02d}', count) for day in range(1, 6) for user, count in (('a', 1), ('b', 1000))]


@pytest.fixture
def reference(fitting):
    return personal.fit_reference(fitting, '2020-01-01', '2020-01-05')


def test_account_identity_changes_only_personal_reference(reference):
    a, b = row('a', '2020-01-07', 1000), row('b', '2020-01-07', 1000)
    assert personal.score(reference, a)['score'] > personal.score(reference, b)['score']
    assert personal.score(reference, b)['score'] == 0
    assert personal.score(reference, a, False)['score'] == personal.score(reference, b, False)['score']
    assert all(x['shared_scale_log1p'] == y['shared_scale_log1p'] for x, y in
               zip(personal.score(reference, a)['components'], personal.score(reference, a, False)['components']))


def test_components_sum_and_serialised_inference_is_identical(reference):
    original = personal.score(reference, row('a', '2020-01-07', 33))
    assert math.fsum(c['contribution'] for c in original['components']) == original['score']
    loaded = personal.load_reference(json.loads(json.dumps(reference.document())))
    assert personal.score(loaded, row('a', '2020-01-07', 33)) == original
    assert all(s >= personal.SCALE_FLOOR and math.isfinite(s) for s in reference.scales)
    with pytest.raises(TypeError):
        reference.centres['a'] = (0,) * len(FEATURES)


def test_inputs_and_frozen_references_do_not_adapt_to_later_rows(fitting):
    before = deepcopy(fitting)
    model = personal.fit_reference(fitting, '2020-01-01', '2020-01-05')
    saved = model.document()
    for value in (0.1, 1, 10000):
        personal.score(model, row('a', '2020-01-08', value))
    assert fitting == before and model.document() == saved
    fitting[0]['features']['event_count'] = 9999
    assert model.document() == saved


@pytest.mark.parametrize('fault', ['negative', 'nan', 'infinity', 'bool', 'missing', 'extra', 'idle', 'partial', 'coverage'])
def test_invalid_feature_rows_are_rejected(reference, fault):
    sample = row('a', '2020-01-07')
    if fault == 'negative': sample['features']['event_count'] = -1
    elif fault == 'nan': sample['features']['event_count'] = float('nan')
    elif fault == 'infinity': sample['features']['event_count'] = float('inf')
    elif fault == 'bool': sample['features']['event_count'] = True
    elif fault == 'missing': del sample['features']['new_action_count']
    elif fault == 'extra': sample['features']['case_label'] = 1
    elif fault == 'idle': sample['features']['event_count'] = 0
    elif fault == 'partial': sample['capture_boundary'] = True
    else: sample['coverage']['unknown_action_events'] = 1
    with pytest.raises(ValueError): personal.score(reference, sample)


def test_sparse_and_unknown_accounts_are_unavailable_not_zero(fitting):
    fitting.append(row('sparse', '2020-01-03', 2))
    model = personal.fit_reference(fitting, '2020-01-01', '2020-01-05')
    assert personal.score(model, row('sparse', '2020-01-07'))['status'] == 'insufficient_fitting_history'
    result = personal.score(model, row('unknown', '2020-01-07'))
    assert result == {'status': 'unknown_account', 'score': None, 'components': []}
    assert personal.score(model, row('unknown', '2020-01-07'), False)['status'] == 'ready'


def test_duplicate_future_and_overlapping_windows_are_rejected(fitting, reference):
    with pytest.raises(ValueError): personal.fit_reference(fitting + [fitting[0]], '2020-01-01', '2020-01-05')
    with pytest.raises(ValueError): personal.fit_reference(fitting, '2020-01-01', '2020-01-04')
    with pytest.raises(ValueError): personal.score(reference, row('a', '2020-01-05'))
    with pytest.raises(ValueError): personal.calibrate(reference, fitting, '2020-01-01', '2020-01-05')


def test_normal_only_calibration_is_separate_and_strict(reference):
    samples = [row('a', f'2020-01-{day:02d}', day) for day in range(6, 12)]
    samples += [row('unknown', '2020-01-07', 20)]
    saved = reference.document()
    calibration = personal.calibrate(reference, samples, '2020-01-06', '2020-01-11')
    assert calibration['scored_rows'] == 6 and calibration['unavailable_rows'] == 1
    assert calibration['reference_sha256'] == personal.document_digest(saved)
    assert reference.document() == saved
    assert personal.quantile_linear(list(range(169))) == pytest.approx(166.32)
    assert personal.alert(calibration['threshold'], calibration['threshold']) is False
    assert personal.alert(calibration['threshold'] + 1e-8, calibration['threshold']) is True
    with pytest.raises(ValueError): personal.calibrate(reference, samples[:5], '2020-01-06', '2020-01-11')
    with pytest.raises(ValueError): personal.calibrate(reference, samples, '2020-01-06', '2020-01-10')


@pytest.mark.parametrize('field,value', [('input_profile', 'cloud'), ('shared_scales', [0] * 10),
                                        ('personal_centres', {}), ('activated', True), ('fit_rows_sha256', 'bad')])
def test_persisted_reference_contract_is_checked(reference, field, value):
    document = reference.document()
    document[field] = value
    with pytest.raises(ValueError): personal.load_reference(document)


@pytest.mark.parametrize('a,b,expected', [(True, True, True), (True, None, True), (None, True, True),
                                        (False, False, False), (False, None, None), (None, False, None), (None, None, None)])
def test_fusion_does_not_convert_missing_to_normal(a, b, expected):
    assert personal.either(a, b) is expected


def uid(value):
    return hashlib.sha256(('clue-7119953:' + value).encode()).hexdigest()


def events():
    return [{'id': 2 * day + i, 'uid': user, 'uidType': 'name', 'time': f'2020-01-{day:02d}T12:00:00Z',
             'type': 'file_created' if user == 'a' else 'file_accessed', 'params': {'path': '/fixture/' + user}}
            for day in range(1, 5) for i, user in enumerate(('a', 'b'))]


def test_native_switch_rebuilds_novelty_and_preserves_source_and_earlier_days():
    native = events()
    saved = deepcopy(native)
    normal = {(r['user'], r['date']): r for r in project_rows(native)}
    changed = {(r['user'], r['date']): r for r in project_rows(native, {uid('a'): uid('b'), uid('b'): uid('a')}, '2020-01-03')}
    assert native == saved
    assert all(row == changed[key] for key, row in normal.items() if key[1] < '2020-01-03')
    assert normal[uid('b'), '2020-01-03']['features']['new_action_count'] == 0
    assert changed[uid('a'), '2020-01-03']['features']['new_action_count'] == 1
    assert changed[uid('a'), '2020-01-04']['features']['new_action_count'] == 0
    assert len(normal) == len(changed) == 8
    with pytest.raises(ValueError): project_rows(native, {uid('a'): uid('b')}, '2020-01-03')


def test_native_anonymous_dates_still_define_capture_boundaries():
    native = events()
    native += [{'uid': '0.0.0.0', 'uidType': 'ipaddress', 'time': '2020-01-05T01:00:00Z'}]
    projected = project_rows(native)
    assert not any(r['date'] == '2020-01-05' for r in projected)
    assert not next(r for r in projected if r['date'] == '2020-01-04')['capture_boundary']


def test_resource_only_change_can_be_invisible_to_the_frozen_ten_counts():
    """Observability counterexample: a new resource is not a new path COUNT."""
    native = [{'uid': 'a', 'uidType': 'name', 'time': f'2020-01-{day:02d}T12:00:00Z',
               'type': 'file_accessed', 'params': {'path': '/ordinary-file'}} for day in range(1, 8)]
    native.append({'uid': 'ip', 'uidType': 'ipaddress', 'time': '2020-01-08T12:00:00Z'})
    changed = deepcopy(native)
    changed[6]['params']['path'] = '/different-file'
    normal_rows, changed_rows = project_rows(native), project_rows(changed)
    fit = [r for r in normal_rows if '2020-01-02' <= r['date'] <= '2020-01-06']
    model = personal.fit_reference(fit, '2020-01-02', '2020-01-06')
    ordinary = next(r for r in normal_rows if r['date'] == '2020-01-07')
    altered = next(r for r in changed_rows if r['date'] == '2020-01-07')
    assert ordinary['features'] == altered['features']
    assert personal.score(model, ordinary)['score'] == personal.score(model, altered)['score']


def test_report_fusion_uses_common_coverage_and_rejects_repeated_controls():
    sample = {'account': 'cohort-1', 'date': '2020-01-01',
              'alerts': {'population': False, 'personal': None, 'ae': True, 'ae_or_personal': True}}
    report = comparison.summaries([sample])
    assert report['common_scorable_rows'] == 0
    assert report['methods']['personal']['unavailable_rows'] == 1
    assert report['methods']['ae_or_personal']['alerts'] == 1
    with pytest.raises(ValueError): comparison.summaries([sample, deepcopy(sample)])


def test_bad_pinned_manifest_stops_before_artifact_loading(tmp_path, monkeypatch):
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    (bundle / 'clue_model_manifest.json').write_text('{}')
    monkeypatch.setattr(comparison, 'ROOT', tmp_path)
    monkeypatch.setattr(comparison, 'candidate', lambda *a: pytest.fail('Deserialised before verifying inputs'))
    with pytest.raises(ValueError, match='pinned'):
        comparison.run(tmp_path / 'data.json', bundle, tmp_path / 'prefix.zip', tmp_path / 'plan.json', tmp_path / 'data/processed/results')
    assert not (tmp_path / 'data/processed/results').exists()


@pytest.mark.parametrize('alter_earlier_partition', [False, True])
def test_case_assembly_preserves_controls_counts_missing_days_and_rejects_contamination(tmp_path, monkeypatch, alter_earlier_partition):
    """Exercise report assembly without artifacts/torch; inference is deliberately stubbed."""
    from types import SimpleNamespace
    users = [f'u{i}' for i in range(6)]
    cuts = ['2020-01-01', '2020-01-06', '2020-01-07', '2020-01-08', '2020-01-13']
    fitting = [row(u, f'2020-01-{d:02d}') for d in range(2, 7) for u in users]
    normal = [row(u, f'2020-01-{d:02d}') for d in range(9, 14) for u in users]
    parts = [[], fitting, [row(u, '2020-01-07') for u in users], [row(u, '2020-01-08') for u in users], normal]
    plan = {'switch_day_utc': '2020-01-09', 'cases': [
        {'case_id': f'case-{i // 2}', 'left': users[i], 'right': users[i + 1]} for i in range(0, 6, 2)]}
    manifest = {'cutoffs_utc': cuts, 'threshold_raw_mse': 1.0}
    monkeypatch.setattr(comparison, 'ROOT', tmp_path)
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    for name in ('personal_baseline.py', 'clue_native_projection.py', 'evaluate_personal_baseline.py'):
        (scripts / name).write_text('# synthetic metadata fixture')
    monkeypatch.setattr(comparison, 'verify_inputs', lambda *a: (manifest, plan, {'provenance': {}}, users, parts, {}))
    monkeypatch.setattr(comparison, 'candidate', lambda *a: (None, None, None, None, None, None))
    monkeypatch.setattr(comparison, 'version', lambda _: 'synthetic-test')
    monkeypatch.setattr(comparison, 'Prefix', lambda _: SimpleNamespace(events=lambda: []))
    monkeypatch.setattr(comparison, 'project_rows', lambda events, mapping, switch_day: mapping)

    def projected(data, cutoffs):
        mapping = data['rows']
        changed_parts = deepcopy(parts)
        # Missing donor activity becomes a missing recipient day, never a TN.
        omissions = {('u0', '2020-01-12'), ('u0', '2020-01-13')} if 'u0' in mapping else (
            {('u2', '2020-01-13')} if 'u2' in mapping else {('u5', '2020-01-12'), ('u5', '2020-01-13')})
        changed_parts[4] = []
        for source in normal:
            if (source['user'], source['date']) in omissions:
                continue
            changed = deepcopy(source)
            if source['user'] in mapping:
                changed['user'] = mapping[source['user']]
                changed['_synthetic_switch'] = True
            changed_parts[4].append(changed)
        if alter_earlier_partition:
            changed_parts[1][0]['features']['event_count'] = 999
        return users, changed_parts

    monkeypatch.setattr(comparison, 'select', projected)

    def inference(rows, reference, calibration, model, scaler, aliases, threshold):
        result = []
        for sample in rows:
            synthetic_switch = sample.get('_synthetic_switch', False)
            ae_value = 2.0 if not synthetic_switch and sample['date'] == '2020-01-09' and sample['user'] in users[:2] else (0.0 if synthetic_switch else 1.0)
            decisions = {'population': False, 'personal': False, 'ae': ae_value > threshold,
                         'ae_or_personal': ae_value > threshold}
            result.append({'account': aliases[sample['user']], 'date': sample['date'],
                           'alerts': decisions, 'scores': {'ae_raw_mse': ae_value}})
        return result

    monkeypatch.setattr(comparison, 'score_rows', inference)
    output = tmp_path / 'data/processed/comparison'
    if alter_earlier_partition:
        with pytest.raises(ValueError, match='earlier data'):
            comparison.run('data', 'bundle', 'prefix', 'plan', output)
        assert not (output / 'development_report.json').exists()
        return
    report = comparison.run('data', 'bundle', 'prefix', 'plan', output)
    assert report['development_normal']['rows'] == 30
    assert report['development_switches']['rows'] == 25
    assert [c['summary']['rows'] for c in report['cases']] == [8, 9, 8]
    assert [c['normal_controls']['rows'] for c in report['cases']] == [20, 20, 20]
    missing = report['cases'][0]['owner_active_dates_without_actor_activity']
    assert missing == {'cohort-1': [], 'cohort-2': ['2020-01-12', '2020-01-13']}
    assert all({d['account'], d['operated_by']} == {'cohort-1', 'cohort-2'} for d in report['cases'][0]['days'])
    assert report['cases_with_any_alert']['ae'] == 0
    assert report['activated'] is False
