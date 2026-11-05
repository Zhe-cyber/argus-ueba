from datetime import datetime, timezone

from workspace_next import finding_context as fc

UTC = timezone.utc


def test_local_time_marks_malaysian_office_hours():
    # 02:00 UTC Wednesday = 10:00 MYT: inside office hours, but outside the detector's UTC window.
    assert fc.local_time(datetime(2026, 11, 4, 2, 0, tzinfo=UTC))[1] is True
    assert fc.local_time(datetime(2026, 11, 4, 10, 0, tzinfo=UTC))[1] is False  # 18:00 MYT, end is exclusive
    assert fc.local_time(datetime(2026, 11, 7, 2, 0, tzinfo=UTC))[1] is False   # Saturday
    assert fc.local_time(None) == (None, None)


def test_triage_never_hides_human_out_of_hours_or_multi_signal():
    assert fc.triage('anomalous_behavior', 'service_or_workload', False) == 'automation_context'
    assert fc.triage('anomalous_behavior', 'other_or_unclassified', True) == 'office_hours_context'
    assert fc.triage('anomalous_behavior', 'other_or_unclassified', False) == 'review_first'
    assert fc.triage('rarity_spike', 'other_or_unclassified', True) == 'review_first'
    assert fc.triage('anomalous_behavior', 'other_or_unclassified', None) == 'review_first'
    assert set(fc.TRIAGE_LABELS) == {'review_first', 'automation_context', 'office_hours_context'}
