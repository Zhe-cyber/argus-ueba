"""
test_aws_live_ingest.py — pytest suite for scripts/aws_live_ingest.py.

Strategy
--------
Everything that would touch the network is mocked with unittest.mock:
  - boto3's CloudTrail paginator is faked (fetch_events is exercised against
    a fake paginator object, never a real ct_client).
  - post_event / requests.post is monkeypatched so no HTTP call is made and
    no real Argus backend (or its SQLite events.db — LESSONS rule 10) is
    ever touched.

Run:
    $env:DATABASE_URL="sqlite-local"
    pytest scripts/tests -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import aws_live_ingest as poller


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ct_event(event_id: str, event_time: str = "2026-07-04T00:00:00Z", **extra) -> dict:
    """Build one raw CloudTrail JSON record (the string inside CloudTrailEvent)."""
    body = {"eventID": event_id, "eventTime": event_time, "eventName": "ConsoleLogin",
             "userIdentity": {"userName": "alice"}}
    body.update(extra)
    return body


def _fake_paginator(pages: list[list[dict]]):
    """
    Build a fake boto3 CloudTrail client whose get_paginator("lookup_events")
    .paginate(...) yields the given pages. Each page is a list of raw dicts
    (already the "record" shape); this helper wraps them in the
    {"Events": [{"CloudTrailEvent": "<json>", ...}]} envelope LookupEvents
    actually returns.
    """
    ct = MagicMock()
    paginator = MagicMock()

    def _paginate(**kwargs):
        for page_records in pages:
            events = []
            for rec in page_records:
                if rec is None:
                    # malformed: no CloudTrailEvent key at all
                    events.append({"eventID": "malformed"})
                elif rec == "BAD_JSON":
                    events.append({"CloudTrailEvent": "{not json"})
                else:
                    events.append({"CloudTrailEvent": json.dumps(rec)})
            yield {"Events": events}

    paginator.paginate.side_effect = _paginate
    ct.get_paginator.return_value = paginator
    return ct


# ---------------------------------------------------------------------------
# fetch_events: malformed records
# ---------------------------------------------------------------------------

def test_fetch_events_skips_malformed_records():
    """A missing CloudTrailEvent key or invalid JSON string must be skipped,
    not raise, and must not appear in the returned records."""
    ct = _fake_paginator([[
        _ct_event("good-1"),
        None,            # missing CloudTrailEvent
        "BAD_JSON",      # invalid JSON string
        _ct_event("good-2"),
    ]])
    start = datetime.now(timezone.utc) - timedelta(minutes=5)
    end = datetime.now(timezone.utc)

    records = poller.fetch_events(ct, start, end)

    ids = sorted(r["eventID"] for r in records)
    assert ids == ["good-1", "good-2"]


# ---------------------------------------------------------------------------
# poll_once: dedup across overlapping windows
# ---------------------------------------------------------------------------

def test_poll_once_dedups_overlapping_windows(monkeypatch):
    """Two consecutive poll_once calls whose CloudTrail windows overlap and
    return the same eventID must post that eventID exactly once."""
    posted_ids: list[str] = []

    def fake_post_event(api, record):
        posted_ids.append(record["eventID"])
        return 200, {"ae_live_score": 0.1, "rarity_flags": {}}

    monkeypatch.setattr(poller, "post_event", fake_post_event)

    shared = _ct_event("dup-1")
    ct_page1 = _fake_paginator([[shared, _ct_event("only-in-1")]])
    ct_page2 = _fake_paginator([[shared, _ct_event("only-in-2")]])

    state = poller.PollState(datetime.now(timezone.utc) - timedelta(minutes=5))

    n1 = poller.poll_once(ct_page1, "http://fake", state, interval=30)
    n2 = poller.poll_once(ct_page2, "http://fake", state, interval=30)

    assert n1 == 2
    assert n2 == 1  # only-in-2 is new; dup-1 must be skipped the second time
    assert sorted(posted_ids) == sorted(["dup-1", "only-in-1", "only-in-2"])
    assert posted_ids.count("dup-1") == 1


# ---------------------------------------------------------------------------
# Eviction: retains the NEWEST ids, drops the oldest
# ---------------------------------------------------------------------------

def test_eviction_retains_newest_ids():
    """When the dedup memory exceeds MAX_SEEN_IDS, remember() must evict the
    OLDEST ids first and keep the most-recently-seen KEEP_IDS ids — a plain
    set() has no order and could evict an arbitrary (possibly just-seen) id."""
    state = poller.PollState(datetime.now(timezone.utc))

    # Use small caps so the test runs fast and deterministically.
    monkeypatch_max = poller.MAX_SEEN_IDS
    monkeypatch_keep = poller.KEEP_IDS
    poller.MAX_SEEN_IDS = 10
    poller.KEEP_IDS = 5
    try:
        for i in range(12):
            state.remember(f"id-{i}")

        remaining = list(state.seen.keys())
        # Eviction fires once len > MAX_SEEN_IDS (10), trimming down to
        # KEEP_IDS (5) oldest-first; the loop continues past that point
        # (id-11) without triggering a second eviction. Whatever the exact
        # cutoff, the surviving ids must (a) be a contiguous suffix — i.e.
        # in insertion order with none re-ordered — and (b) always include
        # the most recently inserted id and exclude the very first ones.
        assert remaining == sorted(remaining, key=lambda x: int(x.split("-")[1]))
        assert remaining[-1] == "id-11"          # newest always retained
        assert "id-0" not in state.seen           # oldest always evicted
        assert "id-1" not in state.seen
        assert len(state.seen) <= poller.MAX_SEEN_IDS
    finally:
        poller.MAX_SEEN_IDS = monkeypatch_max
        poller.KEEP_IDS = monkeypatch_keep


# ---------------------------------------------------------------------------
# post_event: non-200 and network-error branches
# ---------------------------------------------------------------------------

def test_post_event_non_200(monkeypatch):
    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.json.side_effect = ValueError("no json")
    fake_response.text = "Internal Server Error"

    monkeypatch.setattr(poller.requests, "post", MagicMock(return_value=fake_response))

    status, body = poller.post_event("http://fake", _ct_event("x"))

    assert status == 500
    assert body == {"raw": "Internal Server Error"}


def test_post_event_network_error(monkeypatch):
    import requests as real_requests

    def raise_conn_error(*a, **kw):
        raise real_requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(poller.requests, "post", raise_conn_error)

    status, body = poller.post_event("http://fake", _ct_event("x"))

    assert status == 0
    assert "boom" in body["error"]


def test_poll_once_handles_non_200_and_network_error(monkeypatch):
    """poll_once must not raise when post_event reports a failure; it should
    just not count that event as posted."""
    call_count = {"n": 0}

    def flaky_post(api, record):
        call_count["n"] += 1
        if record["eventID"] == "fails-http":
            return 503, {"error": "unavailable"}
        if record["eventID"] == "fails-network":
            return 0, {"error": "connection refused"}
        return 200, {}

    monkeypatch.setattr(poller, "post_event", flaky_post)

    ct = _fake_paginator([[
        _ct_event("fails-http"),
        _ct_event("fails-network"),
        _ct_event("succeeds"),
    ]])
    state = poller.PollState(datetime.now(timezone.utc) - timedelta(minutes=5))

    posted = poller.poll_once(ct, "http://fake", state, interval=30)

    assert posted == 1
    assert call_count["n"] == 3
    # All three eventIDs should still be marked "seen" (we attempted to post them)
    assert set(state.seen.keys()) == {"fails-http", "fails-network", "succeeds"}


# ---------------------------------------------------------------------------
# Checkpoint: restart reloads state and does not re-post
# ---------------------------------------------------------------------------

def test_checkpoint_restart_does_not_repost(tmp_path, monkeypatch):
    """Simulates a full restart: save() a state to disk, then load_or_new()
    a fresh PollState from that file and confirm a previously-seen eventID
    is NOT re-posted."""
    state_file = tmp_path / "poller_state.json"

    posted_ids: list[str] = []

    def fake_post_event(api, record):
        posted_ids.append(record["eventID"])
        return 200, {}

    monkeypatch.setattr(poller, "post_event", fake_post_event)

    # --- "process 1": poll once, then persist a checkpoint ---
    window_start = datetime.now(timezone.utc) - timedelta(minutes=10)
    state1 = poller.PollState(window_start)
    ct1 = _fake_paginator([[_ct_event("persisted-1")]])
    poller.poll_once(ct1, "http://fake", state1, interval=30)
    state1.save(state_file)

    assert posted_ids == ["persisted-1"]
    assert state_file.exists()

    # --- "process 2": restart, reload the checkpoint ---
    state2 = poller.PollState.load_or_new(state_file, default_window_start=datetime.now(timezone.utc))
    assert "persisted-1" in state2.seen
    assert state2.window_start == state1.window_start

    # Same eventID appears again in the next fetched window (e.g. overlap
    # replay) — it must be recognised as already-seen and not re-posted.
    ct2 = _fake_paginator([[_ct_event("persisted-1"), _ct_event("new-2")]])
    poller.poll_once(ct2, "http://fake", state2, interval=30)

    assert posted_ids == ["persisted-1", "new-2"]


def test_load_or_new_falls_back_on_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    default_start = datetime.now(timezone.utc)

    state = poller.PollState.load_or_new(missing, default_start)

    assert state.window_start == default_start
    assert len(state.seen) == 0


def test_load_or_new_falls_back_on_corrupt_file(tmp_path):
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not valid json", encoding="utf-8")
    default_start = datetime.now(timezone.utc)

    state = poller.PollState.load_or_new(corrupt, default_start)

    assert state.window_start == default_start
    assert len(state.seen) == 0


# ---------------------------------------------------------------------------
# argparse smoke test
# ---------------------------------------------------------------------------

def test_help_flag_exits_cleanly():
    """`--help` must still print usage and exit 0 (argparse intact)."""
    import subprocess
    import sys as _sys

    result = subprocess.run(
        [_sys.executable, str(Path(poller.__file__)), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--state-file" in result.stdout
