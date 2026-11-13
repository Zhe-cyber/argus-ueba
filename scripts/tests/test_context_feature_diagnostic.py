"""Synthetic separation examples test the machinery, not account identifiability."""
from copy import deepcopy
import hashlib

import pytest

from scripts import context_feature_diagnostic as diagnostic
from scripts.resource_observability import token


def row(user, day, category=None, events=1, paths=1):
    category = token('synthetic', user) if category is None else category
    return {'user': user, 'date': f'2020-01-{day:02d}', 'event_count': events, 'distinct_paths': paths,
            'coverage': dict.fromkeys(('invalid_resource_events', 'missing_required_paths', 'unknown_action_events'), 0),
            'views': {'action_mix': {category: events}, 'parent_depth1': {category: paths} if paths else {},
                      'parent_depth2': {category: paths} if paths else {}}}


@pytest.fixture
def fitting():
    return [row(u, d) for u in ('a', 'b', 'c', 'd') for d in range(1, 6)]


def test_js_identity_disjointness_symmetry_and_new_categories():
    assert diagnostic.js({'a': 1}, {'a': 1}) == 0
    assert diagnostic.js({'a': 1}, {'b': 1}) == 1
    left, right = {'a': .25, 'b': .75}, {'a': .75, 'c': .25}
    assert 0 < diagnostic.js(left, right) < 1
    assert diagnostic.js(left, right) == pytest.approx(diagnostic.js(right, left))


@pytest.mark.parametrize('bad', [{}, {'a': float('nan')}, {'a': -1}, {'a': .5}, {'a': True}])
def test_js_rejects_invalid_probabilities(bad):
    with pytest.raises(ValueError):
        diagnostic.js(bad, {'a': 1})


def test_parent_proxy_drops_leaf_but_preserves_literal_parent_case():
    for depth in (1, 2):
        assert diagnostic.parent_category('/team/work/a.txt', depth) == diagnostic.parent_category('/team/work/b.txt', depth)
        assert diagnostic.parent_category('/a.txt', depth) == diagnostic.parent_category('/b.txt', depth)
        assert diagnostic.parent_category('/team/work/a', depth) != diagnostic.parent_category('/Team/work/a', depth)
    assert diagnostic.parent_category('/team/work/a', 1) == diagnostic.parent_category('/team/other/b', 1)
    assert diagnostic.parent_category('/team/work/a', 2) != diagnostic.parent_category('/team/other/b', 2)


def test_reference_weights_dates_equally_not_by_events():
    a, b = token('category', 'a'), token('category', 'b')
    rows = [row('u', 1, a, events=999)] + [row('u', d, b) for d in range(2, 6)]
    ref = diagnostic.fit(rows, '2020-01-01', '2020-01-05')
    assert ref.centres['action_mix']['u'][a] == pytest.approx(.2)
    assert ref.centres['action_mix']['u'][b] == pytest.approx(.8)


def test_later_own_reference_comparison_and_immutability(fitting):
    ref = diagnostic.fit(fitting, '2020-01-01', '2020-01-05')
    before = ref.document()
    result = diagnostic.compare(ref, [row(u, 6) for u in ('a', 'b', 'c', 'd')], '2020-01-06', '2020-01-06')
    summary = diagnostic.summarize(result['action_mix'])
    assert summary['own_closer_than_median_other'] == summary['own_uniquely_nearest'] == 4
    assert summary['equal_account_mean_own_closer_fraction'] == 1
    assert ref.document() == before
    with pytest.raises(TypeError):
        ref.centres['action_mix']['a']['changed'] = 1
    with pytest.raises(ValueError, match='follow fitting'):
        diagnostic.compare(ref, [row('a', 5)], '2020-01-05', '2020-01-05')


def test_identical_profiles_count_ties_not_unique_identification(fitting):
    common = token('same')
    rows = [row(r['user'], int(r['date'][-2:]), common) for r in fitting]
    ref = diagnostic.fit(rows, '2020-01-01', '2020-01-05')
    results = diagnostic.compare(ref, [row('a', 6, common)], '2020-01-06', '2020-01-06')
    summary = diagnostic.summarize(results['action_mix'])
    assert summary['own_uniquely_nearest'] == summary['own_closer_than_median_other'] == 0
    assert summary['tied_with_median_other'] == summary['own_tied_for_nearest'] == 1


def test_unseen_categories_not_dropped_and_vocabulary_includes_sparse_accounts(fitting):
    special = token('sparse-only')
    rows = fitting + [row('sparse', d, special) for d in range(1, 5)]
    ref = diagnostic.fit(rows, '2020-01-01', '2020-01-05')
    assert 'sparse' not in ref.centres['action_mix']
    results = diagnostic.compare(ref, [row('a', 6, special), row('a', 7, token('brand-new'))], '2020-01-06', '2020-01-07')
    known, new = results['action_mix']
    assert known['globally_unseen_category_mass'] == 0
    assert new['globally_unseen_category_mass'] == new['own_distance'] == 1
    assert new['no_overlap_with_own']


def test_coverage_duplicate_and_sparse_gates(fitting):
    ref = diagnostic.fit(fitting, '2020-01-01', '2020-01-05')
    login = row('a', 6, paths=0)
    query = row('b', 6)
    query['coverage']['missing_required_paths'] = 1
    results = diagnostic.compare(ref, [login, query], '2020-01-06', '2020-01-06')
    assert results['parent_depth1'][0]['status'] == 'no_resource_activity'
    assert results['action_mix'][1]['status'] == 'unresolved_event_coverage'
    with pytest.raises(ValueError):
        diagnostic.fit(fitting + [deepcopy(fitting[0])], '2020-01-01', '2020-01-05')
    with pytest.raises(ValueError):
        diagnostic.summarize(results['action_mix'] * 2)
    sparse = diagnostic.fit([r for r in fitting if r['user'] == 'a'], '2020-01-01', '2020-01-05')
    assert diagnostic.compare(sparse, [row('a', 6)], '2020-01-06', '2020-01-06')['action_mix'][0]['status'] == 'fewer_than_three_other_references'


def test_native_projection_counts_distinct_paths_and_only_fitting_validation():
    from scripts.run_context_feature_diagnostic import project
    def event(day, path, uid='a', action='file_accessed'):
        return {'uid': uid, 'uidType': 'name', 'time': day + 'T12:00:00Z', 'type': action, 'params': {'path': path}}
    events = [event('2017-07-01', '/before'), event('2017-07-13', '/users/a/one'),
              event('2017-07-13', '/users/a/one'), event('2017-07-13', '/users/a/two'),
              event('2017-08-01', '/calibration-excluded'), event('2017-08-10', '/after')]
    user = hashlib.sha256(b'clue-7119953:a').hexdigest()
    rows = project(events, {user})
    assert len(rows) == 1 and rows[0]['event_count'] == 3 and rows[0]['distinct_paths'] == 2
    assert sum(rows[0]['views']['parent_depth1'].values()) == 2
    assert rows[0]['exact_uid_parent_match_paths'] == 2


def test_changed_input_refused_before_native_io(tmp_path, monkeypatch):
    from scripts import run_context_feature_diagnostic as runner
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    (inputs / 'development_report.json').write_text('{}')
    monkeypatch.setattr(runner, 'Prefix', lambda *a: pytest.fail('Native I/O before binding checks'))
    with pytest.raises(ValueError, match='frozen W6 report'):
        runner.run(inputs, 'prefix', 'manifest', tmp_path / 'data/processed/new')
