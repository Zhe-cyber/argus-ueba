"""
train_cloud_ae.py — Train a cloud-native Autoencoder on AWS/Azure/GitHub logs.

Reads the cloud_features.parquet produced by build_cloud_dataset.py,
trains a PyTorch autoencoder on NORMAL user behavior, and saves the model to
ml/models/cloud_ae_v1.pt + ml/models/cloud_scaler_v1.pkl.

The AE learns what "normal" cloud API behavior looks like. At inference
time, unusual behavior (privilege escalation, data exfiltration, off-hours
bulk access) will have higher reconstruction error → higher anomaly score.

Usage
-----
    python scripts/train_cloud_ae.py
    python scripts/train_cloud_ae.py --data data/processed/cloud_features.parquet
    python scripts/train_cloud_ae.py --epochs 150 --seed 42

Architecture
------------
    Input  (12) → Linear(12→32) → LeakyReLU → Linear(32→16) → LeakyReLU
    Bottleneck (8)
    Decoder: Linear(8→16) → LeakyReLU → Linear(16→32) → LeakyReLU → Linear(32→12)

Requirements
------------
    pip install torch scikit-learn pandas pyarrow joblib
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.cloud_feature_extractor import CLOUD_FEATURES, CLOUD_INPUT_DIM


# ---------------------------------------------------------------------------
# Autoencoder definition (must exactly match ae_scorer.py cloud arch)
# ---------------------------------------------------------------------------

def _build_cloud_ae(input_dim: int):
    import torch.nn as nn

    class CloudAE(nn.Module):
        def __init__(self, d: int) -> None:
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Linear(d, 32),  nn.LeakyReLU(0.1),
                nn.Linear(32, 16), nn.LeakyReLU(0.1),
                nn.Linear(16, 8),  nn.LeakyReLU(0.1),
            )
            self.decoder = nn.Sequential(
                nn.Linear(8, 16),  nn.LeakyReLU(0.1),
                nn.Linear(16, 32), nn.LeakyReLU(0.1),
                nn.Linear(32, d),
            )

        def forward(self, x):
            return self.decoder(self.encoder(x))

    return CloudAE(input_dim)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(
    data_path:   Path,
    out_dir:     Path,
    epochs:      int  = 200,
    lr:          float = 1e-3,
    batch_size:  int  = 64,
    val_split:   float = 0.2,
    seed:        int  = 42,
) -> None:
    # ── Imports ────────────────────────────────────────────────────────────
    try:
        import numpy as np
        import pandas as pd
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
        from sklearn.preprocessing import StandardScaler
        import joblib
    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e}")
        print("        pip install torch scikit-learn pandas pyarrow joblib")
        sys.exit(1)

    torch.manual_seed(seed)
    np.random.seed(seed)

    # ── Load data ──────────────────────────────────────────────────────────
    if not data_path.exists():
        print(f"[ERROR] Data file not found: {data_path}")
        print("        Run:  python scripts/build_cloud_dataset.py first")
        sys.exit(1)

    df = pd.read_parquet(str(data_path))
    print(f"[INFO] Loaded {len(df):,} user-day rows from {data_path.name}")

    # ── Split: NORMAL users for training, attackers for validation ─────────
    normal_df   = df[df["is_attacker"] == 0].copy()
    attacker_df = df[df["is_attacker"] == 1].copy()

    print(f"[INFO] Normal rows:   {len(normal_df):,} ({normal_df['user'].nunique()} users)")
    print(f"[INFO] Attacker rows: {len(attacker_df):,} ({attacker_df['user'].nunique()} users)")

    if len(normal_df) < 10:
        print("[ERROR] Too few normal rows to train. Check your dataset.")
        sys.exit(1)

    # Chronological split on normal users (80% train, 20% val)
    normal_df = normal_df.sort_values("date")
    split_idx  = int(len(normal_df) * (1 - val_split))
    train_df   = normal_df.iloc[:split_idx]
    val_df     = normal_df.iloc[split_idx:]

    print(f"[INFO] Train: {len(train_df):,} rows  Val: {len(val_df):,} rows")

    X_train = train_df[CLOUD_FEATURES].values.astype(np.float32)
    X_val   = val_df[CLOUD_FEATURES].values.astype(np.float32)
    X_atk   = attacker_df[CLOUD_FEATURES].values.astype(np.float32) if len(attacker_df) else None

    # ── Scale ──────────────────────────────────────────────────────────────
    scaler  = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_val   = scaler.transform(X_val)
    if X_atk is not None:
        X_atk = scaler.transform(X_atk)

    # ── DataLoaders ────────────────────────────────────────────────────────
    train_ds     = TensorDataset(torch.tensor(X_train))
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

    # ── Model ──────────────────────────────────────────────────────────────
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model  = _build_cloud_ae(CLOUD_INPUT_DIM).to(device)
    opt    = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    sched  = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    loss_fn = nn.MSELoss()

    print(f"\n[INFO] Training on {device.type.upper()}  epochs={epochs}  batch={batch_size}")
    print(f"       Input dim: {CLOUD_INPUT_DIM}  Features: {CLOUD_FEATURES}")

    best_val_loss = float("inf")
    best_state    = None

    for epoch in range(1, epochs + 1):
        # ── Train ──
        model.train()
        train_loss = 0.0
        for (batch,) in train_loader:
            batch  = batch.to(device)
            out    = model(batch)
            loss   = loss_fn(out, batch)
            opt.zero_grad(); loss.backward(); opt.step()
            train_loss += loss.item() * len(batch)
        train_loss /= len(train_ds)

        # ── Validate ──
        model.eval()
        with torch.no_grad():
            X_v   = torch.tensor(X_val).to(device)
            val_loss = loss_fn(model(X_v), X_v).item()

        sched.step()

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        if epoch % 25 == 0 or epoch == 1:
            print(f"  epoch {epoch:>4}/{epochs}  train={train_loss:.6f}  val={val_loss:.6f}"
                  f"{'  <-- best' if val_loss == best_val_loss else ''}")

    # ── Compute reconstruction error bounds on normal + attacker data ──────
    model.load_state_dict(best_state)
    model.eval()

    def _mse_scores(X: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            t = torch.tensor(X).to(device)
            r = model(t).cpu().numpy()
        return ((X - r) ** 2).mean(axis=1)

    normal_scores  = _mse_scores(X_val)
    # Calibrate so the p95 of normal maps to ~0.5, meaning attackers (who
    # exceed that) map to >0.5 and eventually reach 1.0.
    # ae_min = p5 of normals (cuts noise floor)
    # ae_max = 2 × p95 of normals (so p95 normal → 0.5, attackers → >0.5)
    ae_min = float(np.percentile(normal_scores, 5))
    ae_max = float(np.percentile(normal_scores, 95) * 2.0)

    print(f"\n[INFO] Reconstruction error on normal (val):")
    print(f"       min={normal_scores.min():.6f}  mean={normal_scores.mean():.6f}  "
          f"max={normal_scores.max():.6f}  p95={np.percentile(normal_scores,95):.6f}")

    if X_atk is not None:
        atk_scores = _mse_scores(X_atk)
        print(f"[INFO] Reconstruction error on ATTACKERS (Level5/Level6):")
        print(f"       min={atk_scores.min():.6f}  mean={atk_scores.mean():.6f}  "
              f"max={atk_scores.max():.6f}  p95={np.percentile(atk_scores,95):.6f}")

        # Show per-user attacker scores
        attacker_df = attacker_df.copy()
        attacker_df["ae_score_raw"] = atk_scores
        print(f"\n  Per-user mean scores (attacker vs normal):")
        for user, grp in attacker_df.groupby("user"):
            s = grp["ae_score_raw"].mean()
            norm_pct = (s - ae_min) / max(ae_max - ae_min, 1e-9)
            print(f"    ATTACKER  {user:<20} raw={s:.4f}  normalised={min(norm_pct,1.0):.3f}")
        norm_mean = float(normal_scores.mean())
        print(f"    normal    (val set avg)        raw={norm_mean:.4f}  "
              f"normalised={(norm_mean-ae_min)/max(ae_max-ae_min,1e-9):.3f}")

    # ── Save ───────────────────────────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path  = out_dir / "cloud_ae_v1.pt"
    scaler_path = out_dir / "cloud_scaler_v1.pkl"
    metrics_path = out_dir / "cloud_ae_metrics.json"

    torch.save({
        "state_dict": best_state,
        "input_dim":  CLOUD_INPUT_DIM,
        "features":   CLOUD_FEATURES,
        "ae_min":     ae_min,
        "ae_max":     ae_max,
        "val_loss":   best_val_loss,
        "epochs":     epochs,
        "seed":       seed,
    }, str(model_path))
    print(f"\n[SAVED] {model_path}")

    joblib.dump(scaler, str(scaler_path))
    print(f"[SAVED] {scaler_path}")

    metrics = {
        "input_dim":    CLOUD_INPUT_DIM,
        "features":     CLOUD_FEATURES,
        "train_rows":   len(train_df),
        "val_rows":     len(val_df),
        "attacker_rows": len(attacker_df) if X_atk is not None else 0,
        "best_val_loss": round(best_val_loss, 8),
        "ae_min":        round(ae_min, 8),
        "ae_max":        round(ae_max, 8),
        "normal_mean_score":  round(float(normal_scores.mean()), 6),
    }
    if X_atk is not None:
        metrics["attacker_mean_score"] = round(float(atk_scores.mean()), 6)
        metrics["attacker_mean_normalised"] = round(
            float(((atk_scores.mean() - ae_min) / max(ae_max - ae_min, 1e-9))), 4
        )
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[SAVED] {metrics_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data",       default="data/processed/cloud_features.parquet",
                   help="Path to cloud_features.parquet (from build_cloud_dataset.py)")
    p.add_argument("--out",        default="ml/models/",
                   help="Directory to save model + scaler (default: ml/models/)")
    p.add_argument("--epochs",     type=int,   default=200)
    p.add_argument("--lr",         type=float, default=1e-3)
    p.add_argument("--batch-size", type=int,   default=64)
    p.add_argument("--seed",       type=int,   default=42)
    return p.parse_args()


if __name__ == "__main__":
    args = _args()
    train(
        data_path  = Path(args.data),
        out_dir    = Path(args.out),
        epochs     = args.epochs,
        lr         = args.lr,
        batch_size = args.batch_size,
        seed       = args.seed,
    )
