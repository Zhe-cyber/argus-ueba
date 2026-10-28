"""Synthetic contract tests, not empirical evidence of detection quality."""
from copy import deepcopy
import hashlib
import json
import math

import pytest

from scripts import account_familiarity as model
from scripts.clue_familiarity_projection import project
from scripts.personal_baseline import alert, either
from scripts.resource_observability import token


def row(user, day, resources=None, actions=None):
    resources = [token('resource', user)] if resources is None else resources
    actions = [token('action', 'read')] if actions is None else actions
    return {'user': user, 'date': f'2020-01-{day:02d}', 'capture_boundary': False,
            'event_count': max(1, len(resources), len(actions)), 'path_event_count': len(resources),
            'resources': sorted(resources), 'actions': sorted(actions),
            'coverage': dict.fromkeys(('invalid_resource_events', 'missing_required_paths', 'unknown_action_events'), 0)}


@pytest.fixture
def fitting():
    return [row(u, d) for u in ('a', 'b', 'c') for d in range(1, 6)]


@pytest.fixture
def reference(fitting):
    return model.fit(fitting, '2020-01-01', '2020-01-05')


def test_resource_change_with_identical_counts_changes_score(reference):
    own, other = row('a', 8), row('a', 8, [token('resource', 'b')])
    assert own['event_count'] == other['event_count']
    assert model.score(reference, own)['scores'] == {'resource': 0.0, 'joint': 0.0}
    changed = model.score(reference, other)
    assert changed['scores']['resource'] == pytest.approx(math.log(2))
    assert changed['scores']['joint'] == changed['scores']['resource']
    assert changed['dimensions']['resources']['known_tokens_unseen_by_account'] == 1


def test_joint_is_fixed_max_and_action_counts_do_not_change_identity(fitting):
    for r in fitting:
        r['actions'] = [token('action', r['user'])]
    reference = model.fit(fitting, '2020-01-01', '2020-01-05')
    changed = row('a', 8, actions=[token('action', 'b')])
    scores = model.score(reference, changed)['scores']
    assert scores['resource'] == 0
    assert scores['joint'] == pytest.approx(math.log(2))


def test_reference_is_immutable_and_roundtrips(reference):
    document = reference.document()
    restored = model.load_reference(json.loads(json.dumps(document)))
    before = restored.document()
    document['dimensions']['resources']['counts']['a'].clear()
    sample = row('a', 8, [token('resource', 'b')])
    assert model.score(reference, sample) == model.score(restored, sample)
    assert restored.document() == before
    with pytest.raises(TypeError):
        restored.dimensions['resources'].counts['a']['x'] = 3
    sample['resources'] = [token('resource', 'new')]
    model.score(restored, sample)
    assert restored.document() == before


def test_unknown_resources_are_unavailable_not_zero_or_learned(reference):
    sample = row('a', 8, [token('resource', 'new')])
    result = model.score(reference, sample)
    assert result['scores'] == {'resource': None, 'joint': None}
    assert result['statuses']['resource'] == 'no_fitting_known_tokens'
    assert result['dimensions']['resources']['globally_unseen_fraction'] == 1
    assert model.score(reference, sample) == result


def test_partial_known_fraction_excludes_unseen_but_reports_it(reference):
    sample = row('a', 8, [token('resource', 'b'), token('resource', 'new')])
    result = model.score(reference, sample)
    assert result['scores']['resource'] == pytest.approx(math.log(2))
    assert result['dimensions']['resources']['globally_unseen_fraction'] == .5


def test_unknown_account_and_sparse_history(fitting, reference):
    assert model.score(reference, row('new', 8))['statuses']['resource'] == 'unknown_account'
    fitting = [r for r in fitting if not (r['user'] == 'a' and r['date'] == '2020-01-05')]
    sparse = model.fit(fitting, '2020-01-01', '2020-01-05')
    assert model.score(sparse, row('a', 8))['statuses']['resource'] == 'insufficient_fitting_dates'


@pytest.mark.parametrize('field', ['invalid_resource_events', 'missing_required_paths', 'unknown_action_events'])
def test_coverage_gaps_are_not_scores(reference, field):
    sample = row('a', 8)
    sample['coverage'][field] = 1
    assert model.score(reference, sample)['scores'] == {'resource': None, 'joint': None}


def test_no_resource_day_is_unavailable_but_fits_actions(fitting):
    for r in fitting:
        if r['user'] == 'a':
            r['resources'], r['path_event_count'] = [], 0
    reference = model.fit(fitting, '2020-01-01', '2020-01-05')
    assert reference.dimensions['resources'].days['a'] == 0
    assert reference.dimensions['actions'].days['a'] == 5
    assert model.score(reference, row('a', 8, []))['scores']['resource'] is None


@pytest.mark.parametrize('day', [1, 5])
def test_scores_must_follow_fitting(reference, day):
    with pytest.raises(ValueError, match='follow fitting'):
        model.score(reference, row('a', day))


