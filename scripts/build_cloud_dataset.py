"""
build_cloud_dataset.py — Extract per-user daily cloud features from raw logs.

Reads the flaws.cloud AWS CloudTrail dataset (or any other source) and
produces a Parquet file of per-user per-day behavioral feature vectors,
ready for training the cloud AE.

Usage
-----
    # Build from CloudTrail .json.gz files (all 2M events)
    python scripts/build_cloud_dataset.py \
        --cloudtrail data/raw/cloudtrail/flaws_cloudtrail_logs/ \
        --out        data/processed/cloud_features.parquet

    # Quick test: limit to 50 000 events
    python scripts/build_cloud_dataset.py \
        --cloudtrail data/raw/cloudtrail/flaws_cloudtrail_logs/ \
        --out        data/processed/cloud_features.parquet \
        --limit      50000

Ground truth labels (flaws.cloud)
----------------------------------
    NORMAL users  : backup, AWSService, SecurityMokey, Root, flaws, piper, AWSAccount
    ATTACKER users: Level5, Level6   (CTF privilege-escalation players)

Output schema
-------------
    user        str    — user identifier
    date        str    — YYYY-MM-DD
    source      str    — aws_cloudtrail | azure_ad | github_events | …
    is_attacker int    — 1 for Level5/Level6, 0 otherwise
    + 12 CLOUD_FEATURES columns (float)
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure the project root is on the path
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.normalizer import parse_aws_cloudtrail
from backend.cloud_feature_extractor import CLOUD_FEATURES, aggregate_window

# ---------------------------------------------------------------------------
# Ground truth: flaws.cloud attackers
# ---------------------------------------------------------------------------
KNOWN_ATTACKERS = {"Level5", "Level6", "level5", "level6"}   # cleaned names; see _clean_user()


def _clean_user(raw_event: dict) -> str:
    """
    Extract a clean, stable user identifier from a raw CloudTrail record.

    Priority:
    1. userIdentity.userName                   (IAMUser / Root plain login)
    2. userIdentity.sessionContext.sessionIssuer.userName  (AssumedRole — gives the
       role name, not the random session ID)
    3. The session-name part of principalId    (e.g. 'secmonkey' from
       'AROAUB2AA5FQRGAHITW4A:secmonkey')
    4. userIdentity.type                       (Root, AWSService, AWSAccount, …)
    """
    ui = raw_event.get("userIdentity", {}) or {}
    # 1. Explicit user name
    if ui.get("userName"):
        return str(ui["userName"])
    # 2. AssumedRole session issuer
    issuer = (ui.get("sessionContext") or {}).get("sessionIssuer") or {}
    if issuer.get("userName"):
        return str(issuer["userName"])
    # 3. Session name from principalId  (format: ROLE_ID:session_name)
    pid = str(ui.get("principalId", ""))
    if ":" in pid:
        session_name = pid.split(":", 1)[1]
        # Filter out random-looking session names (all digits or very long UUIDs)
        if session_name and not session_name.isdigit() and len(session_name) < 40:
            return session_name
    # 4. Identity type as fallback
    return str(ui.get("type", "")) or ""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _day_of(ts: str) -> str:
    """Return YYYY-MM-DD from an ISO timestamp; empty string on failure."""
    if not ts:
        return ""
    try:
        clean = ts.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean)
        except ValueError:
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(ts, fmt)
                    break
                except ValueError:
                    continue
            else:
                return ts[:10]
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ts[:10]


def _iter_cloudtrail_gz(path: Path):
    """Yield normalised events from a single .json.gz CloudTrail file."""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            return
    records = data.get("Records", data) if isinstance(data, dict) else data
    for raw in records:
        try:
            ev = parse_aws_cloudtrail(raw)
            # Override user with our cleaner extraction (avoids random session IDs)
            ev["user"] = _clean_user(raw)
            yield ev
        except Exception:
            continue


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build(
    cloudtrail_dir: Path | None,
    out_path: Path,
    limit: int = 0,
) -> None:
    try:
        import pandas as pd
    except ImportError:
        print("[ERROR] pandas is required:  pip install pandas pyarrow")
        sys.exit(1)

    # ── Collect events: user → date → list[event] ──────────────────────────
    print("[INFO] Reading events …")
    user_day_events: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    total = 0
    skipped = 0

    sources: list[tuple[str, str]] = []   # (source_type, path)

    if cloudtrail_dir and cloudtrail_dir.exists():
        for fpath in sorted(cloudtrail_dir.glob("*.json.gz")):
            sources.append(("aws_cloudtrail", str(fpath)))

    if not sources:
        print("[ERROR] No input files found. Pass --cloudtrail <dir>")
        sys.exit(1)

    for src_type, fpath_str in sources:
        fpath = Path(fpath_str)
        print(f"  Reading {fpath.name} …", flush=True)

        if src_type == "aws_cloudtrail":
            event_iter = _iter_cloudtrail_gz(fpath)
        else:
            continue

        for ev in event_iter:
            if limit and total >= limit:
                break

            user = ev.get("user", "").strip()
            ts   = ev.get("timestamp", "")

            # Skip entries with no meaningful user identity
            if (not user
                    or user in ("?", "HIDDEN_DUE_TO_SECURITY_REASONS")
                    or user.isdigit()          # bare account IDs (811596193553)
                    or user.startswith("AIDA") # raw IAM access key IDs
                    or user.startswith("AROA") # raw role IDs without session name
               ):
                skipped += 1
                continue

            day = _day_of(ts)
            if not day:
                skipped += 1
                continue

            ev["_source"] = src_type
            user_day_events[user][day].append(ev)
            total += 1

        if limit and total >= limit:
            print(f"  [limit={limit:,} reached]")
            break

    print(f"[INFO] {total:,} events for {len(user_day_events)} users ({skipped:,} skipped)")

    # ── Build per-user per-day feature vectors ─────────────────────────────
    print("[INFO] Aggregating features …")
    rows: list[dict] = []

    for user, day_map in sorted(user_day_events.items()):
        # Build full history for new_action_count tracking
        # Sort days chronologically
        sorted_days = sorted(day_map.keys())
        prior_events: list[dict] = []

        for day in sorted_days:
            events = day_map[day]
            source = events[0].get("_source", "aws_cloudtrail") if events else "aws_cloudtrail"

            feats = aggregate_window(events, history=prior_events)

            row = {
                "user":        user,
                "date":        day,
                "source":      source,
                "is_attacker": int(user in KNOWN_ATTACKERS),
            }
            row.update(feats)
            rows.append(row)

            # Accumulate history
            prior_events.extend(events)

    if not rows:
        print("[ERROR] No rows generated — check input files.")
        sys.exit(1)

    df = pd.DataFrame(rows, columns=["user", "date", "source", "is_attacker"] + CLOUD_FEATURES)

    # Ensure all feature columns are float
    for col in CLOUD_FEATURES:
        df[col] = df[col].fillna(0.0).astype(float)

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n[INFO] Dataset summary:")
    print(f"  Rows (user-days): {len(df):,}")
    print(f"  Users:            {df['user'].nunique()}")
    print(f"  Date range:       {df['date'].min()} to {df['date'].max()}")
    print(f"  Attacker rows:    {df['is_attacker'].sum():,} ({df['is_attacker'].mean()*100:.1f}%)")
    print(f"\n  User breakdown:")
    for user, grp in df.groupby("user"):
        label = "ATTACKER" if grp['is_attacker'].iloc[0] else "normal  "
        print(f"    [{label}] {user:<40} {len(grp):>5} days  "
              f"avg_events={grp['event_count'].mean():.0f}")

    print(f"\n  Feature means (all users):")
    for col in CLOUD_FEATURES:
        print(f"    {col:<22} mean={df[col].mean():.2f}  max={df[col].max():.0f}")

    # ── Save ───────────────────────────────────────────────────────────────
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(out_path), index=False)
    print(f"\n[SAVED] {out_path.resolve()}")
    print(f"        {len(df):,} rows × {len(df.columns)} columns")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cloudtrail", default=None,
                   help="Directory containing .json.gz CloudTrail files")
    p.add_argument("--out", default="data/processed/cloud_features.parquet",
                   help="Output Parquet file path")
    p.add_argument("--limit", type=int, default=0,
                   help="Stop after N events (0 = all)")
    return p.parse_args()


if __name__ == "__main__":
    args = _args()
    build(
        cloudtrail_dir=Path(args.cloudtrail) if args.cloudtrail else None,
        out_path=Path(args.out),
        limit=args.limit,
    )
