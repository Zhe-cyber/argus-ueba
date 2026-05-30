"""
seed_demo.py — Workstream C: a reproducible live-detection demo.

Drives the REAL /ingest pipeline to produce a repeatable on-stage story:

  1. A benign user — a handful of business-hours logins from one known IP/country.
     → flat AE score, no rarity flags, no alert.
  2. An insider — normal baseline, then an off-hours burst from a new country to a
     sensitive resource.
     → AE/rule score climbs, multiple rarity flags fire (off_hours, new_ip,
       geo_rarity, sensitive_resource, high_volume), an alert auto-fires.

Each run uses a unique id suffix on the usernames so the demo always starts from a
clean history (first_time_action / new_ip / geo_rarity behave fresh every run).

Usage
-----
    # backend must be running, e.g.:
    #   DATABASE_URL="" python -m uvicorn backend.main:app --port 8077
    python scripts/seed_demo.py --api http://127.0.0.1:8077
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone


def _post(api: str, source: str, event: dict) -> dict:
    body = json.dumps({"source": source, "event": event}).encode()
    req = urllib.request.Request(f"{api}/ingest", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _get(api: str, path: str) -> dict:
    with urllib.request.urlopen(f"{api}{path}", timeout=30) as r:
        return json.loads(r.read())


def cf_event(user: str, when: datetime, ip: str, country: str,
             app: str, allowed: bool = True, action: str = "login") -> dict:
    return {
        "action": action, "allowed": allowed,
        "app_domain": app, "app_uid": str(uuid.uuid4())[:8],
        "created_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user_email": user, "ip_address": ip, "country": country,
        "ray_id": str(uuid.uuid4())[:12],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8077")
    ap.add_argument("--burst", type=int, default=55, help="insider off-hours burst size (>50 → high_volume)")
    args = ap.parse_args()

    rid = uuid.uuid4().hex[:6]
    benign = f"alice.normal.{rid}@corp.com"
    insider = f"mallory.insider.{rid}@corp.com"

    # Business-hours weekday baseline (UTC 14:00 Tue) and off-hours (UTC 02:34 Sat).
    biz = datetime(2026, 5, 26, 14, 0, tzinfo=timezone.utc)        # Tue 14:00
    off = datetime(2026, 5, 30, 2, 34, tzinfo=timezone.utc)        # Sat 02:34

    print(f"\n=== DEMO run {rid} ===")
    print(f"benign  : {benign}")
    print(f"insider : {insider}\n")

    # ---- 1. Benign user: 5 normal logins, one IP/country -------------------
    print("[1] Benign user — 5 business-hours logins from 1.2.3.4 (US)…")
    for i in range(5):
        _post(args.api, "cloudflare_access",
              cf_event(benign, biz + timedelta(minutes=3 * i), "1.2.3.4", "US",
                       "intranet.corp.com"))
    b = _get(args.api, f"/users/{benign}/live-score")
    print(f"    live-score: ae_live={b['ae_live']}, rarity={b['rarity']}, "
          f"events={b['event_count']}\n")

    # ---- 2. Insider: baseline, then off-hours burst ------------------------
    print("[2] Insider — 3 normal baseline logins from 1.2.3.4 (US)…")
    for i in range(3):
        _post(args.api, "cloudflare_access",
              cf_event(insider, biz + timedelta(minutes=5 * i), "1.2.3.4", "US",
                       "intranet.corp.com"))

    print(f"[3] Insider — off-hours burst of {args.burst} events from 9.9.9.9 (RU) "
          f"hitting a sensitive resource…")
    # Track the PEAK-rarity event during the burst. new_ip / geo_rarity are
    # first-occurrence flags: they fire on the FIRST event from 9.9.9.9/RU and
    # then go quiet once that IP/country is known. Printing the last event would
    # understate what happened, so we surface the moment the most signals fired.
    last = None
    peak = None
    peak_n = -1
    for i in range(args.burst):
        last = _post(args.api, "cloudflare_access",
                     cf_event(insider, off + timedelta(seconds=20 * i),
                              "9.9.9.9", "RU", "vpn-admin-secrets.corp.com",
                              action="download"))
        n_fired = sum((last.get("rarity_flags") or {}).values())
        if n_fired > peak_n:
            peak_n, peak = n_fired, last

    print("\n--- peak insider event: rarity flags (most signals fired) ---")
    flags = peak.get("rarity_flags", {})
    for k, v in flags.items():
        mark = "🔴 FIRED" if v else "·  ok  "
        print(f"    {mark}  {k}")
    print(f"    rarity_score = {peak.get('rarity_score')}  "
          f"({sum(flags.values())}/{len(flags)} signals)")
    print(f"    ae_live_score = {peak.get('ae_live_score')}  "
          f"rule_live = {peak.get('live_score')}")

    ins = _get(args.api, f"/users/{insider}/live-score")
    print(f"\n--- persisted live-score (insider) ---")
    print(f"    ae_live={ins['ae_live']}, rule_live={ins['rule_live']}, "
          f"rarity={ins['rarity']}, events={ins['event_count']}")

    # ---- 3. Show the auto-created alerts -----------------------------------
    try:
        alerts = _get(args.api, "/alerts?status=Open")
        mine = [a for a in alerts if insider.split("@")[0] in json.dumps(a)]
        print(f"\n--- alerts auto-created for insider: {len(mine)} ---")
        for a in mine[:5]:
            print(f"    [{a.get('severity')}] {a.get('title')}")
    except Exception as exc:
        print(f"    (could not fetch alerts: {exc})")

    print(f"\n=== demo complete — open the dashboard at /users/{insider} ===\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
