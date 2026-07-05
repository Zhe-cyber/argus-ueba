#!/usr/bin/env python3
"""
aws_live_ingest.py — Poll AWS CloudTrail LookupEvents and forward to Argus /ingest.

This is the zero-setup live path for a REAL AWS account: no S3 bucket, no SQS
queue, no trail configuration required. CloudTrail records the last 90 days of
management events in every AWS account for free, and LookupEvents reads them
with nothing but an access key.

Honest latency note
-------------------
LookupEvents visibility lag is typically ~2–15 minutes after the API call
happens (AWS does not guarantee faster). For the "<60 s console-to-dashboard"
demo, the S3 → SQS delivery path is still required (FYP2 plan item #8); this
poller is the fallback and the week-1 proof that the pipeline runs against a
real tenant.

Restart safety (W1-A scout finding, 2026-07-04)
------------------------------------------------
`/ingest` is NOT idempotent for a repeated CloudTrail eventID: backend/main.py
`ingest_event()` calls `event_store.insert_event()` unconditionally — a plain
INSERT, never an upsert — and the `events` table (backend/event_store.py) has
no eventID/event_id column or unique constraint. CloudTrail's `eventID` is
only ever carried into the JSON `metadata` blob by normalizer.py and is never
read back out for a dedup check. So re-posting the same eventID after a
poller restart creates a second row: it double-counts that event in the 24h
rolling window (Stage 4), the stored-event history the AE scorers use
(Stage 5), and `total_event_count` (used for the "new user" alert and
displayed counts).

Because of that, this poller persists a small on-disk checkpoint
(`--state-file`, default `data/aws_poller_state.json`) after every poll:
`{"window_start": <iso8601>, "seen_ids": [<eventID>, ...]}` (newest-last).
On startup it reloads the checkpoint instead of recomputing `window_start`
from `--lookback-hours`, so a restart resumes the dedup window rather than
re-fetching (and re-posting) everything already forwarded. Delete the file
(or point --state-file elsewhere) to force a fresh backfill.

Prerequisites
-------------
1. AWS account with a $1 billing alarm (P0 checklist).
2. A dedicated read-only IAM user for Argus:
     - Attach ONLY the managed policy `AWSCloudTrail_ReadOnlyAccess`
       (or an inline policy allowing just `cloudtrail:LookupEvents`).
     - Create an access key for it.
3. Credentials via any standard boto3 mechanism:
     aws configure                       (writes ~/.aws/credentials)
   or env vars:
     AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION

Usage
-----
  # Poll every 60 s, forward everything new to the local backend
  python scripts/aws_live_ingest.py

  # Faster polling, remote backend, stop after 100 events
  python scripts/aws_live_ingest.py --interval 30 --api https://my-space.hf.space --limit 100

  # First run: also backfill the last 6 hours of events
  python scripts/aws_live_ingest.py --lookback-hours 6

  # Use a custom checkpoint location (default: data/aws_poller_state.json)
  python scripts/aws_live_ingest.py --state-file /tmp/my_poller_state.json

Environment variables
---------------------
  ARGUS_API_URL  — backend URL (default: http://localhost:8001)
  AWS_*          — standard boto3 credential variables
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("Install requests first:  pip install requests")
    sys.exit(1)

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
except ImportError:
    print("Install boto3 first:  pip install boto3")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_API = os.getenv("ARGUS_API_URL", "http://localhost:8001")
DEFAULT_STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "aws_poller_state.json"

# Dedup memory cap: once we've tracked this many eventIDs, evict down to
# KEEP_IDS, dropping the OLDEST first (see PollState.remember / _evict).
MAX_SEEN_IDS = 50_000
KEEP_IDS = 25_000

SEVERITY_COLORS = {
    "Critical": "\033[91m",
    "High":     "\033[93m",
    "Medium":   "\033[33m",
    "Low":      "\033[37m",
}
RESET = "\033[0m"
BOLD  = "\033[1m"
GREEN = "\033[92m"
CYAN  = "\033[96m"


# ---------------------------------------------------------------------------
# Poller state (dedup memory + window cursor + disk checkpoint)
# ---------------------------------------------------------------------------

class PollState:
    """
    Tracks the rolling poll window and the eventID dedup memory.

    `seen` is an OrderedDict used as an ordered set (values unused) so
    eviction can drop the OLDEST inserted ids — a plain `set` has no
    insertion order, so `set(list(seen)[-25_000:])` (the original bug)
    could evict an id seen moments ago and cause a duplicate re-post.
    """

    def __init__(self, window_start: datetime) -> None:
        self.window_start = window_start
        self.seen: "OrderedDict[str, None]" = OrderedDict()

    def is_new(self, event_id: str) -> bool:
        return event_id not in self.seen

    def remember(self, event_id: str) -> None:
        """Record an eventID as posted, evicting the oldest if over cap."""
        self.seen[event_id] = None
        self.seen.move_to_end(event_id)
        if len(self.seen) > MAX_SEEN_IDS:
            self._evict_oldest()

    def _evict_oldest(self) -> None:
        """Keep only the KEEP_IDS most-recently-remembered ids."""
        n_drop = len(self.seen) - KEEP_IDS
        for _ in range(n_drop):
            self.seen.popitem(last=False)  # FIFO: drop oldest first

    # -- disk checkpoint --------------------------------------------------

    def save(self, path: Path) -> None:
        """Persist {window_start, seen_ids} so a restart can resume."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "window_start": self.window_start.isoformat(),
            "seen_ids": list(self.seen.keys()),
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load_or_new(cls, path: Path, default_window_start: datetime) -> "PollState":
        """Reload a checkpoint if present/valid; otherwise start fresh."""
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                state = cls(datetime.fromisoformat(payload["window_start"]))
                for eid in payload.get("seen_ids", []):
                    state.seen[eid] = None
                return state
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                pass  # corrupt/partial checkpoint — fall back to a fresh state
        return cls(default_window_start)


