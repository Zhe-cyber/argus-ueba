"""
ingest_cloudtrail.py — Batch-ingest an AWS CloudTrail dataset through the UEBA pipeline.

Supports the Kaggle dataset:
    https://www.kaggle.com/datasets/nobukim/aws-cloudtrails-dataset-from-flaws-cloud

Usage
-----
1. Download the Kaggle dataset and unzip it somewhere, e.g.:
       data/raw/cloudtrail/

2. Run this script (backend must be running on port 8001):
       python scripts/ingest_cloudtrail.py --path data/raw/cloudtrail/

3. The script walks the directory for .json / .csv files and POSTs each
   CloudTrail record to POST /ingest.  Progress and summary stats are printed.

Options
-------
  --path      Directory or single file to ingest  (required)
  --api       Base URL of the UEBA API             (default: http://localhost:8001)
  --user      Override user field for all events   (optional)
  --limit     Stop after N events                  (default: unlimited)
  --dry-run   Parse and print events without posting

Supported input formats
-----------------------
  JSON  — standard CloudTrail log file ({"Records": [...]} wrapper or bare list)
  CSV   — tabular export with columns: eventTime, userIdentity.userName,
          eventName, eventSource, sourceIPAddress, (etc.)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Generator, Iterator

# ---------------------------------------------------------------------------
# HTTP — use requests if available, fall back to urllib
# ---------------------------------------------------------------------------
try:
    import requests as _req

    def _post(url: str, payload: dict) -> tuple[int, dict]:
        r = _req.post(url, json=payload, timeout=15)
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text}
        return r.status_code, body

except ImportError:
    import urllib.request
    import urllib.error

    def _post(url: str, payload: dict) -> tuple[int, dict]:    # type: ignore[misc]
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read())
            except Exception:
                body = {"error": str(exc)}
            return exc.code, body


# ---------------------------------------------------------------------------
# CloudTrail JSON parsing
# ---------------------------------------------------------------------------

def _iter_json_file(path: Path) -> Generator[dict, None, None]:
    """
    Yield individual CloudTrail event records from a JSON file.

    Handles:
     - Standard CloudTrail log format: {"Records": [...]}
     - Bare list of records: [...]
     - NDJSON (one record per line)
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = raw.strip()

    # Try structured JSON first
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "Records" in obj:
            for rec in obj["Records"]:
                yield rec
            return
        if isinstance(obj, list):
            for rec in obj:
                yield rec
            return
    except json.JSONDecodeError:
        pass

    # Fall back to NDJSON (one JSON object per line)
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _iter_csv_file(path: Path) -> Generator[dict, None, None]:
    """
    Yield CloudTrail-like dicts from a CSV export.

    Common column names from the Kaggle flaws.cloud dataset and AWS Console export:
        eventTime / EventTime / event_time
        userIdentity / userIdentity.userName / userName / user
        eventName / EventName / event_name / action
        eventSource / EventSource / event_source / service
        sourceIPAddress / SourceIPAddress / ip / source_ip
    """
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalise column names to lowercase for matching
            norm = {k.lower().replace(" ", "_").replace(".", "_"): v
                    for k, v in row.items()}

            def _get(*keys: str, default: str = "") -> str:
                for k in keys:
                    if norm.get(k):
                        return str(norm[k]).strip()
                return default

            event_time  = _get("eventtime", "event_time", "time", "timestamp")
            user_name   = _get(
                "useridentity_username", "username", "user",
                "useridentity", "principal", "account",
            )
            event_name  = _get("eventname", "event_name", "action", "operation")
            event_source = _get("eventsource", "event_source", "service", "source")
            source_ip   = _get("sourceipaddress", "source_ip", "ip", "remoteip")
            region      = _get("awsregion", "region", default="us-east-1")
            account_id  = _get("recipientaccountid", "accountid", "account_id")

            # Skip header-like or empty rows
            if not event_time or not event_name:
                continue

            yield {
                "eventTime":    event_time,
                "eventName":    event_name,
                "eventSource":  event_source,
                "sourceIPAddress": source_ip,
                "awsRegion":    region,
                "userIdentity": {
                    "type":      "IAMUser",
                    "userName":  user_name or "unknown",
                    "accountId": account_id,
                },
                "requestParameters": {},
                "responseElements":  {},
                "_csv_row": norm,   # keep original for debugging
            }


def _iter_gz_json(path: Path) -> Generator[dict, None, None]:
    """
    Stream records from a .json.gz file using ijson for true streaming (if
    available), otherwise falling back to full-load parsing.

    Handles the standard CloudTrail {"Records": [...]} envelope.
    """
    import gzip

    # ---- Try ijson streaming first (fast, low-memory, early-exit friendly) ----
    try:
        import ijson  # type: ignore
        with gzip.open(path, "rb") as fh:
            # Try {"Records": [...]} envelope
            try:
                for rec in ijson.items(fh, "Records.item"):
                    yield rec
                return
            except Exception:
                pass
        # Fallback: try bare list
        with gzip.open(path, "rb") as fh:
            try:
                for rec in ijson.items(fh, "item"):
                    yield rec
                return
            except Exception:
                pass
    except ImportError:
        pass

    # ---- Full-load fallback (original behaviour) ----
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        content = fh.read()

    try:
        obj = json.loads(content)
        if isinstance(obj, dict) and "Records" in obj:
            for rec in obj["Records"]:
                yield rec
            return
        if isinstance(obj, list):
            for rec in obj:
                yield rec
            return
    except (json.JSONDecodeError, MemoryError):
        pass

    # Fallback: NDJSON (one JSON object per line)
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _iter_file(path: Path) -> Iterator[dict]:
    suffix = path.suffix.lower()
    if suffix == ".gz":
        yield from _iter_gz_json(path)
    elif suffix in (".json", ".jsonl", ".ndjson"):
        yield from _iter_json_file(path)
    elif suffix == ".csv":
        yield from _iter_csv_file(path)
    else:
        # Try JSON first, then CSV
        try:
            yield from _iter_json_file(path)
        except Exception:
            yield from _iter_csv_file(path)


