"""
anonymise_demo.py — Generate demo data from real processed outputs.

Reads the real scored data, anonymises user IDs, caps to a small slice
suitable for a public demo, and writes:
    demo/demo_scores.csv
    demo/demo_shap.parquet

Usage (from project root):
    python scripts/anonymise_demo.py              # default: 200 users
    python scripts/anonymise_demo.py --n 100      # custom user count
    python scripts/anonymise_demo.py --seed 99    # reproducible shuffle

The output files are committed to the repo (they are excluded from the
normal .gitignore rules that block *.csv / *.parquet).

When DEMO_MODE=true, backend/loader.py reads these files instead of the
full dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# ── Make sure the project root is on sys.path so backend.config is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from backend.config import SCORES_PATH, SHAP_PATH, DEMO_DIR


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_N    = 200   # users in the demo slice
DEFAULT_SEED = 42

# Columns to keep in the scores demo file (drop any raw IDs / PII)
SCORES_KEEP = [
    "ae_score", "if_score", "rule_score", "wa_score", "ensemble_score",
    "is_insider", "scenario",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _anonymise_id(real_id: str, salt: str = "ueba-demo") -> str:
    """
    Replace a real user ID with a deterministic but opaque token.

    The same real_id always maps to the same demo ID so the demo
    dataset is reproducible across runs, but the mapping cannot be
    trivially reversed.
    """
    digest = hashlib.sha256(f"{salt}:{real_id}".encode()).hexdigest()[:8].upper()
    return f"USR-{digest}"


def _stratified_sample(df: pd.DataFrame, n: int, score_col: str,
                        seed: int) -> pd.DataFrame:
    """
    Return n rows preserving the High/Medium/Low risk ratio of the
    full dataset so the demo distribution looks realistic.
    """
    rng = np.random.default_rng(seed)

    p90 = df[score_col].quantile(0.90)
    p70 = df[score_col].quantile(0.70)

    high   = df[df[score_col] >= p90]
    medium = df[(df[score_col] >= p70) & (df[score_col] < p90)]
    low    = df[df[score_col] < p70]

    # Target counts scaled to the full-dataset ratio, minimum 1 per tier
    n_high   = max(1, round(n * len(high)   / len(df)))
    n_medium = max(1, round(n * len(medium) / len(df)))
    n_low    = max(1, n - n_high - n_medium)

    def _safe_sample(bucket, k):
        k = min(k, len(bucket))
        return bucket.sample(k, random_state=int(rng.integers(2**31)))

    return pd.concat([
        _safe_sample(high,   n_high),
        _safe_sample(medium, n_medium),
        _safe_sample(low,    n_low),
    ]).sample(frac=1, random_state=int(rng.integers(2**31)))  # shuffle


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(n: int = DEFAULT_N, seed: int = DEFAULT_SEED) -> None:
    # ── Validate inputs ──────────────────────────────────────────────────
    if not SCORES_PATH.exists():
        print(f"[error] Scores file not found: {SCORES_PATH}")
        print("        Run the scoring pipeline first, or check DATA_DIR in .env")
        sys.exit(1)

    if not SHAP_PATH.exists():
        print(f"[error] SHAP file not found: {SHAP_PATH}")
        print("        Run the scoring pipeline first, or check DATA_DIR in .env")
        sys.exit(1)

    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load full data ────────────────────────────────────────────────────
    print(f"Loading scores  : {SCORES_PATH}")
    scores_full = pd.read_csv(SCORES_PATH)
    scores_full.columns = scores_full.columns.str.strip()

    print(f"Loading SHAP    : {SHAP_PATH}")
    shap_full = pd.read_parquet(SHAP_PATH)
    shap_full.columns = shap_full.columns.str.strip()

    # ── Detect columns ────────────────────────────────────────────────────
    user_col = next(
        (c for c in ("user", "user_id", "userId", "username") if c in scores_full.columns),
        None,
    )
    if user_col is None:
        print(f"[error] Cannot find user column. Columns: {list(scores_full.columns)}")
        sys.exit(1)

    score_col = next(
        (c for c in ("ae_score", "ensemble_score") if c in scores_full.columns),
        None,
    )
    if score_col is None:
        print(f"[error] Cannot find score column. Columns: {list(scores_full.columns)}")
        sys.exit(1)

    print(f"Detected columns: user={user_col!r}, score={score_col!r}")
    print(f"Full dataset    : {len(scores_full):,} users")

    # ── Sample ────────────────────────────────────────────────────────────
    n = min(n, len(scores_full))
    sample = _stratified_sample(scores_full, n, score_col, seed)
    print(f"Demo slice      : {len(sample)} users (stratified, seed={seed})")

    # ── Anonymise user IDs ────────────────────────────────────────────────
    id_map: dict[str, str] = {
        real: _anonymise_id(str(real))
        for real in sample[user_col].unique()
    }
    sample = sample.copy()
    sample[user_col] = sample[user_col].map(id_map)
    sample = sample.rename(columns={user_col: "user"})

    # Keep only safe columns + the user column
    keep_cols = ["user"] + [c for c in SCORES_KEEP if c in sample.columns]
    demo_scores = sample[keep_cols].reset_index(drop=True)

    # ── Write scores CSV ──────────────────────────────────────────────────
    out_scores = DEMO_DIR / "demo_scores.csv"
    demo_scores.to_csv(out_scores, index=False)
    print(f"Written         : {out_scores}  ({len(demo_scores)} rows)")

    # ── Build SHAP demo slice ─────────────────────────────────────────────
    # Detect user column in shap_df
    shap_user_col = next(
        (c for c in ("user", "user_id", "userId", "username") if c in shap_full.columns),
        None,
    )

    real_ids_in_sample = set(scores_full.loc[
        scores_full[user_col].astype(str).isin(
            {v for v in scores_full[user_col].astype(str) if id_map.get(v)}
        ),
        user_col
    ].astype(str))

    # Rebuild reverse map: anon_id → original_id for SHAP lookup
    reverse_map = {v: k for k, v in id_map.items()}

    if shap_user_col:
        # Column-based: filter by original IDs then remap
        orig_ids = set(reverse_map.values())
        shap_slice = shap_full[
            shap_full[shap_user_col].astype(str).isin(orig_ids)
        ].copy()
        shap_slice[shap_user_col] = shap_slice[shap_user_col].astype(str).map(id_map)
        shap_slice = shap_slice.rename(columns={shap_user_col: "user"})
    else:
        # Index-based
        orig_ids = set(reverse_map.values())
        try:
            shap_slice = shap_full.loc[shap_full.index.astype(str).isin(orig_ids)].copy()
            shap_slice.index = shap_slice.index.astype(str).map(id_map)
            shap_slice.index.name = "user"
        except Exception as e:
            print(f"[warn] Could not filter SHAP by index: {e}")
            shap_slice = shap_full.head(n).copy()

    out_shap = DEMO_DIR / "demo_shap.parquet"
    shap_slice.to_parquet(out_shap, index=True)
    print(f"Written         : {out_shap}  ({len(shap_slice)} rows, {shap_slice.shape[1]} cols)")

    # ── Summary ───────────────────────────────────────────────────────────
    p90 = demo_scores[score_col if score_col in demo_scores.columns else "ae_score"].quantile(0.90)
    p70 = demo_scores[score_col if score_col in demo_scores.columns else "ae_score"].quantile(0.70)
    ae  = demo_scores["ae_score"] if "ae_score" in demo_scores.columns else demo_scores.iloc[:, 1]

    high   = int((ae >= p90).sum())
    medium = int(((ae >= p70) & (ae < p90)).sum())
    low    = int((ae < p70).sum())

    print()
    print("Demo data summary")
    print(f"  Total  : {len(demo_scores)}")
    print(f"  High   : {high}  (>= p90 = {p90:.4f})")
    print(f"  Medium : {medium}")
    print(f"  Low    : {low}")
    if "is_insider" in demo_scores.columns:
        print(f"  Insider: {int(demo_scores['is_insider'].sum())}")
    print()
    print("Set DEMO_MODE=true in .env.local and restart the backend to use these files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate anonymised demo data.")
    parser.add_argument("--n",    type=int, default=DEFAULT_N,
                        help=f"Number of users in demo slice (default: {DEFAULT_N})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"Random seed for reproducibility (default: {DEFAULT_SEED})")
    args = parser.parse_args()
    main(n=args.n, seed=args.seed)