# ---------------------------------------------------------------------------
# CloudTrail polling
# ---------------------------------------------------------------------------

def fetch_events(ct_client, start_time: datetime, end_time: datetime) -> list[dict]:
    """
    Fetch CloudTrail management events in [start_time, end_time).

    Each LookupEvents record wraps the raw CloudTrail JSON in the
    'CloudTrailEvent' field as a string — that raw record is exactly the
    shape backend/normalizer.py parse_aws_cloudtrail() expects, so it is
    decoded here and posted as-is.
    """
    records: list[dict] = []
    paginator = ct_client.get_paginator("lookup_events")
    try:
        for page in paginator.paginate(
            StartTime=start_time,
            EndTime=end_time,
            PaginationConfig={"MaxItems": 500},
        ):
            for ev in page.get("Events", []):
                raw = ev.get("CloudTrailEvent")
                if not raw:
                    continue
                try:
                    records.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
    except (ClientError, BotoCoreError) as exc:
        print(f"  ! CloudTrail error: {exc}")
    return records


# ---------------------------------------------------------------------------
# Argus forwarding
# ---------------------------------------------------------------------------

def post_event(api: str, record: dict) -> tuple[int, dict]:
    """POST one raw CloudTrail record to Argus /ingest."""
    try:
        r = requests.post(
            f"{api}/ingest",
            json={"source": "aws_cloudtrail", "event": record},
            timeout=15,
        )
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text}
        return r.status_code, body
    except requests.RequestException as exc:
        return 0, {"error": str(exc)}


def describe(record: dict, result: dict) -> str:
    """One-line colourised summary of an ingested event."""
    user   = record.get("userIdentity", {}).get("userName") or \
             record.get("userIdentity", {}).get("principalId", "?")
    action = record.get("eventName", "?")
    ts     = record.get("eventTime", "")
    ae     = result.get("ae_live_score")
    ae_str = f" ae={ae:.3f}" if isinstance(ae, (int, float)) else ""
    flags  = result.get("rarity_flags") or {}
    fired  = [k for k, v in flags.items() if v]
    flag_str = f" {BOLD}[{', '.join(fired)}]{RESET}" if fired else ""
    return f"{CYAN}{ts}{RESET} {BOLD}{user}{RESET} → {action}{ae_str}{flag_str}"


