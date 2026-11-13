"""W33 feature/history tests on synthetic native rows only."""
from datetime import date, timedelta
import hashlib
import math

import pytest

from scripts import clue_v2_features as v2
from scripts.shared_core_features import project_clue

START = date(2017, 9, 4)
_ids = iter(range(1, 10**9))


def native(uid, day, action='file_accessed', path='/nsA/file', hour=10, synthetic=False):
    row = {'id': next(_ids), 'uid': uid, 'uidType': 'name', 'type': action,
           'time': f'{day}T{hour:02d}:00:00Z', 'params': {} if path is None else {'path': path}}
    if synthetic:
        row['id'], row['_argus_scenario'] = 'sim:' + str(row['id']), 'test'
    return row


def build(rows, synthetic=False):
    day = v2.V2Day()
    for row in rows:
        day.add(project_clue(row, synthetic=synthetic))
    return day


def run(history, uid, days):
    """Commit (offset, rows) original days in order, returning each start-of-day snapshot."""
    out = []
    for offset, rows in days:
        day = build([dict(r, time=r['time'].replace('DAY', (START + timedelta(offset)).isoformat())) for r in rows])
        out.append(history.snapshot(day))
        history.commit_original(day)
    return out


def r(**kw):
    return native('alice', 'DAY', **kw)


def test_js_distance_closed_form_bounds_and_alignment():
    assert v2.js_distance([3, 1], [3, 1]) == 0.0
    a, b = 5 / 6, 1 / 6  # smoothed [2,0] vs [0,2]; symmetric so JS = KL(p||m)
    assert v2.js_distance([2, 0], [0, 2]) == pytest.approx(math.sqrt(a * math.log2(2 * a) + b * math.log2(2 * b)), abs=1e-15)
    extreme = v2.js_distance([10**6, 0], [0, 10**6])
    assert 0 < extreme <= 1
    for bad in [([1], [1, 2]), ([], []), ([-1, 1], [1, 1])]:
        with pytest.raises(ValueError):
            v2.js_distance(*bad)


def test_cold_start_needs_five_prior_usable_days():
    snaps = run(v2.History(), 'alice', [(d, [r()]) for d in range(6)])
    assert [s['status'] for s in snaps] == ['cold_start'] * 5 + ['eligible']
    assert snaps[4]['features'] is None and snaps[5]['prior_usable_days'] == 5
    assert snaps[5]['nine_feature_eligible'] and list(snaps[5]['features']) == v2.FEATURES


def test_invalid_original_day_is_neither_scored_nor_salvaged_into_history():
    history = v2.History()
    run(history, 'alice', [(d, [r()]) for d in range(5)])
    # file_accessed without a path invalidates the whole day, including its valid login.
    invalid = run(history, 'alice', [(5, [r(path=None), r(action='login_successful', path=None)])])[0]
    assert invalid['status'] == 'invalid_input' and invalid['issues'] == {'missing_required_resource': 1}
    later = run(history, 'alice', [(6, [r(), r(action='login_successful', path=None)])])[0]
    assert later['prior_usable_days'] == 5
    assert later['features']['new_action_count'] == 1  # login never entered history from the invalid day


def test_expanding_actions_versus_bounded_28_day_resources():
    days = [(0, [r(action='file_created', path='/old/x'), r()])] + [(d, [r()]) for d in range(1, 30)]
    days.append((30, [r(action='file_created', path='/old/y'), r()]))
    final = run(v2.History(), 'alice', days)[-1]
    assert final['features']['new_action_count'] == 0      # day 0 is still in expanding history
    assert final['features']['new_resource_share'] == 0.5  # day 0 left the 28-day window


def test_volume_ratio_uses_even_median_midpoint():
    history = v2.History()
    run(history, 'alice', [(d, [r() for _ in range(d + 1)]) for d in range(6)])
    today = run(history, 'alice', [(6, [r() for _ in range(10)])])[0]
    assert today['features']['volume_log_ratio'] == pytest.approx(math.log1p(10) - math.log1p(3.5), abs=1e-15)