def test_fit_rejects_duplicates_wrong_dates_and_coverage(fitting):
    for rows in [fitting + [deepcopy(fitting[0])], fitting + [row('a', 6)]]:
        with pytest.raises(ValueError):
            model.fit(rows, '2020-01-01', '2020-01-05')
    fitting[0]['coverage']['missing_required_paths'] = 1
    with pytest.raises(ValueError, match='coverage'):
        model.fit(fitting, '2020-01-01', '2020-01-05')


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(shrinkage_dates=10),
    lambda d: d.update(activated=True),
    lambda d: d['dimensions']['resources']['days'].update(a=16),
    lambda d: d['dimensions']['resources']['counts']['a'].update({token('resource', 'a'): 6}),
    lambda d: d['dimensions']['actions']['days'].pop('a'),
])
def test_reload_rejects_altered_contract_and_impossible_counts(reference, mutation):
    document = reference.document()
    mutation(document)
    with pytest.raises(ValueError):
        model.load_reference(document)


def test_normal_calibration_strict_threshold_and_union_missing(reference):
    rows = [row(u, d) for u in ('a', 'b', 'c') for d in (6, 7)]
    calibration = model.calibrate(reference, rows, '2020-01-06', '2020-01-07')
    assert calibration['joint']['threshold'] == 0
    assert calibration['joint']['degenerate_calibration']
    assert calibration['joint']['normal_calibration_alerts'] == 0
    assert alert(0, calibration['joint']['threshold']) is False
    assert either(False, None) is None
    assert either(True, None) is True
    with pytest.raises(ValueError):
        model.calibrate(reference, rows[:2], '2020-01-06', '2020-01-07')
    with pytest.raises(ValueError, match='three accounts'):
        model.calibrate(reference, [row(u, d) for u in ('a', 'b') for d in (6, 7, 8)],
                        '2020-01-06', '2020-01-08')


def test_native_projection_deduplicates_daily_presence_and_preserves_actor_independent_paths():
    def event(user, day, action='file_accessed', path='same'):
        return {'uid': user, 'uidType': 'name', 'time': f'2020-01-{day:02d}T12:00:00Z',
                'type': action, 'params': {'path': path}}
    events = [event(u, d, path=u) for u in ('a', 'b') for d in range(1, 5)]
    events.append(event('a', 2, path='a'))
    original = project(events)
    names = {u: hashlib.sha256(('clue-7119953:' + u).encode()).hexdigest() for u in ('a', 'b')}
    changed = project(events, {names['a']: names['b'], names['b']: names['a']}, '2020-01-03')
    assert [r for r in original if r['date'] < '2020-01-03'] == [r for r in changed if r['date'] < '2020-01-03']
    repeated = next(r for r in original if r['user'] == names['a'] and r['date'] == '2020-01-02')
    assert repeated['event_count'] == 2 and len(repeated['resources']) == 1
    borrowed = next(r for r in changed if r['user'] == names['b'] and r['date'] == '2020-01-03')
    assert borrowed['resources'] == repeated['resources']


def test_projection_separates_inapplicable_and_missing_required_paths():
    events = [{'uid': 'a', 'uidType': 'name', 'time': '2020-01-02T12:00:00Z',
               'type': action, 'params': {}} for action in ('login_successful', 'file_accessed')]
    row = project(events[:1])[0]
    assert not any(row['coverage'].values())
    assert project(events)[0]['coverage']['missing_required_paths'] == 1


def test_report_counts_common_subset_and_preserves_unavailable():
    from scripts.evaluate_account_familiarity import summary
    records = [{'account': 'a', 'date': '2020-01-08',
                'alerts': {'resource': None, 'joint': None, 'ae': False, 'ae_or_joint': None},
                'statuses': {'resource': 'no_fitting_known_tokens', 'joint': 'required_dimension_unavailable'}},
               {'account': 'b', 'date': '2020-01-08',
                'alerts': {'resource': True, 'joint': True, 'ae': False, 'ae_or_joint': True},
                'statuses': {'resource': 'ready', 'joint': 'ready'}}]
    report = summary(records)
    assert report['rows'] == 2 and report['common_scorable_rows'] == 1
    assert report['methods']['ae']['scored_rows'] == 2
    assert report['methods']['joint']['unavailable_rows'] == 1
    assert report['methods']['joint']['common_alert_fraction'] == 1
    with pytest.raises(ValueError):
        summary(records + [deepcopy(records[0])])


def test_bad_artifact_bindings_stop_before_loading_weights(tmp_path, monkeypatch):
    from scripts import evaluate_account_familiarity as comparison
    monkeypatch.setattr(comparison, 'ROOT', tmp_path)
    monkeypatch.setattr(comparison, 'candidate', lambda *args: pytest.fail('Weights loaded before binding check'))
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    (bundle / 'clue_model_manifest.json').write_text('{}')
    with pytest.raises(ValueError, match='pinned'):
        comparison.run('data', bundle, 'prefix', 'plan', tmp_path / 'data/processed/new-output')
    assert not (tmp_path / 'data/processed/new-output').exists()


