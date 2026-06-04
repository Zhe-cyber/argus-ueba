#!/usr/bin/env python3
"""
ingest_datasets.py — Batch-ingest the downloaded REAL Azure / GitHub datasets
through the Argus /ingest pipeline.

Real data provenance
--------------------
  Azure : Splunk attack_data (real Azure AD SignInLogs / AuditLogs, Apache-2.0)
          + SimuLand Microsoft Sentinel samples  → data/raw/azure_ad/**
  GitHub: GitHub public Events API (real live activity)  → data/raw/github/*.json

Usage
-----
  # against the live HF Space
  python scripts/ingest_datasets.py --source github --api https://zhe-cyber-argus-ueba.hf.space --limit 40
  python scripts/ingest_datasets.py --source azure  --api https://zhe-cyber-argus-ueba.hf.space

  # against a local backend
  python scripts/ingest_datasets.py --source both --api http://127.0.0.1:8001
"""
from __future__ import annotations
import argparse, glob, json, sys, time
from pathlib import Path

try:
    import requests
    def post(url, payload, timeout=30):
        r = requests.post(url, json=payload, timeout=timeout)
        return r.status_code, (r.json() if r.ok else {})
except ImportError:
    import urllib.request, urllib.error
    def post(url, payload, timeout=30):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, {}

ROOT = Path(__file__).resolve().parent.parent


def _read_records(path: Path) -> list[dict]:
    """Read either a JSON array or newline-delimited JSON file."""
    txt = path.read_text(encoding="utf-8", errors="replace").strip()
    if not txt:
        return []
    try:
        obj = json.loads(txt)
        return obj if isinstance(obj, list) else [obj]
    except json.JSONDecodeError:
        out = []
        for line in txt.splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return out


def collect(source: str) -> list[tuple[str, dict]]:
    """Return (source_tag, raw_event) tuples for the requested dataset."""
    items: list[tuple[str, dict]] = []
    if source in ("github", "both"):
        for f in sorted(glob.glob(str(ROOT / "data/raw/github/*.json"))):
            for ev in _read_records(Path(f)):
                items.append(("github_events", ev))
    if source in ("azure", "both"):
        for f in sorted(glob.glob(str(ROOT / "data/raw/azure_ad/**/*.json"), recursive=True)):
            for ev in _read_records(Path(f)):
                items.append(("azure_ad", ev))
    return items


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["github", "azure", "both"], default="both")
    ap.add_argument("--api", default="https://zhe-cyber-argus-ueba.hf.space")
    ap.add_argument("--limit", type=int, default=0, help="Stop after N events (0 = all)")
    ap.add_argument("--delay", type=float, default=0.0, help="Seconds between requests")
    args = ap.parse_args()

    items = collect(args.source)
    if args.limit:
        items = items[: args.limit]
    print(f"[INFO] Ingesting {len(items)} real events ({args.source}) → {args.api}\n")

    ok = err = 0
    for i, (src, ev) in enumerate(items, 1):
        status, body = post(f"{args.api}/ingest", {"event": ev, "source": src})
        if status == 200:
            ok += 1
            u = body.get("user", "?"); a = body.get("action", "?")
            rar = body.get("rarity_score", 0) or 0
            flags = [k for k, v in (body.get("rarity_flags") or {}).items() if v]
            tag = f"  rarity={rar:.0%} [{','.join(flags)}]" if rar >= 0.4 else ""
            print(f"  [{i:>3}] {src:<14} {str(u)[:34]:<34} {str(a)[:30]:<30}{tag}")
        else:
            err += 1
            print(f"  [{i:>3}] {src:<14} HTTP {status}")
        if args.delay:
            time.sleep(args.delay)

    print(f"\n[DONE] {ok} ingested, {err} errors. Visit the dashboard → Cloud filter.")


if __name__ == "__main__":
    main()
