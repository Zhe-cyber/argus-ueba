"""W33 explanation tests: exact error terms on a real (randomly initialised) AE, facts, and state binding."""
from datetime import date, timedelta

import pytest

from scripts import clue_v2_features as v2, explain_clue_v2 as explain, train_clue_v2 as trainer
from scripts.shared_core_features import project_clue

_ids = iter(range(1, 10**9))
START = date(2017, 9, 4)


def native(action='file_accessed', path='/nsA/f', hour=10, uid='alice'):
    return {'id': next(_ids), 'uid': uid, 'uidType': 'name', 'type': action, 'time': f'DAYT{hour:02d}:00:00Z',
            'params': {} if path is None else {'path': path}}


def build(rows, offset):
    day = v2.V2Day()
    for row in rows:
        day.add(project_clue(dict(row, time=row['time'].replace('DAY', (START + timedelta(offset)).isoformat()))))
    return day


def prepared(prior_days, today_rows):
    """History advanced through the prior days only; today's snapshot taken but NOT committed."""
    history = v2.History()
    for offset, rows in enumerate(prior_days):
        day = build(rows, offset)
        history.snapshot(day); history.commit_original(day)
    today = build(today_rows, len(prior_days))
    return history, today, history.snapshot(today)


def usual():
    return [native(hour=9), native(hour=10), native(hour=14)]


def bundle():
    import torch
    torch.manual_seed(0)
    return {'C': (trainer.build_model(trainer.METHOD['detectors']['C']['architecture']).eval(),
                  trainer.Scaler([0.0] * 9, [1.0] * 9), v2.FEATURES),
            'B': (trainer.build_model(trainer.METHOD['detectors']['B']['architecture']).eval(),
                  trainer.Scaler([0.0] * 5, [1.0] * 5), v2.FEATURES[:5])}


def test_additive_terms_sum_to_the_exact_detector_score():
    import torch
    torch.manual_seed(0)
    model = trainer.build_model(trainer.METHOD['detectors']['C']['architecture']).eval()
    scaler = trainer.Scaler([0.5] * 9, [1.0] * 9)
    features = dict(zip(v2.FEATURES, [12, 3, 2, 0.25, 1, 0.7, 0.5, 0.3, 0.6]))
    result = explain.contributions(model, scaler, v2.FEATURES, features)
    expected = trainer.score_rows(model, scaler.transform(trainer.matrix([{'features': features}], v2.FEATURES)))[0]
    assert result['score_raw_mse'] == expected
    assert sum(t['additive_term'] for t in result['terms']) == pytest.approx(expected, rel=1e-6)
    assert sum(t['share_of_reconstruction_error'] for t in result['terms']) == pytest.approx(1.0)
    values = [t['squared_residual'] for t in result['terms']]
    assert values == sorted(values, reverse=True)


def test_facts_volume_new_actions_resources_hours_and_largest_share():
    today = [native(hour=2) for _ in range(9)] + [native(action='permission_changed', path='/nsZ/x', hour=3) for _ in range(3)]
    history, day, snapshot = prepared([usual() for _ in range(6)], today)
    facts = {f['kind']: f for f in explain.explain(snapshot, history, day, bundle())['facts']}
    assert (facts['volume']['today'], facts['volume']['recent_median'], facts['volume']['ratio']) == (12, 3, 4.0)
    assert facts['new_actions']['actions'] == ['permission_changed']
    assert 'not observed in the available prior usable history' in facts['new_actions']['text']
    assert (facts['new_resources']['new'], facts['new_resources']['total']) == (1, 2)
    assert facts['hours']['usual_hours'] == [9, 10, 14] and facts['hours']['events_outside_usual_hours'] == 12
    assert facts['action_mix']['today_largest'] == 'file_accessed' and facts['action_mix']['recent_share'] == 1.0
    assert 'mostly' not in facts['action_mix']['text']


def test_uniform_hour_history_does_not_claim_unusual_hours():
    every_hour = [native(hour=h) for h in range(24)]
    history, day, snapshot = prepared([[dict(r, id=next(_ids)) for r in every_hour] for _ in range(6)],
                                      [dict(r, id=next(_ids)) for r in every_hour])
    assert snapshot['features']['hour_profile_js_distance'] == 0.0
    hours = {f['kind']: f for f in explain.explain(snapshot, history, day, bundle())['facts']}['hours']
    assert hours['usual_hours'] == [] and hours['events_outside_usual_hours'] is None
    assert hours['text'].startswith('No concentrated usual hours can be established')


def test_action_share_ties_are_deterministic():
    history, day, snapshot = prepared([usual() for _ in range(6)],
                                      [native(action='login_successful', path=None), native(action='file_accessed')])
    mix = {f['kind']: f for f in explain.explain(snapshot, history, day, bundle())['facts']}['action_mix']
    assert mix['today_largest'] == 'file_accessed' and mix['today_share'] == 0.5  # tie broken by name


def test_explanation_rejects_a_state_advanced_past_the_scored_snapshot():
    history, day, snapshot = prepared([usual() for _ in range(6)], [native(action='permission_changed', path='/nsZ/x')])
    history.commit_original(day)  # accidental commit before explaining
    with pytest.raises(ValueError):
        explain.explain(snapshot, history, day, bundle())


def test_explanation_rejects_a_snapshot_from_a_different_state():
    history, day, snapshot = prepared([usual() for _ in range(6)], usual())
    forged = dict(snapshot, prior_usable_days=7)
    with pytest.raises(ValueError, match='differs'):
        explain.explain(forged, history, day, bundle())


def test_why_unscored_and_model_layers_follow_eligibility():
    history, day, cold = prepared([usual() for _ in range(3)], usual())
    result = explain.explain(cold, history, day, bundle())
    assert result['why_unscored'] == 'Insufficient history: 3 of 5 usable prior days.' and result['detectors'] == {}
    history, day, invalid = prepared([usual() for _ in range(6)], [native(path=None)])
    assert explain.why_unscored(invalid) == 'Input incomplete for this day: missing_required_resource (1).'
    history, day, free = prepared([usual() for _ in range(6)], [native(action='login_successful', path=None)])
    result = explain.explain(free, history, day, bundle())
    assert set(result['detectors']) == {'B'} and result['why_unscored'].startswith('No resource today')
    assert result['key']['scope'] == '7119953' and result['key']['day'] == (START + timedelta(6)).isoformat()
    text = ' '.join(f['text'] for f in result['facts']).lower()
    assert not any(word in text for word in ('attack', 'malicious', 'compromise', 'suspicious', 'never seen'))