def _collect_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    files = []
    for ext in ("*.json", "*.jsonl", "*.ndjson", "*.csv", "*.gz"):
        files.extend(sorted(path.rglob(ext)))
    return files


# ---------------------------------------------------------------------------
# Main ingestion loop
# ---------------------------------------------------------------------------

def ingest(
    path:          Path,
    api_url:       str       = "http://localhost:8001",
    user_override: str | None = None,
    limit:         int       = 0,
    dry_run:       bool      = False,
    workers:       int       = 8,
) -> None:
    ingest_url = f"{api_url.rstrip('/')}/ingest"
    files      = _collect_files(path)

    if not files:
        print(f"[error] No .json / .csv files found under {path}")
        sys.exit(1)

    print(f"Found {len(files)} file(s) to ingest from {path}")
    print(f"API:  {ingest_url}  (workers={workers})")
    if dry_run:
        print("[DRY RUN — no HTTP requests will be sent]")
    print()

    total        = 0
    ok_count     = 0
    err_count    = 0
    users_seen:   set[str]       = set()
    sources_seen: dict[str, int] = {}
    t_start      = time.time()

    def _apply_override(raw_event: dict) -> dict:
        if not user_override:
            return raw_event
        raw_event = dict(raw_event)
        if "userIdentity" in raw_event and isinstance(raw_event["userIdentity"], dict):
            raw_event["userIdentity"]["userName"] = user_override
        else:
            raw_event["user"] = user_override
        return raw_event

    def _send(raw_event: dict) -> tuple[int, dict]:
        payload = {"event": raw_event, "source": "aws_cloudtrail"}
        return _post(ingest_url, payload)

    for fpath in files:
        print(f"  Ingesting {fpath.name} …", flush=True)
        file_count = 0

        # Collect up to (limit - total) events from this file
        batch: list[dict] = []
        for raw_event in _iter_file(fpath):
            if limit and (total + len(batch)) >= limit:
                break
            batch.append(_apply_override(raw_event))

        if dry_run:
            for i, raw_event in enumerate(batch[:3]):
                _user = (
                    raw_event.get("userIdentity", {}).get("userName")
                    or raw_event.get("user", "?")
                )
                print(f"    event[{total+i}]: "
                      f"time={raw_event.get('eventTime','?')} "
                      f"user={_user} "
                      f"action={raw_event.get('eventName','?')} "
                      f"source={raw_event.get('eventSource','?')}")
            ok_count   += len(batch)
            total      += len(batch)
            file_count += len(batch)
            print(f"    → {file_count} events (dry-run)")
        else:
            # POST concurrently with a thread pool
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_send, ev): ev for ev in batch}
                done_count = 0
                for fut in as_completed(futures):
                    done_count += 1
                    file_count += 1
                    total      += 1
                    # Print progress every 50 events
                    if done_count % 50 == 0 or done_count == len(batch):
                        elapsed_so_far = time.time() - t_start
                        rate = total / elapsed_so_far if elapsed_so_far > 0 else 0
                        print(f"    {done_count}/{len(batch)}  "
                              f"[{total} total | {rate:.1f} ev/s]", flush=True)
                    try:
                        status, body = fut.result()
                    except Exception as exc:
                        err_count += 1
                        if err_count <= 3:
                            print(f"\n    [warn] request failed: {exc}")
                        continue

                    if 200 <= status < 300:
                        ok_count += 1
                        uid = body.get("user", "?")
                        src = body.get("source", "?")
                        users_seen.add(uid)
                        sources_seen[src] = sources_seen.get(src, 0) + 1
                    else:
                        err_count += 1
                        detail = body.get("detail", body)
                        if err_count <= 3:
                            print(f"\n    [warn] HTTP {status}: {str(detail)[:120]}")

        if limit and total >= limit:
            print(f"[info] Limit of {limit} events reached — stopping.")
            break

    elapsed = time.time() - t_start
    print()
    print("=" * 60)
    print(f"  Ingestion complete in {elapsed:.1f}s")
    print(f"  Total events : {total:,}")
    print(f"  Accepted     : {ok_count:,}")
    print(f"  Errors       : {err_count:,}")
    if not dry_run:
        print(f"  Unique users : {len(users_seen)}")
        if sources_seen:
            for src, cnt in sorted(sources_seen.items(), key=lambda x: -x[1]):
                print(f"    {src}: {cnt:,}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--path", required=True,
        help="Directory or file containing CloudTrail JSON/CSV",
    )
    p.add_argument(
        "--api", default=os.environ.get("UEBA_API_URL", "http://localhost:8001"),
        help="UEBA API base URL (default: http://localhost:8001)",
    )
    p.add_argument(
        "--user", default=None,
        help="Override user ID for all events (e.g. 'ACM2278' to test against CERT user)",
    )
    p.add_argument(
        "--limit", type=int, default=0,
        help="Stop after N events (0 = no limit)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Parse files and print first few events without calling the API",
    )
    p.add_argument(
        "--workers", type=int, default=8,
        help="Concurrent POST workers (default: 8)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ingest(
        path=Path(args.path),
        api_url=args.api,
        user_override=args.user,
        limit=args.limit,
        dry_run=args.dry_run,
        workers=args.workers,
    )