@pytest.mark.parametrize('bad', [[None], [[]], [token('resource', 'a')] * 2])
def test_invalid_or_duplicate_tokens_are_rejected(reference, bad):
    sample = row('a', 8)
    sample['resources'] = bad
    with pytest.raises(ValueError, match='distinct hashed tokens'):
        model.score(reference, sample)


@pytest.mark.parametrize('contaminate_history', [False, True])
def test_pipeline_case_assembly_and_prior_history_guard(tmp_path, monkeypatch, contaminate_history):
    """Inference and native parsing stubbed; checks glue and denominators, not efficacy."""
    from types import SimpleNamespace
    from scripts import evaluate_account_familiarity as comparison
    users = [f'u{i}' for i in range(6)]
    cuts = ['2020-01-01', '2020-01-06', '2020-01-07', '2020-01-08', '2020-01-13']
    parts = [[], [row(u, d) for u in users for d in range(2, 7)],
             [row(u, 7) for u in users], [row(u, 8) for u in users],
             [row(u, d) for u in users for d in range(9, 14)]]
    originals = {(r['user'], r['date']): r for p in parts for r in p}
    plan = {'switch_day_utc': '2020-01-09', 'cases': [
        {'case_id': str(i), 'left': users[i], 'right': users[i + 1]} for i in (0, 2, 4)]}
    manifest = {'cutoffs_utc': cuts, 'threshold_raw_mse': 1.0}
    monkeypatch.setattr(comparison, 'ROOT', tmp_path)
    (tmp_path / 'scripts').mkdir()
    for name in ('account_familiarity.py', 'clue_familiarity_projection.py',
                 'resource_observability.py', 'evaluate_account_familiarity.py'):
        (tmp_path / 'scripts' / name).write_text('# synthetic metadata fixture')
    monkeypatch.setattr(comparison, 'verify_inputs', lambda *args: (manifest, plan, {'rows': [], 'provenance': {}}, users, parts, {}))
    monkeypatch.setattr(comparison, 'candidate', lambda *args: (None,) * 6)
    monkeypatch.setattr(comparison, 'version', lambda _: 'synthetic-test')
    monkeypatch.setattr(comparison, 'Prefix', lambda _: SimpleNamespace(events=lambda: []))
    monkeypatch.setattr(comparison, 'index_projection', lambda rows, frozen: rows)
    monkeypatch.setattr(comparison, 'project_rows', lambda events, mapping, day: mapping)

    def changed(mapping):
        result = deepcopy(parts)
        omitted = ({('u0', '2020-01-12'), ('u0', '2020-01-13')} if 'u0' in mapping else
                   {('u2', '2020-01-13')} if 'u2' in mapping else
                   {('u5', '2020-01-12'), ('u5', '2020-01-13')})
        result[4] = []
        for r in parts[4]:
            if (r['user'], r['date']) in omitted:
                continue
            new = deepcopy(r)
            if r['user'] in mapping:
                new['user'] = mapping[r['user']]
                new['_switched'] = True
            result[4].append(new)
        return result

    def resource_projection(events, mapping=None, day=None):
        if mapping is None:
            return deepcopy(originals)
        projected = changed(mapping)
        if contaminate_history:
            projected[1][0]['resources'] = [token('invalid', 'earlier-change')]
        return {(r['user'], r['date']): r for p in projected for r in p}

    def fake_residuals(rows, *args):
        values = [2.0 if r['user'] in users[:2] and r['date'] == '2020-01-09' and not r.get('_switched')
                  else 0.0 if r.get('_switched') else 1.0 for r in rows]
        return SimpleNamespace(mean=lambda axis: SimpleNamespace(tolist=lambda: values))

    monkeypatch.setattr(comparison, 'project', resource_projection)
    monkeypatch.setattr(comparison, 'select', lambda data, _: (users, changed(data['rows'])))
    monkeypatch.setattr(comparison, 'residuals', fake_residuals)
    output = tmp_path / 'data/processed/familiarity'
    if contaminate_history:
        with pytest.raises(ValueError, match='familiarity history'):
            comparison.run('data', 'bundle', 'prefix', 'plan', output)
        assert not (output / 'development_report.json').exists()
        return
    report = comparison.run('data', 'bundle', 'prefix', 'plan', output)
    assert report['development_normal']['rows'] == 30
    assert report['development_switches']['rows'] == 25
    assert [c['summary']['rows'] for c in report['cases']] == [8, 9, 8]
    assert all(c['normal_controls']['rows'] == 20 for c in report['cases'])
    assert report['cases'][0]['owner_active_dates_without_actor_activity'] == {
        'cohort-1': [], 'cohort-2': ['2020-01-12', '2020-01-13']}
    assert all({r['account'], r['operated_by']} == {'cohort-1', 'cohort-2'} for r in report['cases'][0]['days'])
    assert report['development_switches']['methods']['ae']['alerts'] == 0
    assert report['activated'] is False
