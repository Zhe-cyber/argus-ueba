#!/usr/bin/env python3
"""
github_live_ingest.py — Poll GitHub Events API and forward them to Argus /ingest.

This gives the platform genuine real-time event ingestion with no cloud account
required. The GitHub Events API is completely free:
  - Unauthenticated: 60 req/hour (enough for demos)
  - With a free token: 5 000 req/hour (set GITHUB_TOKEN env var)

Usage
-----
  # Watch all public GitHub events (global feed)
  python scripts/github_live_ingest.py

  # Watch a specific user's events (higher signal density)
  python scripts/github_live_ingest.py --user torvalds

  # Watch events for a GitHub organisation
  python scripts/github_live_ingest.py --org python

  # Faster polling, specific backend URL
  python scripts/github_live_ingest.py --user alice --interval 10 --api http://localhost:8000

  # Limit to N events then stop (useful for demos)
  python scripts/github_live_ingest.py --limit 50

Environment variables
---------------------
  GITHUB_TOKEN   — Personal Access Token for higher rate limit (optional)
  ARGUS_API_URL  — Override backend URL (default: http://localhost:8000)

What it does
------------
1. Polls GitHub Events API every --interval seconds
2. Sends each unseen event to POST /ingest with source=github_events
3. Prints each ingested event + any alerts that fired
4. Tracks seen event IDs so no event is ingested twice
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("Install requests first:  pip install requests")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GITHUB_API  = "https://api.github.com"
DEFAULT_API = os.getenv("ARGUS_API_URL", "http://localhost:8000")
TOKEN       = os.getenv("GITHUB_TOKEN", "")

SEVERITY_COLORS = {
    "Critical": "\033[91m",  # bright red
    "High":     "\033[93m",  # yellow
    "Medium":   "\033[33m",  # dark yellow
    "Low":      "\033[37m",  # light grey
}
RESET = "\033[0m"
BOLD  = "\033[1m"
GREEN = "\033[92m"
CYAN  = "\033[96m"


# ---------------------------------------------------------------------------
# GitHub polling
# ---------------------------------------------------------------------------

def gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def fetch_events(user: str | None, org: str | None) -> list[dict]:
    if user:
        url = f"{GITHUB_API}/users/{user}/events"
    elif org:
        url = f"{GITHUB_API}/orgs/{org}/events"
    else:
        url = f"{GITHUB_API}/events"

    try:
        r = requests.get(url, headers=gh_headers(), timeout=10)
        if r.status_code == 403:
            reset = int(r.headers.get("X-RateLimit-Reset", 0))
            wait  = max(0, reset - int(time.time())) + 5
            print(f"⚠  Rate limited — sleeping {wait}s")
            time.sleep(wait)
            return []
        r.raise_for_status()
        return r.json() or []
    except requests.RequestException as e:
        print(f"GitHub fetch error: {e}")
        return []


# ---------------------------------------------------------------------------
# Argus ingest
# ---------------------------------------------------------------------------

def ingest(event: dict, api_url: str) -> dict | None:
    try:
        r = requests.post(
            f"{api_url}/ingest",
            json={"event": event, "source": "github_events"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"  Ingest error: {e}")
        return None


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Forward GitHub Events to Argus in real time")
    ap.add_argument("--user",     default=None, help="GitHub username to watch")
    ap.add_argument("--org",      default=None, help="GitHub organisation to watch")
    ap.add_argument("--interval", default=30,   type=int, help="Poll interval in seconds (default: 30)")
    ap.add_argument("--api",      default=DEFAULT_API, help="Argus backend URL")
    ap.add_argument("--limit",    default=0,    type=int, help="Stop after N ingested events (0 = unlimited)")
    args = ap.parse_args()

    target = args.user or args.org or "(public feed)"
    print(f"\n{BOLD}Argus GitHub Live Ingest{RESET}")
    print(f"  Watching : {CYAN}{target}{RESET}")
    print(f"  Backend  : {CYAN}{args.api}{RESET}")
    print(f"  Interval : {args.interval}s")
    print(f"  Auth     : {'token set ✓' if TOKEN else 'no token (60 req/h)'}")
    if args.limit:
        print(f"  Limit    : {args.limit} events")
    print()

    seen_ids:    set[str] = set()
    total_ingested = 0

    while True:
        events = fetch_events(args.user, args.org)

        new_events = [e for e in events if str(e.get("id", "")) not in seen_ids]
        # Process oldest first so the timeline is chronological
        new_events.sort(key=lambda e: e.get("created_at", ""))

        for ev in new_events:
            ev_id   = str(ev.get("id", ""))
            ev_type = ev.get("type", "")
            actor   = (ev.get("actor") or {}).get("login", "?")
            repo    = (ev.get("repo")  or {}).get("name",  "?")
            ts      = ev.get("created_at", "")

            seen_ids.add(ev_id)

            result = ingest(ev, args.api)
            if result is None:
                continue

            total_ingested += 1
            ts_fmt = ts[:19].replace("T", " ") + "Z"
            print(
                f"{GREEN}✓{RESET} [{ts_fmt}]  "
                f"{CYAN}{actor:<20}{RESET}  "
                f"{ev_type:<28}  "
                f"{repo}"
            )

            # Print any alerts that fired
            live = result.get("live_score", 0)
            ae   = result.get("ae_live_score")
            rar  = result.get("rarity_score", 0)
            flags_on = [k for k, v in (result.get("rarity_flags") or {}).items() if v]

            if rar >= 0.4 or (ae and ae >= 0.5):
                scores = f"  → rule={live:.3f}"
                if ae:
                    scores += f"  ae={ae:.3f}"
                scores += f"  rarity={rar:.0%}"
                if flags_on:
                    scores += f"  [{', '.join(flags_on)}]"
                print(f"  {BOLD}⚡ Anomaly signals{RESET}{scores}")

            if args.limit and total_ingested >= args.limit:
                print(f"\n✓ Reached limit of {args.limit} events. Done.")
                return

        if new_events:
            print(f"  ({len(new_events)} new · {total_ingested} total · next poll in {args.interval}s)")
        else:
            now = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(f"  [{now}] No new events · sleeping {args.interval}s …", end="\r")

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped.")