# ---------------------------------------------------------------------------
# Poll-once (extracted from the main loop so tests can call it directly)
# ---------------------------------------------------------------------------

def poll_once(ct_client, api: str, state: PollState, interval: int) -> int:
    """
    Run exactly one poll cycle: fetch the current window, dedup against
    `state`, post every new event, and advance `state.window_start`.

    Returns the number of events successfully posted (status == 200) this
    cycle. Behaviour matches the original inline while-loop body exactly;
    only the "cap the dedup set" step now evicts oldest-first via
    `state.remember()` instead of an unordered `set(...)`.
    """
    window_end = datetime.now(timezone.utc)
    records = fetch_events(ct_client, state.window_start, window_end)
    # Overlap each window by one interval so LookupEvents' delivery lag
    # cannot drop events that land late; dedup handles the double-fetch.
    state.window_start = window_end - timedelta(seconds=interval * 2)

    new = [r for r in records
           if r.get("eventID") and state.is_new(r["eventID"])]

    posted = 0
    for rec in sorted(new, key=lambda r: r.get("eventTime", "")):
        state.remember(rec["eventID"])
        status, body = post_event(api, rec)
        if status == 200:
            posted += 1
            print(f"  {describe(rec, body)}")
        else:
            print(f"  ! /ingest {status}: {body}")

    if not new:
        print(f"  … no new events ({window_end:%H:%M:%S} UTC)")

    return posted


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Live-poll AWS CloudTrail into Argus")
    ap.add_argument("--api",            default=DEFAULT_API, help="Argus backend URL")
    ap.add_argument("--interval",       type=int, default=60, help="Poll interval seconds (default 60)")
    ap.add_argument("--lookback-hours", type=float, default=0.5,
                    help="How far back the first poll reaches (default 0.5 h; ignored on resume)")
    ap.add_argument("--limit",          type=int, default=0, help="Stop after N events (0 = run forever)")
    ap.add_argument("--region",         default=None, help="AWS region (default: boto3 config)")
    ap.add_argument("--state-file",     default=str(DEFAULT_STATE_FILE),
                    help="Checkpoint path for restart-safe dedup (default: data/aws_poller_state.json)")
    args = ap.parse_args()

    try:
        ct = boto3.client("cloudtrail", region_name=args.region)
        ct.lookup_events(MaxResults=1)  # credential + permission smoke test
    except NoCredentialsError:
        print("No AWS credentials found. Run `aws configure` or set AWS_ACCESS_KEY_ID / "
              "AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION.")
        sys.exit(1)
    except ClientError as exc:
        print(f"AWS rejected the request: {exc}\n"
              "Check the IAM user has cloudtrail:LookupEvents permission.")
        sys.exit(1)

    # Backend reachability check
    try:
        requests.get(args.api + "/", timeout=10)
    except requests.RequestException:
        print(f"Cannot reach Argus backend at {args.api} — is uvicorn running?")
        sys.exit(1)

    print(f"{GREEN}Polling CloudTrail every {args.interval}s → {args.api}/ingest{RESET}")
    print("LookupEvents lag is ~2–15 min; do something in the AWS console and wait.\n")

    state_path = Path(args.state_file)
    default_start = datetime.now(timezone.utc) - timedelta(hours=args.lookback_hours)
    state = PollState.load_or_new(state_path, default_start)
    total = 0

    while True:
        posted = poll_once(ct, args.api, state, args.interval)
        total += posted
        state.save(state_path)

        if args.limit and total >= args.limit:
            print(f"\n{GREEN}Done — {total} events ingested.{RESET}")
            return
        if posted == 0:
            print(f"    ({total} total so far)")
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
