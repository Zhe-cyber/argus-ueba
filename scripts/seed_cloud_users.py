# -*- coding: utf-8 -*-
"""
seed_cloud_users.py - Seed the dashboard with flaws.cloud users.

Computes AE scores locally from cloud_features.parquet, then bulk-upserts
them into the live backend via POST /admin/seed-live-scores (one request).

This bridges the offline training pipeline and the live dashboard so that
all flaws.cloud users (including Level5/Level6 attackers) appear on the
Cloud source view with real scores.

Usage
-----
    python scripts/seed_cloud_users.py                          # live HF
    python scripts/seed_cloud_users.py --api http://localhost:8001
    python scripts/seed_cloud_users.py --dry-run                # show scores only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

API_DEFAULT   = "https://zhe-cyber-argus-ueba.hf.space"
DATA_PATH     = ROOT / "data"  / "processed" / "cloud_features.parquet"
MODEL_PATH    = ROOT / "ml"    / "models"    / "cloud_ae_v1.pt"
SCALER_PATH   = ROOT / "ml"    / "models"    / "cloud_scaler_v1.pkl"
ADMIN_TOKEN   = "argus-admin-2026"          # must match ADMIN_TOKEN on the HF Space


def compute_scores(dry_run: bool) -> list[dict]:
    """Load parquet + model, score every user, return list of score dicts."""
    import numpy as np
    import pandas as pd
    import torch
    import joblib
    from backend.cloud_feature_extractor import CLOUD_FEATURES

    df = pd.read_parquet(str(DATA_PATH))
    print(f"[INFO] {len(df):,} user-days, {df['user'].nunique()} users")

    # One row per user — aggregate across all their days
    # Use mean of feature values across all days (captures full behavioural baseline)
    # Aggregate each feature as mean across all user-days; sum event_count
    feat_agg = {f: (f, "mean") for f in CLOUD_FEATURES if f != "event_count"}
    agg = df.groupby("user").agg(
        is_attacker  = ("is_attacker", "max"),
        total_events = ("event_count", "sum"),  # total events across all days
        **feat_agg,
    ).reset_index()

    # event_count was aggregated as total_events; restore for feature matrix
    if "event_count" in CLOUD_FEATURES and "event_count" not in agg.columns:
        agg["event_count"] = agg["total_events"]
    X_raw = agg[CLOUD_FEATURES].fillna(0.0).values.astype("float32")

    # Load scaler + model
    scaler = joblib.load(str(SCALER_PATH))
    X_scaled = scaler.transform(X_raw).astype("float32")

    ckpt = torch.load(str(MODEL_PATH), map_location="cpu", weights_only=False)
    ae_min = float(ckpt["ae_min"])
    ae_max = float(ckpt["ae_max"])

    import torch.nn as nn
    class CloudAE(nn.Module):
        def __init__(self, d):
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Linear(d, 32), nn.LeakyReLU(0.1),
                nn.Linear(32, 16), nn.LeakyReLU(0.1),
                nn.Linear(16, 8),  nn.LeakyReLU(0.1),
            )
            self.decoder = nn.Sequential(
                nn.Linear(8, 16),  nn.LeakyReLU(0.1),
                nn.Linear(16, 32), nn.LeakyReLU(0.1),
                nn.Linear(32, d),
            )
        def forward(self, x): return self.decoder(self.encoder(x))

    model = CloudAE(len(CLOUD_FEATURES))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    with torch.no_grad():
        x_t   = torch.tensor(X_scaled)
        recon = model(x_t)
        errors = ((x_t - recon) ** 2).mean(dim=1).numpy()

    ae_range = ae_max - ae_min
    scores_norm = np.clip((errors - ae_min) / ae_range if ae_range > 0 else errors, 0.0, 1.0)

    results = []
    print(f"\n{'User':<35} {'Score':>7}  {'Risk':<6}  Label")
    print("-" * 65)
    for i, row in agg.iterrows():
        user    = str(row["user"])
        score   = float(scores_norm[i])
        label   = "ATTACKER" if row["is_attacker"] else "normal"
        risk    = "High" if score >= 0.7 else "Medium" if score >= 0.4 else "Low"
        print(f"  {user:<33} {score:>7.4f}  {risk:<6}  {label}")
        results.append({
            "user_id":     user,
            "ae_live":     round(score, 6),
            "rule_live":   0.0,
            "rarity":      0.0,
            "event_count": int(row.get("total_events", 1)),
        })

    return results


def push_scores(api: str, scores: list[dict]) -> None:
    """Bulk-upsert scores via POST /admin/seed-live-scores."""
    try:
        import requests
        r = requests.post(
            f"{api}/admin/seed-live-scores",
            json=scores,
            headers={"x-admin-token": ADMIN_TOKEN, "Content-Type": "application/json"},
            timeout=60,
        )
        print(f"\n[INFO] POST /admin/seed-live-scores -> HTTP {r.status_code}")
        print(f"       {r.json()}")
    except Exception as exc:
        import urllib.request
        data = json.dumps(scores).encode()
        req  = urllib.request.Request(
            f"{api}/admin/seed-live-scores", data=data,
            headers={"x-admin-token": ADMIN_TOKEN, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(f"\n[INFO] POST -> HTTP {resp.status}  {json.loads(resp.read())}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api",      default=API_DEFAULT)
    p.add_argument("--dry-run",  action="store_true",
                   help="Compute and print scores only — do not push to backend")
    args = p.parse_args()

    scores = compute_scores(args.dry_run)

    if args.dry_run:
        print(f"\n[DRY-RUN] would push {len(scores)} scores to {args.api}")
        return

    print(f"\n[INFO] Pushing {len(scores)} scores to {args.api} ...")
    push_scores(args.api, scores)
    print("[DONE] Reload the dashboard -> Cloud filter to see the users.")


if __name__ == "__main__":
    main()