def test_unseen_action_kind_stays_in_support():
    history = v2.History()
    run(history, 'alice', [(d, [r()]) for d in range(5)])
    today = run(history, 'alice', [(5, [r(), r(action='login_successful', path=None)])])[0]
    assert today['features']['action_mix_js_distance'] == pytest.approx(v2.js_distance([1, 1], [5, 0]), abs=0)
    assert today['features']['action_mix_js_distance'] > 0


def test_hour_profile_is_utc_event_weighted():
    history = v2.History()
    run(history, 'alice', [(d, [r(hour=9), r(hour=9), r(hour=15)]) for d in range(5)])
    today = run(history, 'alice', [(5, [r(hour=3)])])[0]
    prior = [0] * 24; prior[9], prior[15] = 10, 5
    current = [0] * 24; current[3] = 1
    assert today['features']['hour_profile_js_distance'] == pytest.approx(v2.js_distance(current, prior), abs=0)


def test_resource_free_day_has_unavailable_share_but_core_features():
    history = v2.History()
    run(history, 'alice', [(d, [r()]) for d in range(5)])
    today = run(history, 'alice', [(5, [r(action='login_successful', path=None)])])[0]
    assert today['features']['new_resource_share'] is None
    assert today['unavailable'] == {'new_resource_share': 'no_resource_today'}
    assert today['five_feature_eligible'] and not today['nine_feature_eligible']
    assert today['features']['unique_resources'] == 0


def test_off_hours_is_time_of_day_only_including_weekends():
    history = v2.History()
    run(history, 'alice', [(d, [r()]) for d in range(5)])  # 4-8 Sep
    saturday = (date(2017, 9, 9) - START).days
    day = run(history, 'alice', [(saturday, [r(hour=10), r(hour=20)])])[0]
    assert day['features']['off_hours_fraction'] == 0.5


def test_variants_share_start_of_day_snapshot_and_never_update_history():
    history = v2.History()
    run(history, 'alice', [(d, [r()]) for d in range(5)])
    today = (START + timedelta(5)).isoformat()
    original = build([native('alice', today)])
    variant = build([native('alice', today, synthetic=True) for _ in range(5)], synthetic=True)
    first = history.snapshot(original)
    assert history.snapshot(variant)['prior_usable_days'] == first['prior_usable_days']
    with pytest.raises(ValueError, match='Injected'):
        history.commit_original(variant)
    assert history.snapshot(original) == first
    history.commit_original(original)
    for again in (original, build([native('alice', (START + timedelta(4)).isoformat())])):
        with pytest.raises(ValueError, match='advance'):
            history.snapshot(again)


def test_accounts_do_not_share_history():
    history = v2.History()
    run(history, 'alice', [(d, [r()]) for d in range(5)])
    bob = build([native('bob', (START + timedelta(5)).isoformat())])
    assert history.snapshot(bob)['status'] == 'cold_start'


def test_cohort_rank_encoding_threshold_cap_and_ties(monkeypatch):
    for account in ['acct', 'ü-user']:
        expected = hashlib.sha256(f'[42,"clue_ae_v2_cohort","{account}"]'.encode('utf-8')).hexdigest()
        assert v2.cohort_rank(account) == expected
    activity = {'a': 5, 'b': 9, 'c': 4, 'd': 6, 'e': 5}
    monkeypatch.setattr(v2, 'COHORT_MAX', 2)
    chosen = v2.select_cohort(activity)
    ranked = sorted(['a', 'b', 'd', 'e'], key=lambda x: (v2.cohort_rank(x), x.encode('utf-8')))
    assert chosen['selected'] == ranked[:2]
    assert (chosen['eligible'], chosen['below_min_active_fit_days'], chosen['excluded_by_cap']) == (4, 1, 2)
    assert v2.select_cohort(dict(reversed(list(activity.items())))) == chosen


def test_fitting_activity_rejects_non_fitting_dates():
    assert v2.fitting_activity({'a': ['2017-09-04', '2017-09-04', '2017-11-26']}) == {'a': 2}
    for day in ['2017-09-03', '2017-11-27', '2018-01-15']:
        with pytest.raises(ValueError):
            v2.fitting_activity({'a': [day]})
