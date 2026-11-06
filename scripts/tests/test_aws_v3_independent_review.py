"""Claude's independent C8 review checks on the installed AWS V3 calendar; pure, no provider or store access."""
from collections import Counter
from datetime import date, datetime, timedelta

import pytest

from scripts import aws_study_v3 as protocol, live_history_readiness as readiness, reserved_study as study

ACCOUNT, STACK = '123456789012', 'argus-ueba-actors'


def planned():
    return Counter((a['persona'], a['day']) for a in readiness.expected_actions(ACCOUNT, STACK).values())


def test_every_role_has_planned_activity_on_every_gate_day():
    """span>=7 in a 7-day fit window plus 2/2 validation days makes 1, 7, 8 and 9 Nov mandatory for all roles."""
    counts, roles = planned(), {f'persona-{i:02d}' for i in range(1, 7)}
    for start, end in protocol.WINDOWS.values():
        day = date.fromisoformat(start)
        while day <= date.fromisoformat(end):
            assert all(counts[role, day.isoformat()] >= 1 for role in roles), day
            day += timedelta(days=1)
    first, last = (date.fromisoformat(d) for d in protocol.WINDOWS['fit'])
    assert (last - first).days + 1 == 7  # the span gate leaves no slack: both edge days must be usable


@pytest.mark.parametrize('lost_day', ['2026-11-01', '2026-11-07', '2026-11-08', '2026-11-09'])
def test_one_lost_edge_or_validation_day_for_one_role_fails_the_whole_study(lost_day):
    days = [{'persona': f'persona-{i:02d}', 'day': d, 'partition': part, 'status': 'usable'}
            for i in range(1, 7) for part, (start, end) in protocol.WINDOWS.items()
            for d in (date.fromisoformat(start) + timedelta(n) for n in range(
                (date.fromisoformat(end) - date.fromisoformat(start)).days + 1))
            for d in [d.isoformat()]]
    assert readiness.history_gates(days)['eligible_roles'] == 6
    days = [r for r in days if not (r['persona'] == 'persona-06' and r['day'] == lost_day)]
    assert readiness.history_gates(days)['eligible_roles'] == 5  # release requires exactly 6


def test_last_case_day_action_has_margin_before_the_receipt_cutoff():
    grace, observed_max_lag = timedelta(minutes=15), timedelta(minutes=21)  # lag: 82 real persona events, 1 Nov
    for day in protocol.CASES:
        plan = study.plan_for_date(ACCOUNT, STACK, day, datetime(2026, 11, 1, tzinfo=protocol.MALAYSIA))
        latest = max(datetime.fromisoformat(a['planned_utc']) for a in plan['actions'])
        assert latest + grace + observed_max_lag + timedelta(hours=1) < protocol.RECEIPT_CUTOFF, day


def test_declared_slot_availability_matches_the_frozen_generator():
    slots = study.case_availability(ACCOUNT, STACK)
    status = {(day, s['persona']): s['status'] for day, items in slots.items() for s in items}
    assert status == {('2026-11-14', 'persona-01'): 'available', ('2026-11-14', 'persona-02'): 'available',
                      ('2026-11-15', 'persona-01'): 'unavailable_no_planned_target_read',
                      ('2026-11-15', 'persona-02'): 'available'}
