"""
cert_extract.py — Build per-(user, day) behavioural features from raw CERT r4.2 logs.

This is the shared foundation for:
  • Workstream B — peer-group scoring  (data/processed/daily_features_v4.parquet)
  • Workstream A — live eval-loop replay (scripts/replay_eval.py reuses this output)

It streams the raw CERT r4.2 CSVs (logon, device, file, email, http), filters to the
cohort of users present in user_scores_v4.csv, and produces a daily-feature table whose
columns and classification logic EXACTLY mirror backend/feature_extractor.py — so the
features reproduced here match what the live pipeline computes from ingested events.

Usage
-----
    # fast smoke test (cap rows per file, 40 users)
    python scripts/cert_extract.py --raw ~/Downloads/r4.2/r4.2 --sample-users 40 \
        --row-limit 200000 --out data/processed/daily_features_smoke.parquet

    # full run (all 1000 users, every row — reads the full 14.5 GB http.csv)
    python scripts/cert_extract.py --raw ~/Downloads/r4.2/r4.2 \
        --out data/processed/daily_features_v4.parquet

Notes
-----
  • CERT r4.2 date format is MM/DD/YYYY HH:MM:SS.
  • Business hours = 07:00–18:00 (matches feature_extractor._BIZ_START/_END).
  • r4.2 file.csv has no removable-media column, so USB activity is derived from
    device.csv only — identical to how the live feature_extractor behaves on r4.2 rows.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Reuse the EXACT classification sets from the live pipeline so the features
# produced offline here match the features the live AE sees at inference time.
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from backend.feature_extractor import (  # noqa: E402
    _ARCHIVE_EXTS, _JOB_SITES, _CLOUD_SITES, _SUSPICIOUS_SITES,
    _BIZ_START, _BIZ_END,
)

# The 21 behavioural features, in the canonical order used by ae_scorer.MODEL_FEATURES.
FEATURE_COLS = [
    "login_count", "after_hours_count", "unique_pcs",
    "files_accessed", "n_archive_files", "n_exe_files", "n_afterhours_file",
    "usb_events", "has_usb", "n_afterhours_usb",
    "email_count", "total_attachments", "external_emails",
    "n_afterhours_email", "n_bcc_email",
    "http_count", "suspicious_http", "n_job_site",
    "n_cloud_storage", "n_afterhours_http",
    "usb_and_file",
]

_CHUNK = 500_000


def _log(msg: str) -> None:
    print(f"[cert_extract] {msg}", flush=True)


def _parse_dates(s: pd.Series) -> pd.Series:
    """Parse CERT MM/DD/YYYY HH:MM:SS → datetime (coerce bad rows to NaT)."""
    return pd.to_datetime(s, format="%m/%d/%Y %H:%M:%S", errors="coerce")


def _after_hours(dt: pd.Series) -> pd.Series:
    h = dt.dt.hour
    return (h < _BIZ_START) | (h >= _BIZ_END)


def _contains_any(text: pd.Series, needles) -> pd.Series:
    """Vectorised 'does the lowercased string contain any needle' over a frozenset."""
    pat = "|".join(re_escape(n) for n in needles)
    return text.str.contains(pat, case=False, na=False, regex=True)


def re_escape(s: str) -> str:
    import re
    return re.escape(s)


def _groupby_day(df: pd.DataFrame, feat_cols: list[str]) -> pd.DataFrame:
    """Collapse a per-event frame with a 'user'/'day' column to per-(user,day) sums."""
    return df.groupby(["user", "day"], observed=True)[feat_cols].sum().reset_index()


# ---------------------------------------------------------------------------
# Per-source streaming processors — each returns a per-(user,day) sum frame
# ---------------------------------------------------------------------------

def _accumulate(path: Path, usecols, cohort: set[str], row_limit: int | None,
                row_fn) -> pd.DataFrame:
    """Stream a CSV in chunks, filter to cohort, apply row_fn, sum per (user,day)."""
    if not path.exists():
        _log(f"  [skip] {path.name} not found")
        return pd.DataFrame(columns=["user", "day"])

    t0 = time.time()
    parts: list[pd.DataFrame] = []
    seen = 0
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=_CHUNK,
                             dtype=str, on_bad_lines="skip"):
        seen += len(chunk)
        chunk = chunk[chunk["user"].isin(cohort)]
        if not chunk.empty:
            part = row_fn(chunk)
            if part is not None and not part.empty:
                parts.append(part)
        if row_limit and seen >= row_limit:
            _log(f"  {path.name}: hit row-limit {row_limit:,}")
            break

    if not parts:
        return pd.DataFrame(columns=["user", "day"])
    out = pd.concat(parts, ignore_index=True)
    feat_cols = [c for c in out.columns if c not in ("user", "day")]
    out = out.groupby(["user", "day"], observed=True)[feat_cols].sum().reset_index()
    _log(f"  {path.name}: {seen:,} rows scanned → {len(out):,} user-days "
         f"({time.time()-t0:.1f}s)")
    return out


def _logon_rows(chunk: pd.DataFrame) -> pd.DataFrame:
    dt = _parse_dates(chunk["date"])
    ah = _after_hours(dt)
    out = pd.DataFrame({
        "user": chunk["user"].values,
        "day": dt.dt.strftime("%Y-%m-%d").values,
        "pc": chunk.get("pc", pd.Series(["" ] * len(chunk))).values,
        "login_count": 1,
        "after_hours_count": ah.astype(int).values,
    })
    out = out.dropna(subset=["day"])
    # unique_pcs handled at merge time via nunique; here pass pc for that.
    return out


def _device_rows(chunk: pd.DataFrame) -> pd.DataFrame:
    # Only Connect events count as a USB event (matches "usb connect" semantics).
    act = chunk.get("activity", pd.Series([""] * len(chunk))).fillna("")
    is_connect = act.str.contains("connect", case=False, na=False)
    chunk = chunk[is_connect]
    if chunk.empty:
        return pd.DataFrame(columns=["user", "day"])
    dt = _parse_dates(chunk["date"])
    ah = _after_hours(dt)
    out = pd.DataFrame({
        "user": chunk["user"].values,
        "day": dt.dt.strftime("%Y-%m-%d").values,
        "usb_events": 1,
        "has_usb": 1,
        "n_afterhours_usb": ah.astype(int).values,
    })
    return out.dropna(subset=["day"])


def _file_rows(chunk: pd.DataFrame) -> pd.DataFrame:
    dt = _parse_dates(chunk["date"])
    ah = _after_hours(dt)
    fn = chunk["filename"].fillna("").str.lower()
    ext = "." + fn.str.rsplit(".", n=1).str[-1]
    is_archive = ext.isin(_ARCHIVE_EXTS)
    is_exe = (ext == ".exe")
    out = pd.DataFrame({
        "user": chunk["user"].values,
        "day": dt.dt.strftime("%Y-%m-%d").values,
        "files_accessed": 1,
        "n_archive_files": is_archive.astype(int).values,
        "n_exe_files": is_exe.astype(int).values,
        "n_afterhours_file": ah.astype(int).values,
    })
    return out.dropna(subset=["day"])


def _email_rows(chunk: pd.DataFrame) -> pd.DataFrame:
    dt = _parse_dates(chunk["date"])
    ah = _after_hours(dt)
    to = chunk.get("to", pd.Series([""] * len(chunk))).fillna("")
    bcc = chunk.get("bcc", pd.Series([""] * len(chunk))).fillna("")
    frm = chunk.get("from", pd.Series([""] * len(chunk))).fillna("")
    own_domain = frm.str.split("@").str[-1].str.lower()

    # external = any recipient whose domain differs from sender's domain
    def _ext(row_to: str, dom: str) -> int:
        for addr in str(row_to).split(";"):
            addr = addr.strip().lower()
            if "@" in addr and addr.split("@")[-1] != dom:
                return 1
        return 0

    external = [
        _ext(t, d) for t, d in zip(to.values, own_domain.values)
    ]
    att = pd.to_numeric(chunk.get("attachments", 0), errors="coerce").fillna(0).astype(int)
    out = pd.DataFrame({
        "user": chunk["user"].values,
        "day": dt.dt.strftime("%Y-%m-%d").values,
        "email_count": 1,
        "total_attachments": att.values,
        "external_emails": external,
        "n_afterhours_email": ah.astype(int).values,
        "n_bcc_email": (bcc.str.strip() != "").astype(int).values,
    })
    return out.dropna(subset=["day"])


def _http_rows(chunk: pd.DataFrame) -> pd.DataFrame:
    dt = _parse_dates(chunk["date"])
    ah = _after_hours(dt)
    url = chunk["url"].fillna("").str.lower()
    out = pd.DataFrame({
        "user": chunk["user"].values,
        "day": dt.dt.strftime("%Y-%m-%d").values,
        "http_count": 1,
        "n_afterhours_http": ah.astype(int).values,
        "n_job_site": _contains_any(url, _JOB_SITES).astype(int).values,
        "n_cloud_storage": _contains_any(url, _CLOUD_SITES).astype(int).values,
        "suspicious_http": _contains_any(url, _SUSPICIOUS_SITES).astype(int).values,
    })
    return out.dropna(subset=["day"])


# ---------------------------------------------------------------------------
# unique_pcs needs nunique, not sum — handled separately from logon stream.
# ---------------------------------------------------------------------------

def _logon_unique_pcs(path: Path, cohort: set[str], row_limit: int | None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["user", "day", "unique_pcs"])
    parts = []
    seen = 0
    for chunk in pd.read_csv(path, usecols=["date", "user", "pc"], chunksize=_CHUNK,
                             dtype=str, on_bad_lines="skip"):
        seen += len(chunk)
        chunk = chunk[chunk["user"].isin(cohort)]
        if not chunk.empty:
            dt = _parse_dates(chunk["date"])
            tmp = pd.DataFrame({
                "user": chunk["user"].values,
                "day": dt.dt.strftime("%Y-%m-%d").values,
                "pc": chunk["pc"].fillna("").values,
            }).dropna(subset=["day"])
            parts.append(tmp)
        if row_limit and seen >= row_limit:
            break
    if not parts:
        return pd.DataFrame(columns=["user", "day", "unique_pcs"])
    allpc = pd.concat(parts, ignore_index=True)
    up = allpc.groupby(["user", "day"], observed=True)["pc"].nunique().reset_index()
    up = up.rename(columns={"pc": "unique_pcs"})
    return up


def main() -> int:
    ap = argparse.ArgumentParser(description="Build daily_features parquet from raw CERT r4.2 logs.")
    ap.add_argument("--raw", default=str(Path.home() / "Downloads" / "r4.2" / "r4.2"),
                    help="Directory containing logon.csv, device.csv, file.csv, email.csv, http.csv")
    ap.add_argument("--scores", default="data/processed/user_scores_v4.csv",
                    help="CSV defining the cohort (must have a 'user' column)")
    ap.add_argument("--out", default="data/processed/daily_features_v4.parquet")
    ap.add_argument("--sample-users", type=int, default=0,
                    help="If >0, randomly sample this many users (insiders always kept)")
    ap.add_argument("--row-limit", type=int, default=0,
                    help="If >0, cap rows scanned PER FILE (smoke testing)")
    ap.add_argument("--skip-http", action="store_true",
                    help="Skip the 14.5 GB http.csv (fast; http features will be 0)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    raw = Path(args.raw).expanduser()
    scores = pd.read_csv(args.scores)
    rng = np.random.default_rng(args.seed)

    all_users = scores["user"].astype(str).tolist()
    if args.sample_users and args.sample_users < len(all_users):
        insiders = scores[scores.get("is_insider", 0) == 1]["user"].astype(str).tolist()
        normals = [u for u in all_users if u not in set(insiders)]
        n_norm = max(args.sample_users - len(insiders), 0)
        picked = set(insiders) | set(rng.choice(normals, size=min(n_norm, len(normals)),
                                                 replace=False).tolist())
        cohort = picked
    else:
        cohort = set(all_users)

    _log(f"cohort: {len(cohort)} users  | raw dir: {raw}")
    row_limit = args.row_limit or None

    frames = []
    frames.append(_accumulate(raw / "logon.csv", ["date", "user", "pc", "activity"],
                              cohort, row_limit, lambda c: _logon_rows(c).drop(columns=["pc"])))
    frames.append(_logon_unique_pcs(raw / "logon.csv", cohort, row_limit))
    frames.append(_accumulate(raw / "device.csv", ["date", "user", "pc", "activity"],
                              cohort, row_limit, _device_rows))
    frames.append(_accumulate(raw / "file.csv", ["date", "user", "filename"],
                              cohort, row_limit, _file_rows))
    frames.append(_accumulate(raw / "email.csv",
                              ["date", "user", "to", "bcc", "from", "attachments"],
                              cohort, row_limit, _email_rows))
    if not args.skip_http:
        frames.append(_accumulate(raw / "http.csv", ["date", "user", "url"],
                                  cohort, row_limit, _http_rows))

    # Outer-merge all sources on (user, day)
    daily = None
    for fr in frames:
        if fr is None or fr.empty:
            continue
        daily = fr if daily is None else daily.merge(fr, on=["user", "day"], how="outer")

    if daily is None or daily.empty:
        _log("ERROR: no data produced — check --raw path and cohort")
        return 1

    # usb_and_file: r4.2 file.csv lacks removable-media flag → 0 (matches live behaviour)
    if "usb_and_file" not in daily.columns:
        daily["usb_and_file"] = 0

    for col in FEATURE_COLS:
        if col not in daily.columns:
            daily[col] = 0
        daily[col] = pd.to_numeric(daily[col], errors="coerce").fillna(0)

    daily = daily[["user", "day"] + FEATURE_COLS]
    daily["user"] = daily["user"].astype(str)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    daily.to_parquet(out, index=False)
    _log(f"WROTE {out}  ({len(daily):,} user-days, {daily['user'].nunique()} users)")
    _log(f"  per-user totals (sample):\n{daily.groupby('user')[FEATURE_COLS].sum().head(3)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
