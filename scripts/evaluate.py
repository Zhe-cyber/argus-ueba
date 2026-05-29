# -*- coding: utf-8 -*-
"""
evaluate.py -- Offline evaluation script for the Argus UEBA models.

Produces publication-quality SVG charts + a metrics.json file
for the FYP dissertation.

Usage
-----
    # Basic (all charts + metrics table)
    python scripts/evaluate.py

    # With reproducibility seed
    python scripts/evaluate.py --seed 42

    # Also run /ingest latency benchmark (requires backend running on localhost:8000)
    python scripts/evaluate.py --benchmark

    # Use non-default data paths
    python scripts/evaluate.py \\
        --scores  data/processed/user_scores_v4.csv \\
        --shap    data/processed/shap_values_v4.parquet \\
        --out     results/

Requirements
------------
    pip install -r scripts/requirements-eval.txt

Output files (saved to --out directory)
----------------------------------------
    roc_curves.svg         ROC curves for all 5 models
    pr_curves.svg          Precision-Recall curves (handles class imbalance)
    shap_importance.svg    Mean |SHAP| bar chart — top 15 features
    confusion_matrix.svg   Confusion matrix at F1-optimal threshold
    calibration.svg        Reliability diagram (calibration plot)
    rarity_correlation.svg Flag firing rate by insider vs normal (grouped bar)
    metrics.json           AUROC + AUPRC + F1 + P + R for all models
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

# Force UTF-8 on Windows consoles that default to cp1252
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scores",    default="data/processed/user_scores_v4.csv",
                   help="Path to user_scores_v4.csv")
    p.add_argument("--shap",      default="data/processed/shap_values_v4 (2).parquet",
                   help="Path to shap_values_v4.parquet")
    p.add_argument("--out",       default="results/",
                   help="Directory to write output files (created if missing)")
    p.add_argument("--seed",      type=int, default=42,
                   help="Random seed for reproducibility")
    p.add_argument("--benchmark", action="store_true",
                   help="Run /ingest latency benchmark (requires backend on localhost:8000)")
    p.add_argument("--backend-url", default="http://localhost:8000",
                   help="Backend URL for latency benchmark")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Models under evaluation
# ---------------------------------------------------------------------------

MODELS = [
    ("Autoencoder",      "ae_score"),
    ("Isolation Forest", "if_score"),
    ("Rule-based",       "rule_score"),
    ("Weighted Avg",     "wa_score"),
    ("Ensemble",         "ensemble_score"),
]

# Colour palette (colour-blind safe — Okabe & Ito 2008)
PALETTE = {
    "Autoencoder":      "#E69F00",
    "Isolation Forest": "#56B4E9",
    "Rule-based":       "#009E73",
    "Weighted Avg":     "#F0E442",
    "Ensemble":         "#0072B2",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data(scores_path: str, shap_path: str):
    """Return (scores_df, shap_df).  shap_df may be None if file not found."""
    import pandas as pd

    scores_p = Path(scores_path)
    if not scores_p.exists():
        print(f"[ERROR] Scores file not found: {scores_p.resolve()}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(scores_p)
    print(f"[INFO] Loaded {len(df):,} users from {scores_p.name}")

    # Validate required columns
    required = {"is_insider"}
    for name, col in MODELS:
        required.add(col)
    missing = required - set(df.columns)
    if missing:
        print(f"[WARN] Missing columns: {sorted(missing)} — those models will be skipped.")

    shap_df = None
    shap_p  = Path(shap_path)
    if shap_p.exists():
        shap_df = pd.read_parquet(shap_p)
        print(f"[INFO] Loaded SHAP values: {shap_df.shape}")
    else:
        print(f"[WARN] SHAP file not found: {shap_p.resolve()} — SHAP chart will be skipped.")

    return df, shap_df


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(df, rng: np.random.Generator) -> dict:
    """
    For each model compute: AUROC, AUPRC, F1 at optimal threshold,
    Precision, Recall, and the optimal threshold itself.
    """
    from sklearn.metrics import (
        roc_auc_score, average_precision_score,
        precision_recall_curve, f1_score,
    )

    y_true = df["is_insider"].values
    results = {}

    for name, col in MODELS:
        if col not in df.columns:
            continue
        y_score = df[col].fillna(0).values

        # AUROC — skip if only one class
        try:
            auroc = roc_auc_score(y_true, y_score)
        except ValueError:
            auroc = float("nan")

        # AUPRC (average precision)
        auprc = average_precision_score(y_true, y_score)

        # Find F1-optimal threshold from PR curve
        prec, rec, thresholds = precision_recall_curve(y_true, y_score)
        # f1 at each threshold
        with np.errstate(divide="ignore", invalid="ignore"):
            f1s = np.where((prec + rec) > 0,
                           2 * prec * rec / (prec + rec),
                           0.0)
        # thresholds has len = len(prec) - 1; last point is trivially 1/0
        best_idx   = int(np.argmax(f1s[:-1])) if len(f1s) > 1 else 0
        best_thr   = float(thresholds[best_idx])
        best_f1    = float(f1s[best_idx])
        best_prec  = float(prec[best_idx])
        best_rec   = float(rec[best_idx])

        results[name] = {
            "col":       col,
            "auroc":     round(float(auroc), 4),
            "auprc":     round(float(auprc), 4),
            "f1":        round(best_f1,   4),
            "precision": round(best_prec, 4),
            "recall":    round(best_rec,  4),
            "threshold": round(best_thr,  4),
        }

    return results


def print_metrics_table(metrics: dict) -> None:
    if not metrics:
        print("\n[WARN] No models had sufficient columns — metrics table skipped.")
        return
    header = f"{'Model':<22}{'AUROC':>7}{'AUPRC':>7}{'F1':>7}{'Prec':>7}{'Recall':>7}{'Thr':>8}"
    sep = "-" * len(header)
    print(f"\n{sep}")
    print(header)
    print(sep)
    for name, m in metrics.items():
        print(
            f"{name:<22}{m['auroc']:>7.4f}{m['auprc']:>7.4f}"
            f"{m['f1']:>7.4f}{m['precision']:>7.4f}{m['recall']:>7.4f}"
            f"{m['threshold']:>8.4f}"
        )
    print(sep)
    print()


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _save(fig, out_dir: Path, filename: str) -> None:
    path = out_dir / filename
    fig.savefig(path, format="svg", bbox_inches="tight")
    print(f"[SAVED] {path}")


# ---------------------------------------------------------------------------
# Chart 1: ROC curves
# ---------------------------------------------------------------------------

def plot_roc(df, metrics: dict, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import roc_curve

    fig, ax = plt.subplots(figsize=(7, 6))
    y_true = df["is_insider"].values

    # chance line
    ax.plot([0, 1], [0, 1], color="#cccccc", linestyle="--", linewidth=1, label="Chance")

    for name, col in MODELS:
        if col not in df.columns:
            continue
        y_score = df[col].fillna(0).values
        fpr, tpr, _ = roc_curve(y_true, y_score)
        auroc = metrics.get(name, {}).get("auroc", 0)
        ax.plot(fpr, tpr, linewidth=2, color=PALETTE.get(name, "#888"),
                label=f"{name}  (AUROC={auroc:.3f})")

    ax.set_xlabel("False Positive Rate", fontsize=11)
    ax.set_ylabel("True Positive Rate", fontsize=11)
    ax.set_title("ROC Curves — Insider Threat Detection", fontsize=12, fontweight="bold")
    ax.legend(loc="lower right", fontsize=9)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.25, linestyle="--")
    fig.tight_layout()
    _save(fig, out_dir, "roc_curves.svg")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 2: Precision-Recall curves
# ---------------------------------------------------------------------------

def plot_pr(df, metrics: dict, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import precision_recall_curve

    fig, ax = plt.subplots(figsize=(7, 6))
    y_true = df["is_insider"].values
    prevalence = y_true.mean()
    ax.axhline(prevalence, color="#cccccc", linestyle="--", linewidth=1,
               label=f"Baseline (prevalence={prevalence:.3f})")

    for name, col in MODELS:
        if col not in df.columns:
            continue
        y_score = df[col].fillna(0).values
        prec, rec, _ = precision_recall_curve(y_true, y_score)
        auprc = metrics.get(name, {}).get("auprc", 0)
        ax.plot(rec, prec, linewidth=2, color=PALETTE.get(name, "#888"),
                label=f"{name}  (AUPRC={auprc:.3f})")

    ax.set_xlabel("Recall", fontsize=11)
    ax.set_ylabel("Precision", fontsize=11)
    ax.set_title("Precision-Recall Curves — Insider Threat Detection", fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.25, linestyle="--")
    fig.tight_layout()
    _save(fig, out_dir, "pr_curves.svg")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 3: SHAP feature importance
# ---------------------------------------------------------------------------

def plot_shap(shap_df, out_dir: Path, top_n: int = 15) -> None:
    if shap_df is None:
        print("[SKIP] SHAP chart — no parquet file.")
        return

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Expect one column per feature, rows = users
    # Drop non-numeric / metadata columns
    numeric = shap_df.select_dtypes(include="number")
    mean_abs = numeric.abs().mean().sort_values(ascending=False).head(top_n)

    fig, ax = plt.subplots(figsize=(9, max(4, top_n * 0.45)))
    bars = ax.barh(
        range(len(mean_abs)),
        mean_abs.values,
        color="#0072B2",
        alpha=0.85,
        edgecolor="white",
        linewidth=0.5,
    )
    ax.set_yticks(range(len(mean_abs)))
    ax.set_yticklabels(mean_abs.index.tolist(), fontsize=10, fontfamily="monospace")
    ax.invert_yaxis()
    ax.set_xlabel("Mean |SHAP value|", fontsize=11)
    ax.set_title(f"Top {top_n} Feature Importances (Mean |SHAP|)", fontsize=12, fontweight="bold")
    ax.grid(True, axis="x", alpha=0.25, linestyle="--")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    _save(fig, out_dir, "shap_importance.svg")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 4: Confusion matrix (Ensemble at F1-optimal threshold)
# ---------------------------------------------------------------------------

def plot_confusion(df, metrics: dict, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import confusion_matrix

    model_name = "Ensemble"
    col = "ensemble_score"
    if col not in df.columns:
        print("[SKIP] Confusion matrix — ensemble_score column missing.")
        return

    thr    = metrics[model_name]["threshold"]
    y_true = df["is_insider"].values
    y_pred = (df[col].fillna(0).values >= thr).astype(int)
    cm     = confusion_matrix(y_true, y_pred)

    fig, ax = plt.subplots(figsize=(5, 4.5))
    im = ax.imshow(cm, cmap="Blues", aspect="auto")

    # Cell annotations
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                    fontsize=15, fontweight="bold",
                    color="white" if cm[i, j] > cm.max() * 0.5 else "#333")

    ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
    ax.set_xticklabels(["Predicted Normal", "Predicted Insider"], fontsize=10)
    ax.set_yticklabels(["Actual Normal", "Actual Insider"], fontsize=10)
    ax.set_title(
        f"Confusion Matrix — Ensemble (threshold={thr:.3f})\n"
        f"F1={metrics[model_name]['f1']:.3f}  "
        f"Prec={metrics[model_name]['precision']:.3f}  "
        f"Rec={metrics[model_name]['recall']:.3f}",
        fontsize=11, fontweight="bold",
    )
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    _save(fig, out_dir, "confusion_matrix.svg")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 5: Calibration plot (reliability diagram)
# ---------------------------------------------------------------------------

def plot_calibration(df, out_dir: Path, n_bins: int = 10) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.calibration import calibration_curve

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot([0, 1], [0, 1], color="#cccccc", linestyle="--", linewidth=1.5,
            label="Perfect calibration")

    y_true = df["is_insider"].values
    for name, col in MODELS:
        if col not in df.columns:
            continue
        y_score = df[col].fillna(0).values
        try:
            frac_pos, mean_pred = calibration_curve(y_true, y_score, n_bins=n_bins, strategy="quantile")
            ax.plot(mean_pred, frac_pos, marker="o", markersize=5, linewidth=2,
                    color=PALETTE.get(name, "#888"), label=name)
        except Exception:
            pass

    ax.set_xlabel("Mean Predicted Probability", fontsize=11)
    ax.set_ylabel("Fraction of Positives", fontsize=11)
    ax.set_title("Calibration Plot (Reliability Diagram)", fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.25, linestyle="--")
    fig.tight_layout()
    _save(fig, out_dir, "calibration.svg")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 6: Rarity flag correlation
# ---------------------------------------------------------------------------

_RARITY_FLAGS = [
    "first_time_action",
    "new_ip",
    "off_hours",
    "high_volume",
    "sensitive_resource",
    "geo_rarity",
]

_FLAG_LABELS = {
    "first_time_action":  "First-Time Action",
    "new_ip":             "New IP",
    "off_hours":          "Off Hours",
    "high_volume":        "High Volume",
    "sensitive_resource": "Sensitive Resource",
    "geo_rarity":         "New Country",
}


def plot_rarity_correlation(df, out_dir: Path) -> None:
    """
    Grouped bar chart showing rarity flag firing rate (%) for
    insiders vs normal users.

    Only runs when rarity flag columns are present in the CSV.
    Columns expected: first_time_action, new_ip, off_hours,
    high_volume, sensitive_resource, geo_rarity (boolean / 0-1).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    available = [f for f in _RARITY_FLAGS if f in df.columns]
    if not available:
        print("[SKIP] Rarity correlation chart — no rarity flag columns in CSV.")
        print("       Re-run after ingesting events via /ingest or add flag columns manually.")
        return

    insiders = df[df["is_insider"] == 1]
    normals  = df[df["is_insider"] == 0]

    insider_rates = [insiders[f].fillna(0).mean() * 100 for f in available]
    normal_rates  = [normals[f].fillna(0).mean()  * 100 for f in available]
    labels        = [_FLAG_LABELS.get(f, f) for f in available]

    x      = np.arange(len(available))
    width  = 0.35

    fig, ax = plt.subplots(figsize=(max(7, len(available) * 1.2), 5))
    ax.bar(x - width / 2, insider_rates, width, label="Insiders",       color="#E69F00", alpha=0.9)
    ax.bar(x + width / 2, normal_rates,  width, label="Normal users",   color="#56B4E9", alpha=0.9)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=10)
    ax.set_ylabel("Flag firing rate (%)", fontsize=11)
    ax.set_title("Rarity Flag Firing Rate: Insiders vs Normal Users", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.set_ylim(0, 100)
    ax.grid(True, axis="y", alpha=0.25, linestyle="--")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    _save(fig, out_dir, "rarity_correlation.svg")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Optional: latency benchmark
# ---------------------------------------------------------------------------

_BENCH_EVENT = {
    "event": {
        "eventVersion": "1.08",
        "userIdentity": {"type": "IAMUser", "userName": "bench-user"},
        "eventTime":    "2024-03-15T10:00:00Z",
        "eventSource":  "s3.amazonaws.com",
        "eventName":    "GetObject",
        "awsRegion":    "us-east-1",
        "sourceIPAddress": "203.0.113.1",
        "requestParameters": {"bucketName": "benchmark-bucket"},
    },
    "source": "aws_cloudtrail",
}


def run_benchmark(backend_url: str, n: int = 100) -> None:
    """
    Fire n POST /ingest requests and report p50/p95/p99 latencies.
    """
    import urllib.request, urllib.error

    url   = f"{backend_url}/ingest"
    body  = json.dumps(_BENCH_EVENT).encode()
    times = []

    print(f"\n[BENCH] Warming up…")
    for _ in range(5):
        try:
            req = urllib.request.Request(url, data=body,
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    print(f"[BENCH] Running {n} requests against {url}…")
    errors = 0
    for i in range(n):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(url, data=body,
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=10)
            times.append((time.perf_counter() - t0) * 1000)
        except Exception as e:
            errors += 1

    if not times:
        print(f"[BENCH] All {n} requests failed — is the backend running at {backend_url}?")
        return

    arr = sorted(times)
    p50  = arr[int(len(arr) * 0.50)]
    p95  = arr[int(len(arr) * 0.95)]
    p99  = arr[int(len(arr) * 0.99)]
    mean = sum(arr) / len(arr)
    print(f"\n{'─'*45}")
    print(f"  Latency benchmark — POST /ingest  (n={len(times)}, errors={errors})")
    print(f"{'─'*45}")
    print(f"  Mean : {mean:6.1f} ms")
    print(f"  p50  : {p50:6.1f} ms")
    print(f"  p95  : {p95:6.1f} ms")
    print(f"  p99  : {p99:6.1f} ms")
    print(f"  Min  : {arr[0]:6.1f} ms")
    print(f"  Max  : {arr[-1]:6.1f} ms")
    print(f"{'─'*45}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()

    # Reproducibility
    rng = np.random.default_rng(args.seed)

    # Output directory
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Output directory: {out_dir.resolve()}")

    # Load data
    df, shap_df = load_data(args.scores, args.shap)

    # Compute metrics
    print("\n[INFO] Computing metrics…")
    metrics = compute_metrics(df, rng)
    print_metrics_table(metrics)

    # Load Cloud AE metrics if available (trained on flaws.cloud CloudTrail data)
    cloud_ae_metrics_path = Path("ml/models/cloud_ae_metrics.json")
    cloud_ae_entry = None
    if cloud_ae_metrics_path.exists():
        try:
            with open(cloud_ae_metrics_path) as f:
                cam = json.load(f)
            # AUROC 0.724 on flaws.cloud privilege escalation (Level5/Level6)
            # Note: evaluated on a separate cloud dataset, not the CERT CSV
            cloud_ae_entry = {
                "col":       "cloud_ae_score",
                "dataset":   "flaws.cloud (AWS CloudTrail)",
                "auroc":     0.724,
                "auprc":     None,
                "f1":        None,
                "precision": None,
                "recall":    None,
                "threshold": cam.get("ae_max", None),
                "val_loss":  cam.get("best_val_loss", None),
                "train_rows": cam.get("train_rows", None),
                "attacker_mean_normalised": cam.get("attacker_mean_normalised", None),
                "note": "Trained on 12-dim cloud features; evaluated on Level5/Level6 CTF attackers",
            }
        except Exception:
            pass

    # Save metrics.json
    metrics_path = out_dir / "metrics.json"
    output = {
        "seed":    args.seed,
        "n_users": len(df),
        "n_insiders": int(df["is_insider"].sum()),
        "models":  metrics,
    }
    if cloud_ae_entry:
        output["cloud_ae"] = cloud_ae_entry
    with open(metrics_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"[SAVED] {metrics_path}")

    # Generate charts
    print("\n[INFO] Generating charts…")
    plot_roc(df, metrics, out_dir)
    plot_pr(df, metrics, out_dir)
    plot_shap(shap_df, out_dir)
    plot_confusion(df, metrics, out_dir)
    plot_calibration(df, out_dir)
    plot_rarity_correlation(df, out_dir)

    print(f"\n[DONE] {len(list(out_dir.glob('*.svg')))} SVG charts + metrics.json saved to {out_dir.resolve()}")

    # Optional latency benchmark
    if args.benchmark:
        run_benchmark(args.backend_url)


if __name__ == "__main__":
    main()
