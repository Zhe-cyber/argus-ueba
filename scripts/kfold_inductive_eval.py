#!/usr/bin/env python3
"""
kfold_inductive_eval.py — Inductive (held-out) evaluation of the one-class
autoencoder via 5-fold cross-validation, to remove the transductive optimism
of scoring users that were in the training set.

Procedure (per fold):
  1. Split users into 5 stratified folds on is_insider.
  2. Fit StandardScaler + behavioural peer-group KMeans on TRAIN-fold NORMALS only.
  3. Train the one-class autoencoder on TRAIN-fold NORMALS only.
  4. Score the HELD-OUT fold (reconstruction error).
Every user is therefore scored by a model that never saw it. Pool the
out-of-fold scores and compute AUROC / AUPRC / F1.

Outputs results/kfold_inductive_metrics.json.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SEED = 42
np.random.seed(SEED)

import torch, torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             precision_recall_curve)

ROLE_FEATURES = ["login_count_sum", "files_accessed_sum", "usb_events_sum", "email_count_sum"]


def build_user_table(daily_path: Path, scores_path: Path):
    daily = pd.read_parquet(daily_path)
    base = [c for c in daily.columns if c not in ("user", "date_d", "y_true")]
    g = daily.groupby("user")
    U = pd.concat([
        g[base].sum().add_suffix("_sum"),
        g[base].mean().add_suffix("_mean"),
        g[base].max().add_suffix("_max"),
    ], axis=1).reset_index()
    # burst ratios + usb/file interaction (match the production feature pipeline)
    for f in ("files_accessed", "usb_events", "after_hours_count"):
        U[f + "_burst_ratio"] = np.minimum(U[f + "_max"] / np.maximum(U[f + "_mean"], 0.001), 50.0)
    U["usb_file_interaction"] = U["has_usb_sum"] * U["files_accessed_max"]
    labels = pd.read_csv(scores_path)[["user", "is_insider"]]
    U = U.merge(labels, on="user", how="left").fillna({"is_insider": 0})
    static_feats = [c for c in U.columns
                    if c.endswith(("_sum", "_mean", "_max", "_burst_ratio")) or c == "usb_file_interaction"]
    return U, static_feats


def make_ae(d: int):
    class AE(nn.Module):
        def __init__(self, d):
            super().__init__()
            self.enc = nn.Sequential(
                nn.Linear(d, 128), nn.BatchNorm1d(128), nn.LeakyReLU(0.1), nn.Dropout(0.3),
                nn.Linear(128, 64), nn.BatchNorm1d(64), nn.LeakyReLU(0.1), nn.Dropout(0.2),
                nn.Linear(64, 32), nn.BatchNorm1d(32), nn.LeakyReLU(0.1),
                nn.Linear(32, 16), nn.LeakyReLU(0.1))
            self.dec = nn.Sequential(
                nn.Linear(16, 32), nn.LeakyReLU(0.1),
                nn.Linear(32, 64), nn.BatchNorm1d(64), nn.LeakyReLU(0.1), nn.Dropout(0.2),
                nn.Linear(64, 128), nn.BatchNorm1d(128), nn.LeakyReLU(0.1),
                nn.Linear(128, d))
        def forward(self, x): return self.dec(self.enc(x))
    return AE(d)


def train_ae(Xtr, epochs=150):
    torch.manual_seed(SEED)
    model = make_ae(Xtr.shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.MSELoss()
    dl = DataLoader(TensorDataset(torch.tensor(Xtr)), batch_size=64, shuffle=True, drop_last=True)
    model.train()
    for _ in range(epochs):
        for (b,) in dl:
            opt.zero_grad(); out = model(b); loss = loss_fn(out, b); loss.backward(); opt.step()
    return model


def recon_error(model, X):
    model.eval()
    with torch.no_grad():
        r = model(torch.tensor(X))
        return ((torch.tensor(X) - r) ** 2).mean(dim=1).numpy()


def peer_ratio_features(U, train_norm_idx, all_role):
    """Fit peer KMeans (K=5) on TRAIN normals, return peer-ratio columns for all users."""
    rs = StandardScaler().fit(all_role[train_norm_idx])
    km = KMeans(n_clusters=5, random_state=SEED, n_init=10).fit(rs.transform(all_role[train_norm_idx]))
    pg_train_norm = km.predict(rs.transform(all_role[train_norm_idx]))
    avgs = pd.DataFrame(all_role[train_norm_idx], columns=ROLE_FEATURES)
    avgs["pg"] = pg_train_norm
    peer_mean = avgs.groupby("pg")[ROLE_FEATURES].mean()
    pg_all = km.predict(rs.transform(all_role))
    out = np.zeros((len(all_role), len(ROLE_FEATURES)), dtype=np.float32)
    for j, f in enumerate(ROLE_FEATURES):
        pm = pd.Series(pg_all).map(peer_mean[f]).values
        out[:, j] = all_role[:, j] / np.maximum(pm, 1.0)
    return out


def main():
    U, static_feats = build_user_table(ROOT / "_kfold/daily_features_v4.parquet",
                                       ROOT / "_kfold/user_scores_v4.csv")
    y = U["is_insider"].values.astype(int)
    all_role = U[ROLE_FEATURES].values.astype(np.float32)
    print(f"[INFO] {len(U)} users, {int(y.sum())} insiders, {len(static_feats)+4} features")

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    oof = np.zeros(len(U)); per_fold = []
    for k, (tr, te) in enumerate(skf.split(U, y), 1):
        tr_norm = tr[y[tr] == 0]
        peer = peer_ratio_features(U, tr_norm, all_role)             # fit on train normals
        X = np.hstack([U[static_feats].values.astype(np.float32), peer]).astype(np.float32)
        sc = StandardScaler().fit(X[tr_norm])                        # scale on train normals
        Xs = sc.transform(X).astype(np.float32)
        model = train_ae(Xs[tr_norm])                               # train on train normals
        oof[te] = recon_error(model, Xs[te])                        # score held-out fold
        fa = roc_auc_score(y[te], oof[te])
        per_fold.append(round(float(fa), 4))
        print(f"  fold {k}: held-out AUROC = {fa:.4f}  (test n={len(te)}, insiders={int(y[te].sum())})")

    auroc = roc_auc_score(y, oof)
    auprc = average_precision_score(y, oof)
    prec, rec, thr = precision_recall_curve(y, oof)
    f1s = np.where((prec + rec) > 0, 2 * prec * rec / (prec + rec), 0)
    f1 = float(np.max(f1s))

    res = {
        "evaluation": "inductive — 5-fold stratified CV, one-class AE retrained per fold, out-of-fold scoring",
        "seed": SEED, "n_users": len(U), "n_insiders": int(y.sum()),
        "pooled_auroc": round(float(auroc), 4),
        "pooled_auprc": round(float(auprc), 4),
        "pooled_f1_best": round(f1, 4),
        "per_fold_auroc": per_fold,
        "per_fold_mean": round(float(np.mean(per_fold)), 4),
        "per_fold_std": round(float(np.std(per_fold)), 4),
        "transductive_reference_auroc": 0.9763,
    }
    (ROOT / "results").mkdir(exist_ok=True)
    json.dump(res, open(ROOT / "results/kfold_inductive_metrics.json", "w"), indent=2)
    print("\n" + json.dumps(res, indent=2))
    print("\n[SAVED] results/kfold_inductive_metrics.json")


if __name__ == "__main__":
    main()
