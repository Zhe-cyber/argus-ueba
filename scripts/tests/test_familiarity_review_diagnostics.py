"""Reporting-only review checks; original score and thresholds stay fixed."""
from copy import deepcopy
import math

import pytest

from scripts import account_familiarity as familiarity
from scripts.review_familiarity_diagnostics import near_threshold, unavailable_breakdown, prefix_token, exclusivity
from scripts.resource_observability import token


def test_near_ties_are_reported_without_reclassifying_strict_decisions():
    values = [None, 1.0, math.nextafter(1.0, math.inf), 1.0 - 1e-13, 1.0 + 1e-11]
    original = deepcopy(values)
    report = near_threshold(values, 1.0)
    assert report == {'scored_rows': 4, 'unavailable_rows': 1, 'strict_alerts': 2,
                      'exact_ties': 1, 'within_absolute_1e_minus12': 3, 'near_above': 1, 'near_below': 1}
    assert values == original


@pytest.mark.parametrize('values', [[float('nan')], [float('inf')], [True]])
def test_bad_scores_are_rejected(values):
    with pytest.raises(ValueError):
        near_threshold(values, 1)


def test_coverage_split_separates_no_activity_and_new_namespace():
    def row(count, known, status='no_fitting_known_tokens', score=None):
        return {'scores': {'resource': score}, 'statuses': {'resource': status},
                'dimensions': {'resources': {'distinct_tokens': count, 'fitting_known_tokens': known}}}
    report = unavailable_breakdown([row(0, 0), row(2, 0), row(1, 1, 'insufficient_fitting_dates'), row(1, 1, 'ready', 0)])
    assert {r['resource_activity']: r['rows'] for r in report} == {
        'no_resource_activity': 1, 'only_globally_unseen': 1, 'has_fitting_known_resources': 1}


def test_prefix_proxy_and_literal_exclusivity_do_not_assign_ownership():
    assert prefix_token('///files/a') == prefix_token('/files/b')
    assert prefix_token('/') is None
    assert prefix_token('/files/a') != prefix_token('/Files/a')
    resources = {'donor_only', 'shared', 'new'}
    counts = {'donor': {'donor_only': 2, 'shared': 2}, 'recipient': {'shared': 1}, 'third': {}}
    prefixes = {'donor_only': 'specific', 'shared': 'generic', 'new': 'specific'}
    prefix_users = {'specific': {'donor'}, 'generic': {'donor', 'recipient'}}
    report = exclusivity(resources, 'recipient', 'donor', counts, prefixes, prefix_users)
    assert report == {'distinct_resources': 3, 'fitting_known_resources': 2, 'globally_unseen_resources': 1,
                      'fitting_known_absent_from_recipient': 1, 'literal_tokens_seen_only_under_donor_in_fitting': 1,
                      'resources_with_first_component_seen_only_under_donor_in_fitting': 2,
                      'fitting_known_resources_with_donor_exclusive_first_component': 1}
    assert 'owner' not in report


def test_population_popularity_cancels_for_never_used_resources():
    def row(user, day, paths):
        return {'user': user, 'date': f'2020-01-{day:02d}', 'capture_boundary': False,
                'event_count': len(paths), 'path_event_count': len(paths),
                'resources': sorted(token('path', p) for p in paths), 'actions': [token('action', 'read')],
                'coverage': dict.fromkeys(('invalid_resource_events', 'missing_required_paths', 'unknown_action_events'), 0)}
    fitting = [row(u, d, paths) for u, paths in [('a', ['own']), ('b', ['common', 'rare']), ('c', ['common'])]
               for d in range(1, 6)]
    ref = familiarity.fit(fitting, '2020-01-01', '2020-01-05')
    rare = familiarity.score(ref, row('a', 6, ['rare']))['scores']['resource']
    common = familiarity.score(ref, row('a', 6, ['common']))['scores']['resource']
    assert rare == pytest.approx(math.log(2))
    assert common == pytest.approx(rare)
    assert ref.dimensions['resources'].pooled[token('path', 'common')] == 10
    assert ref.dimensions['resources'].pooled[token('path', 'rare')] == 5


def test_altered_report_refused_before_native_read(tmp_path, monkeypatch):
    from scripts import review_familiarity_diagnostics as diagnostics
    monkeypatch.setattr(diagnostics, 'ROOT', tmp_path)
    data = tmp_path / 'data/processed'
    data.mkdir(parents=True)
    (data / 'development_report.json').write_text('{}')
    monkeypatch.setattr(diagnostics, 'Prefix', lambda *args: pytest.fail('Read native data before report verification'))
    with pytest.raises(ValueError, match='unchanged W6 report'):
        diagnostics.run(data, 'prefix', 'manifest', data / 'supplement.json')
    assert not (data / 'supplement.json').exists()
