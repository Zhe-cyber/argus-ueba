"""Algorithm identity for the RUNNING method, baseline score v1.2: the same 47 inputs as v1.1, outputs regenerated
on 2026-11-12 with the sensitive first-access floor. No case changed (none has sensitive_new >= 0.5 with a score
below 30); the floor itself is pinned by the unit tests below."""
from datetime import date
import json
from pathlib import Path

import pytest

from backend import baseline_scorer as scorer
from backend.tests.test_baseline_reference import compute

OUT = Path(__file__).resolve().parent / 'data' / 'baseline_reference_v1_2.json'
CASES = json.loads(OUT.read_text(encoding='utf-8'))['cases']


def test_running_scorer_is_v1_2_and_bound_to_this_file():
    assert scorer.VERSION == 'baseline-risk-score-v1.2' and scorer.REFERENCE_FILE == OUT
    assert (scorer.SENSITIVE_FLOOR_SIGNAL, scorer.SENSITIVE_FLOOR_SCORE) == (0.5, 30)


@pytest.mark.parametrize('case', CASES, ids=[c['name'] for c in CASES])
def test_reference_vector_v1_2(case):
    assert compute(case, scorer.SENSITIVE_FLOOR_SCORE) == case['expected']


def _days(evaluable_new, sensitive='lab-confidential', extra_today=()):
    """History of 3 + len(evaluable_new) days; evaluable_new[i] True adds a never-seen resource that day (sets rho_r).
    Today: 4 usual reads plus one read of `sensitive` (flagged by the deployment list)."""
    rows = [[f'2026-10-0{d}T02:00:00Z', 'aws_cloudtrail', 'GetObject', 'lab-p01'] for d in range(1, 4) for _ in range(4)]
    for i, new in enumerate(evaluable_new, 4):
        rows += [[f'2026-10-{i:02d}T02:00:00Z', 'aws_cloudtrail', 'GetObject', 'lab-p01']] * 4
        if new:
            rows.append([f'2026-10-{i:02d}T02:00:00Z', 'aws_cloudtrail', 'GetObject', f'lab-new-{i}'])
    rows += [['2026-10-20T02:00:00Z', 'aws_cloudtrail', 'GetObject', 'lab-p01']] * 4
    rows += [['2026-10-20T02:00:00Z', 'aws_cloudtrail', 'GetObject', sensitive], *extra_today]
    return scorer.group_days(rows)


def score(days):
    return scorer.score_day(days, date(2026, 10, 20))


def test_floor_applies_at_exactly_half():
    r = score(_days([True, False]))  # rho_resource 0.5 -> sensitive_new 0.5
    assert r['signals']['sensitive_new'] == 0.5 and r['score'] == 30 and r['tier'] == 'Medium'
    assert r['facts'][-1] == 'First access to a sensitive resource in the last 28 days: lab-confidential (minimum tier Medium)'


def test_floor_does_not_apply_below_half():
    r = score(_days([True, True, False, False, True]))  # rho_resource 0.6 -> sensitive_new 0.4
    assert r['signals']['sensitive_new'] == 0.4 and r['score'] < 30 and r['tier'] == 'Low'
    assert not any('minimum tier' in f for f in r['facts'])


def test_floor_lifts_what_v1_1_left_low(monkeypatch):
    lifted = score(_days([True, False]))
    monkeypatch.setattr(scorer, 'SENSITIVE_FLOOR_SCORE', None)
    v11 = score(_days([True, False]))
    assert v11['score'] < 30 and v11['tier'] == 'Low' and lifted['score'] == 30
    assert {k: v for k, v in lifted.items() if k not in ('score', 'tier', 'facts')} == {k: v for k, v in v11.items() if k not in ('score', 'tier', 'facts')}
    assert lifted['facts'][:-1] == v11['facts']  # only the floor fact is added


def test_no_floor_when_unavailable_or_learning():
    no_res = scorer.group_days([[f'2026-10-0{d}T02:00:00Z', 'aws_cloudtrail', 'ListBuckets', ''] for d in range(1, 7)]
                               + [['2026-10-20T02:00:00Z', 'aws_cloudtrail', 'ListBuckets', '']])
    r = score(no_res)
    assert r['signals']['new_resource'] is None and r['signals']['sensitive_new'] == 0.0 and r['score'] == 0
    learning = scorer.group_days([['2026-10-19T02:00:00Z', 'aws_cloudtrail', 'GetObject', 'lab-p01'],
                                  ['2026-10-20T02:00:00Z', 'aws_cloudtrail', 'GetObject', 'lab-confidential']])
    assert score(learning)['tier'] == 'Learning' and score(learning)['score'] is None


def test_score_already_medium_or_more_is_unchanged(monkeypatch):
    loud = [['2026-10-20T13:00:00Z', 'aws_cloudtrail', 'DeleteObject', 'lab-confidential']] * 30
    with_floor = score(_days([False, False], extra_today=loud))
    monkeypatch.setattr(scorer, 'SENSITIVE_FLOOR_SCORE', None)
    assert with_floor == score(_days([False, False], extra_today=loud)) and with_floor['score'] >= 30
