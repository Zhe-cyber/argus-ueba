#!/usr/bin/env python3
"""
cloud_kfold_inductive_eval.py — Inductive 5-fold CV for the cloud autoencoder
on flaws.cloud, removing the transductive optimism of scoring normal user-days
that were in training. Each fold trains the cloud AE on the training fold's
NORMAL user-days only and scores the held-out fold.

IMPORTANT LIMITATION (printed): flaws.cloud contains only ~2 distinct attacker
entities (Level5, Level6), with Level6 accounting for ~99% of attacker
user-days. The attacker class therefore cannot be robustly cross-validated;
this evaluation is a 2-entity case study, not a statistical benchmark.

Outputs results/cloud_kfold_inductive_metrics.json.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
import torch, torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, average_precision_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.cloud_feature_extractor import CLOUD_FEATURES
SEED = 42; np.random.seed(SEED)


def _mk(d):
    class AE(nn.Module):
        def __init__(s, d):
            super().__init__()
            s.e = nn.Sequential(nn.Linear(d, 32), nn.LeakyReLU(.1),
                                nn.Linear(32, 16), nn.LeakyReLU(.1),
                                nn.Linear(16, 8), nn.LeakyReLU(.1))
            s.d = nn.Sequential(nn.Linear(8, 16), nn.LeakyReLU(.1),
                                nn.Linear(16, 32), nn.LeakyReLU(.1), nn.Linear(32, d))
        def forward(s, x): return s.d(s.e(x))
    return AE(d)


def main():
    df = pd.read_parquet(ROOT / "data/processed/cloud_features.parquet")
    X = df[CLOUD_FEATURES].fillna(0).values.astype("float32")
    y = df["is_attacker"].values.astype(int)
    atk_entities = df[df.is_attacker == 1]["user"].nunique()
    print(f"[INFO] {len(df)} user-days, {int(y.sum())} attacker-days, "
          f"{atk_entities} distinct attacker entities")

    skf = StratifiedKFold(5, shuffle=True, random_state=SEED)
    oof = np.zeros(len(y)); fold = []
    for tr, te in skf.split(X, y):
        trn = tr[y[tr] == 0]
        sc = StandardScaler().fit(X[trn]); Xs = sc.transform(X).astype("float32")
        torch.manual_seed(SEED); m = _mk(X.shape[1])
        opt = torch.optim.Adam(m.parameters(), 1e-3, weight_decay=1e-5); lf = nn.MSELoss()
        dl = DataLoader(TensorDataset(torch.tensor(Xs[trn])), batch_size=64, shuffle=True, drop_last=True)
        m.train()
        for _ in range(200):
            for (b,) in dl:
                opt.zero_grad(); l = lf(m(b), b); l.backward(); opt.step()
        m.eval()
        with torch.no_grad():
            e = ((torch.tensor(Xs[te]) - m(torch.tensor(Xs[te]))) ** 2).mean(1).numpy()
        oof[te] = e; fold.append(round(float(roc_auc_score(y[te], e)), 4))

    res = {
        "evaluation": "inductive 5-fold CV (held-out normal user-days)",
        "dataset": "flaws.cloud", "seed": SEED,
        "n_user_days": len(df), "n_attacker_days": int(y.sum()),
        "distinct_attacker_entities": int(atk_entities),
        "limitation": "Level6 ~= 99% of attacker-days; effectively a 2-entity case study, not a benchmark",
        "inductive_auroc_mean": round(float(np.mean(fold)), 4),
        "inductive_auroc_std": round(float(np.std(fold)), 4),
        "pooled_oof_auroc": round(float(roc_auc_score(y, oof)), 4),
        "pooled_oof_auprc": round(float(average_precision_score(y, oof)), 4),
        "reported_same_dataset_auroc": 0.724,
    }
    (ROOT / "results").mkdir(exist_ok=True)
    json.dump(res, open(ROOT / "results/cloud_kfold_inductive_metrics.json", "w"), indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
