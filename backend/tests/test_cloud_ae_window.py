"""
test_cloud_ae_window.py — W2 cloud train/serve skew fix.

Covers the pure window/history split that mirrors the training contract
(scripts/build_cloud_dataset.py:207-233): each user is scored on their LATEST
UTC calendar day (window), with every strictly earlier cloud event as history
(which feeds new_action_count). No model files are required — these tests
exercise only the split + day-parsing logic.
"""
from __future__ import annotations

from backend.ae_scorer import _CloudAEScorer
from backend.cloud_feature_extractor import aggregate_window


def _ev(ts: str, action: str = "GetObject", resource: str = "s3://b/k",
        ip: str = "10.0.0.1"):
    return {"timestamp": ts, "action": action, "resource": resource,
            "ip_address": ip, "source": "aws_cloudtrail"}


# ---------------------------------------------------------------------------
# _split_latest_day
# ---------------------------------------------------------------------------

def test_multi_day_split_window_is_latest_day_only():
    """Events across 3 days → window = day-3 events; history = days 1-2."""
    events = [
        _ev("2026-01-01T09:00:00Z", action="ListBuckets"),
        _ev("2026-01-01T10:00:00Z", action="GetObject"),
        _ev("2026-01-02T09:00:00Z", action="AssumeRole"),
        _ev("2026-01-03T09:00:00Z", action="DeleteUser"),
        _ev("2026-01-03T11:00:00Z", action="CreateAccessKey"),
    ]
    window, history = _CloudAEScorer._split_latest_day(events)

    assert len(window) == 2
    assert {e["action"] for e in window} == {"DeleteUser", "CreateAccessKey"}
    assert len(history) == 3
    assert {e["action"] for e in history} == {"ListBuckets", "GetObject", "AssumeRole"}


def test_single_day_user_has_empty_history():
    """A user whose events are all on one day → history empty, window = all."""
    events = [
        _ev("2026-02-05T08:00:00Z"),
        _ev("2026-02-05T14:30:00Z"),
        _ev("2026-02-05T22:00:00Z"),
    ]
    window, history = _CloudAEScorer._split_latest_day(events)

    assert len(window) == 3
    assert history == []


def test_empty_events_returns_empty_pair():
    window, history = _CloudAEScorer._split_latest_day([])
    assert window == []
    assert history == []


def test_malformed_timestamps_are_skipped_not_crashing():
    """Rows with unparseable timestamps are dropped; valid ones still split."""
    events = [
        _ev("not-a-timestamp"),
        _ev(""),
        {"action": "GetObject"},  # missing timestamp entirely
        _ev("2026-03-01T09:00:00Z", action="ListBuckets"),
        _ev("2026-03-02T09:00:00Z", action="AssumeRole"),
    ]
    window, history = _CloudAEScorer._split_latest_day(events)

    assert [e["action"] for e in window] == ["AssumeRole"]
    assert [e["action"] for e in history] == ["ListBuckets"]


def test_all_malformed_timestamps_returns_empty():
    events = [_ev("garbage"), _ev(""), {"action": "x"}]
    window, history = _CloudAEScorer._split_latest_day(events)
    assert window == []
    assert history == []


# ---------------------------------------------------------------------------
# _day_of (UTC calendar day, mirrors build_cloud_dataset._day_of)
# ---------------------------------------------------------------------------

def test_day_of_normalises_timezone_to_utc():
    # 2026-01-02T01:00 at +05:00 is 2026-01-01T20:00 UTC → day is 2026-01-01.
    assert _CloudAEScorer._day_of("2026-01-02T01:00:00+05:00") == "2026-01-01"


def test_day_of_handles_z_suffix_and_naive_and_space_formats():
    assert _CloudAEScorer._day_of("2026-05-09T13:00:00Z") == "2026-05-09"
    assert _CloudAEScorer._day_of("2026-05-09T13:00:00") == "2026-05-09"
    assert _CloudAEScorer._day_of("2026-05-09 13:00:00") == "2026-05-09"


def test_day_of_rejects_malformed():
    assert _CloudAEScorer._day_of("") == ""
    assert _CloudAEScorer._day_of("not-a-date") == ""
    assert _CloudAEScorer._day_of("2026/05/09") == ""


# ---------------------------------------------------------------------------
# Train/serve parity: history now feeds new_action_count (the actual bug)
# ---------------------------------------------------------------------------

def test_history_populates_new_action_count_at_serving():
    """
    The bug (LESSONS.md rule 3): score_user passed history=None, so
    new_action_count was always 0. With the split, actions seen on prior days
    are NOT counted as new, and only genuinely-new actions on the latest day
    are counted — matching how training built each user-day.
    """
    events = [
        _ev("2026-04-01T09:00:00Z", action="GetObject"),      # history
        _ev("2026-04-01T10:00:00Z", action="ListBuckets"),    # history
        _ev("2026-04-02T09:00:00Z", action="GetObject"),      # window: seen before
        _ev("2026-04-02T10:00:00Z", action="DeleteUser"),     # window: NEW
    ]
    window, history = _CloudAEScorer._split_latest_day(events)

    with_hist = aggregate_window(window, history=history)
    # DeleteUser is the only action not present in prior history.
    assert with_hist["new_action_count"] == 1.0

    # Contrast with the old buggy call: whole set as one window, history=None
    # → new_action_count feature is skipped entirely (stays 0).
    buggy = aggregate_window(events, history=None)
    assert buggy["new_action_count"] == 0.0
