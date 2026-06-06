# -*- coding: utf-8 -*-
"""Build a logo-rich system-architecture diagram for the poster.

Uses the user-supplied real tool logos in ./logo, strips their white
background to transparent, and lays them out as white 'chips' in a layered
ingestion -> features -> detection -> explain -> store -> UI flow.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
from scipy import ndimage
import numpy as np

LOGO_DIR = "logo"
OUT = "results/report_png/architecture_logos.png"

# diagram slug -> file in ./logo
FILES = {
    "amazonwebservices": "aws.jpg",
    "microsoftazure":    "entra id (azure).png",
    "cloudflare":        "cloudflare.png",
    "github":            "github.png",
    "fastapi":           "fast API.png",
    "python":            "python.png",
    "pandas":            "pandas.png",
    "numpy":             "numpy.png",
    "scikitlearn":       "Scikit_learn.png",
    "pytorch":           "pytorch.png",
    "googlegemini":      "Google_Gemini.png",
    "sqlite":            "SQLite.png",
    "postgresql":        "Postgresql.png",
    "react":             "React.png",
    "nextdotjs":         "Nextjs.png",
    "tailwindcss":       "Tailwind_CSS.png",
    "docker":            "Docker_Logo.png",
    "huggingface":       "hugging face.png",
}

def load_logo(path):
    """Load -> RGBA, remove the border-connected near-white background, autocrop."""
    arr = np.array(Image.open(path).convert("RGBA"))
    rgb = arr[:, :, :3].astype(int)
    alpha = arr[:, :, 3]
    near_white = ((rgb[:, :, 0] >= 228) & (rgb[:, :, 1] >= 228) &
                  (rgb[:, :, 2] >= 228) & (alpha > 10))
    if near_white.any():
        lbl, _ = ndimage.label(near_white)
        border = set(lbl[0, :]) | set(lbl[-1, :]) | set(lbl[:, 0]) | set(lbl[:, -1])
        border.discard(0)
        if border:
            arr[np.isin(lbl, list(border)), 3] = 0
    ys, xs = np.where(arr[:, :, 3] > 10)
    if len(xs):
        arr = arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return arr

print("Loading logos ...")
IMG = {}
for slug, fname in FILES.items():
    p = os.path.join(LOGO_DIR, fname)
    if os.path.exists(p):
        IMG[slug] = load_logo(p)
        print("  [ok]", slug, IMG[slug].shape[1], "x", IMG[slug].shape[0])
    else:
        print("  [MISSING]", slug, fname)

# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(13, 12.8))
ax.set_xlim(0, 130); ax.set_ylim(0, 128); ax.axis("off")
PXU = fig.get_size_inches()[0] * fig.dpi / 130.0  # px per x-unit (display)

LAYER = {
    "src":   "#1f6feb", "norm": "#0969da", "feat": "#8250df",
    "det":   "#cf222e", "xai":  "#bf8700", "store": "#1a7f37",
    "ui":    "#0550ae", "deploy": "#57606a",
}

def logo_at(cx, cy, slug, target_h, max_w=None):
    a = IMG.get(slug)
    if a is None:
        return
    h_px, w_px = a.shape[0], a.shape[1]
    zoom = (target_h * PXU) / h_px
    if max_w:                                  # cap wide word-mark logos
        zoom = min(zoom, (max_w * PXU) / w_px)
    ab = AnnotationBbox(OffsetImage(a, zoom=zoom), (cx, cy),
                        frameon=False, box_alignment=(0.5, 0.5))
    ax.add_artist(ab)

def chip(cx, cy, w, h, edge, slug, label, logo_h=3.0, fs=8.5):
    ax.add_patch(FancyBboxPatch((cx - w/2, cy - h/2), w, h,
                 boxstyle="round,pad=0.3,rounding_size=1.3",
                 linewidth=1.4, edgecolor=edge, facecolor="white"))
    if slug:
        logo_at(cx, cy + h*0.20, slug, logo_h, max_w=w*0.46)
        ax.text(cx, cy - h*0.30, label, ha="center", va="center", fontsize=fs,
                color="#222228", weight="bold", linespacing=0.95)
    else:
        ax.text(cx, cy, label, ha="center", va="center", fontsize=fs,
                color="#222228", weight="bold", linespacing=0.95)

def band(y, text):
    ax.text(0.5, y, text, ha="left", va="center", fontsize=9,
            color="#57606a", style="italic", weight="bold", linespacing=0.95)

def bar(cx, cy, w, h, color, text, fs=8.0, tcolor="white"):
    ax.add_patch(FancyBboxPatch((cx - w/2, cy - h/2), w, h,
                 boxstyle="round,pad=0.3,rounding_size=1.0",
                 linewidth=0, facecolor=color, alpha=0.95))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
            color=tcolor, weight="bold")

def arrow(x1, y1, x2, y2, color="#7a818a"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                 mutation_scale=20, linewidth=2.4, color=color, alpha=0.95))

# ---- Layer 1: data sources ----
band(117, "DATA\nSOURCES")
src = [("amazonwebservices","AWS\nCloudTrail"), ("microsoftazure","Azure AD\nSign-in"),
       ("cloudflare","Cloudflare\nAccess"), ("github","GitHub\nEvents")]
sx = [23, 48, 73, 98]
for x,(slug,lab) in zip(sx, src):
    chip(x, 117, 22, 11, LAYER["src"], slug, lab)

# ---- Layer 2: ingestion ----
band(102, "INGESTION")
chip(43, 102, 32, 11, LAYER["norm"], "fastapi", "FastAPI  ·  POST /ingest")
chip(83, 102, 32, 11, LAYER["norm"], "python", "Normalizer  ·  parsers")
bar(60, 89.5, 88, 6, LAYER["norm"],
    "Unified 8-field schema   { timestamp, user, action, source_ip, bytes, resource, country, source }")

# ---- Layer 3: features ----
band(77, "FEATURES")
chip(43, 77, 36, 11, LAYER["feat"], "pandas", "CERT vectors  (71-dim)\n30-day rolling")
chip(83, 77, 36, 11, LAYER["feat"], "numpy", "Cloud features  (12-dim)\nper user-day")

# ---- Layer 4: detection ----
band(61.5, "DETECTION")
chip(21, 61.5, 19, 12, LAYER["det"], None, "Rule\nScorer")
chip(43, 61.5, 19, 12, LAYER["det"], None, "Rarity Scorer\n6 flags + geo")
chip(66, 61.5, 21, 12, LAYER["det"], "scikitlearn", "Isolation Forest")
chip(92, 61.5, 27, 12, LAYER["det"], "pytorch", "Autoencoder ×2\nCERT 71d · Cloud 12d")
bar(60, 49, 96, 6, LAYER["det"],
    "Final risk score [0,1] = Autoencoder reconstruction error    (IF / Rule / Rarity = baselines)")

# ---- Layer 5: explain / assist ----
band(36, "EXPLAIN /\nASSIST")
chip(43, 36, 34, 12, LAYER["xai"], None, "SHAP KernelExplainer\nper-alert attribution")
chip(83, 36, 34, 12, LAYER["xai"], "googlegemini", "LLM Assistant\nGemini · DeepSeek · Groq")

# ---- Layer 6: persistence ----
band(20.5, "STORE")
chip(43, 20.5, 22, 11, LAYER["store"], "sqlite", "SQLite")
chip(83, 20.5, 24, 11, LAYER["store"], "postgresql", "PostgreSQL")
ax.text(63, 20.5, "event_store\n+ live_scores", ha="center", va="center",
        fontsize=7.6, color="#555560", weight="bold", linespacing=0.95)

# ---- Layer 7: presentation ----
band(5.5, "UI")
chip(34, 5.5, 19, 11, LAYER["ui"], "react", "React")
chip(60, 5.5, 21, 11, LAYER["ui"], "nextdotjs", "Next.js")
chip(86, 5.5, 21, 11, LAYER["ui"], "tailwindcss", "Tailwind")

# ---- Deployment side bar ----
ax.add_patch(FancyBboxPatch((119, 1), 10, 121,
             boxstyle="round,pad=0.3,rounding_size=1.4",
             linewidth=0, facecolor=LAYER["deploy"], alpha=0.9))
ax.text(124, 117, "DEPLOY", ha="center", va="center", fontsize=8,
        color="white", style="italic", weight="bold")
logo_at(124, 86, "docker", 5.0, max_w=5.0)
ax.text(124, 76, "Docker", ha="center", va="center", fontsize=8,
        color="white", weight="bold")
logo_at(124, 34, "huggingface", 4.6, max_w=4.6)
ax.text(124, 24, "HF Space", ha="center", va="center", fontsize=8,
        color="white", weight="bold")

# ---- flow arrows (central spine) ----
for x in sx:
    arrow(x, 111.0, 60, 108.0)
arrow(60, 96.2, 60, 92.8)
arrow(60, 86.2, 60, 82.8)
for x in (43, 83):
    arrow(x, 71.2, x, 67.8)
arrow(43, 55.2, 54, 52.2)
arrow(92, 55.2, 66, 52.2)
arrow(43, 45.8, 43, 42.2)
arrow(83, 45.8, 83, 42.2)
arrow(43, 29.8, 43, 26.2)
arrow(83, 29.8, 83, 26.2)
arrow(60, 14.8, 60, 11.2)

ax.text(65, 126.5, "Cloud-Native UEBA Platform  —  System Architecture & Tool Stack",
        ha="center", va="top", fontsize=13, weight="bold", color="#1a1a2e")

fig.savefig(OUT, dpi=200, bbox_inches="tight", facecolor="white")
plt.close(fig)
print("WROTE", OUT)
