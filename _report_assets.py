# -*- coding: utf-8 -*-
"""Generate architecture diagram + result chart PNGs for the FYP report."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from pathlib import Path

OUT = Path("results/report_png")
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Figure 1 — System architecture (tools + relationships)
# ---------------------------------------------------------------------------
def architecture():
    fig, ax = plt.subplots(figsize=(11, 8.2))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")

    C = {
        "src":   "#1f6feb",  # blue
        "norm":  "#0969da",
        "feat":  "#8250df",  # purple
        "det":   "#cf222e",  # red
        "xai":   "#bf8700",  # gold
        "store": "#1a7f37",  # green
        "ui":    "#0550ae",
        "deploy":"#57606a",
    }

    def box(x, y, w, h, text, color, fs=9, tcolor="white"):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                     boxstyle="round,pad=0.4,rounding_size=1.2",
                     linewidth=0, facecolor=color, alpha=0.95))
        ax.text(x + w/2, y + h/2, text, ha="center", va="center",
                fontsize=fs, color=tcolor, weight="bold", wrap=True)

    def band_label(y, text):
        ax.text(1.5, y, text, ha="left", va="center", fontsize=8.5,
                color="#57606a", style="italic", weight="bold")

    def arrow(x1, y1, x2, y2, color="#57606a"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                     arrowstyle="-|>", mutation_scale=13,
                     linewidth=1.4, color=color, alpha=0.8))

    # ---- Layer 1: data sources ----
    band_label(96, "DATA SOURCES")
    srcs = ["AWS\nCloudTrail", "Azure AD\nSign-in", "Cloudflare\nAccess", "GitHub\nEvents"]
    sx = [12, 33, 54, 75]
    for x, t in zip(sx, srcs):
        box(x, 88, 16, 6.5, t, C["src"], fs=8.5)

    # ---- Layer 2: ingestion + normalization ----
    band_label(80, "INGESTION")
    box(12, 75, 37, 6.5, "FastAPI  POST /ingest\n(Pydantic validation)", C["norm"], fs=9)
    box(54, 75, 37, 6.5, "Normalizer  -  source-specific\nPython parsers (router dispatch)", C["norm"], fs=8.5)
    box(14, 66.5, 72, 5.5, "Unified 8-field schema  {timestamp, user, action, source_ip, bytes, resource, country, source}", C["norm"], fs=7.6)

    # ---- Layer 3: feature engineering ----
    band_label(60, "FEATURES")
    box(12, 55, 37, 7, "CERT daily vectors  (71-dim)\nPandas / NumPy  -  30-day rolling", C["feat"], fs=8.5)
    box(54, 55, 37, 7, "Cloud window features  (12-dim)\nPandas / NumPy  -  per user-day", C["feat"], fs=8.5)

    # ---- Layer 4: detection ----
    band_label(48, "DETECTION")
    box(7, 40, 17, 7.5, "Rule\nScorer", C["det"], fs=8.5)
    box(26, 40, 17, 7.5, "Rarity Scorer\n(6 flags + geo)", C["det"], fs=8.5)
    box(45, 40, 19, 7.5, "Isolation Forest\n(scikit-learn)", C["det"], fs=8.5)
    box(66, 40, 26, 7.5, "Autoencoder x2  (PyTorch)\nCERT AE 71d  +  Cloud AE 12d", C["det"], fs=8.5)
    box(20, 31.5, 60, 5.5, "Final risk score [0,1]  =  Autoencoder reconstruction error   (IF / Rule / Rarity = comparison baselines)", C["det"], fs=7.3)

    # ---- Layer 5: explainability + assist ----
    band_label(27, "EXPLAIN / ASSIST")
    box(14, 21, 33, 6.5, "SHAP  KernelExplainer\nper-alert feature attribution", C["xai"], fs=8.5)
    box(53, 21, 33, 6.5, "LLM Assistant\nGemini / DeepSeek / Groq", C["xai"], fs=8.5)

    # ---- Layer 6: persistence ----
    band_label(15, "PERSISTENCE")
    box(20, 10, 60, 6, "SQLite / PostgreSQL   -   event_store  +  live_scores tables", C["store"], fs=8.5)

    # ---- Layer 7: presentation ----
    band_label(4.5, "PRESENTATION")
    box(20, 0.5, 60, 6, "React / Next.js dashboard   -   Recharts  +  TailwindCSS", C["ui"], fs=8.5)

    # ---- Deployment wrapper (side) ----
    box(93, 14, 6.5, 67, "", C["deploy"], fs=8.5)
    ax.text(96.25, 47, "Docker  +  HuggingFace Space", ha="center", va="center",
            fontsize=8.5, color="white", weight="bold", rotation=90)
    ax.text(96.25, 84, "DEPLOY", ha="center", va="center", fontsize=7.5,
            color="#57606a", style="italic", weight="bold")

    # ---- arrows (vertical flow) ----
    for x in sx:
        arrow(x+8, 88, 30, 81.5)   # sources -> ingest
    arrow(49, 78.2, 54, 78.2)
    arrow(51, 75, 51, 72)          # norm -> schema
    arrow(35, 66.5, 30, 62)        # schema -> CERT feat
    arrow(67, 66.5, 72, 62)        # schema -> cloud feat
    arrow(30, 55, 20, 47.5)        # CERT feat -> detection
    arrow(72, 55, 79, 47.5)        # cloud feat -> detection
    for x in [15, 34, 54, 79]:
        arrow(x, 40, 50, 37)       # detectors -> ensemble
    arrow(45, 31.5, 30, 27.5)      # ensemble -> SHAP
    arrow(60, 31.5, 70, 27.5)      # ensemble -> LLM
    arrow(35, 21, 45, 16)          # SHAP -> store
    arrow(65, 21, 55, 16)          # LLM -> store
    arrow(50, 10, 50, 6.5)         # store -> UI

    ax.text(50, 99.2, "Figure 1.  Cloud-native UEBA Platform — System Architecture and Tool Stack",
            ha="center", va="top", fontsize=11, weight="bold")
    fig.savefig(OUT / "architecture.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("[OK] architecture.png")

# ---------------------------------------------------------------------------
# Result charts from the scores CSV
# ---------------------------------------------------------------------------
def charts():
    import pandas as pd
    from sklearn.metrics import roc_curve, roc_auc_score, confusion_matrix, precision_recall_curve, f1_score

    df = pd.read_csv("data/processed/user_scores_v4.csv")
    y = df["is_insider"].values
    models = [("Autoencoder (final)","ae_score","#0072B2"),
              ("Weighted Avg (IF+AE)","wa_score","#E69F00"),
              ("Isolation Forest","if_score","#56B4E9"),
              ("Rule-based","rule_score","#009E73")]

    # ROC
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    ax.plot([0,1],[0,1],"--",color="#cccccc",lw=1,label="Chance")
    for name,col,c in models:
        if col not in df: continue
        s = df[col].fillna(0).values
        fpr,tpr,_ = roc_curve(y,s)
        ax.plot(fpr,tpr,lw=2,color=c,label=f"{name} (AUROC={roc_auc_score(y,s):.3f})")
    ax.set_xlabel("False Positive Rate"); ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curves — Insider Threat Detection (CERT r4.2)", weight="bold", fontsize=11)
    ax.legend(loc="lower right", fontsize=8.5); ax.grid(alpha=0.25, ls="--")
    fig.tight_layout(); fig.savefig(OUT/"roc.png", dpi=200, facecolor="white"); plt.close(fig)
    print("[OK] roc.png")

    # Confusion matrix for the Autoencoder (final detector) at F1-opt threshold
    s = df["ae_score"].fillna(0).values
    prec,rec,thr = precision_recall_curve(y,s)
    f1s = np.where((prec+rec)>0, 2*prec*rec/(prec+rec), 0)
    bi = int(np.argmax(f1s[:-1])); t = thr[bi]
    cm = confusion_matrix(y, (s>=t).astype(int))
    fig, ax = plt.subplots(figsize=(4.8,4.2))
    im = ax.imshow(cm, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(j,i,str(cm[i,j]),ha="center",va="center",fontsize=15,
                    weight="bold",color="white" if cm[i,j]>cm.max()*0.5 else "#333")
    ax.set_xticks([0,1]); ax.set_yticks([0,1])
    ax.set_xticklabels(["Pred. Normal","Pred. Insider"]); ax.set_yticklabels(["Normal","Insider"])
    ax.set_title(f"Confusion Matrix — Autoencoder (thr={t:.3f})\nF1={f1s[bi]:.3f}  P={prec[bi]:.3f}  R={rec[bi]:.3f}",
                 weight="bold", fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout(); fig.savefig(OUT/"confusion.png", dpi=200, facecolor="white"); plt.close(fig)
    print("[OK] confusion.png")

    # SHAP importance
    try:
        sh = pd.read_parquet("data/processed/shap_values_v4 (2).parquet")
        num = sh.select_dtypes(include="number")
        ma = num.abs().mean().sort_values(ascending=False).head(12)
        fig, ax = plt.subplots(figsize=(7.5,5))
        ax.barh(range(len(ma)), ma.values, color="#0072B2", alpha=0.88, edgecolor="white")
        ax.set_yticks(range(len(ma))); ax.set_yticklabels(ma.index, fontsize=9, family="monospace")
        ax.invert_yaxis(); ax.set_xlabel("Mean |SHAP value|")
        ax.set_title("Top 12 Feature Importances (Mean |SHAP|)", weight="bold", fontsize=11)
        ax.grid(axis="x", alpha=0.25, ls="--")
        for sp in ["top","right"]: ax.spines[sp].set_visible(False)
        fig.tight_layout(); fig.savefig(OUT/"shap.png", dpi=200, facecolor="white"); plt.close(fig)
        print("[OK] shap.png")
    except Exception as e:
        print("[skip] shap:", e)

if __name__ == "__main__":
    architecture()
    charts()
    print("DONE ->", OUT.resolve())
