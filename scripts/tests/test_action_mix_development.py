import copy
import pytest
from scripts.check_action_mix_development import decision, switched_rows
from scripts import context_feature_diagnostic as context
from scripts.resource_observability import token


def cases():
    return [{'case_id': str(i), 'left': str(2*i), 'right': str(2*i+1)} for i in range(3)]


def test_swaps_whole_day_without_mutating_or_creating_idle_days():
    rows = [{'user': '0', 'date': '2017-08-05', 'views': {'action_mix': {'a': 3}}},
            {'user': '2', 'date': '2017-08-06', 'views': {'action_mix': {'b': 2}}},
            {'user': 'other', 'date': '2017-08-05', 'views': {}}]
    before = copy.deepcopy(rows)
    result = switched_rows(rows, cases())
    assert [(c, u, r['user'], r['date']) for c, u, r in result] == [('0', '0', '1', '2017-08-05'), ('1', '2', '3', '2017-08-06')]
    result[0][2]['views']['action_mix']['a'] = 9
    assert rows == before
    with pytest.raises(ValueError):
        switched_rows(rows, [cases()[0]]*3)


def test_unseen_actions_are_distance_not_unavailability_and_volume_invariant():
    a, b = token('s', 'action', 'a'), token('s', 'action', 'b')
    assert context.js({a: 1.0}, {b: 1.0}) == 1
    assert context.distribution({a: 2, b: 6}) == context.distribution({a: 20, b: 60})


def rows(n, alerts, switched=False):
    return [{'score': 1 if i < alerts else 0, 'ae': 0.0, 'status': 'ready',
             'alert': i < alerts, 'case_id': str(i % 3)} for i in range(n)]


def test_gate_needs_coverage_normal_budget_recall_pairs_and_ranking():
    normal, positive = rows(191, 0), rows(25, 25)
    assert decision(normal, positive)['decision'] == 'go_to_fresh_protocol_design_only'
    positive = rows(25, 0)
    assert decision(normal, positive)['decision'] == 'no_go'
    normal = rows(191, 20)
    assert not decision(normal, rows(25, 25))['gates']['normal_alert_fraction_at_most_5_percent']
    normal = rows(191, 0)
    for r in normal[:30]:
        r.update(score=None, alert=None, status='unavailable')
    result = decision(normal, rows(25, 25))
    assert result['normal_scored'] == 161
    assert not result['gates']['normal_coverage_at_least_90_percent']


def test_no_data_cannot_pass_or_become_negatives():
    result = decision([], [])
    assert result['decision'] == 'no_go'
    assert result['normal_scored'] == result['switch_scored'] == 0
    assert result['common_metrics'] == {}
