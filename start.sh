#!/bin/bash
# start.sh — container entrypoint for HuggingFace Spaces
#
# If HF_MODEL_REPO is set (as a Space Secret), downloads model + data files
# from that HuggingFace Hub repo before starting the server.
# Otherwise assumes files are already present (git-lfs in the Space repo).

set -e

if [ -n "$HF_MODEL_REPO" ]; then
    echo "[startup] Downloading model/data files from HF Hub: $HF_MODEL_REPO"
    python - <<'PYEOF'
import os, shutil
from huggingface_hub import snapshot_download

repo  = os.environ["HF_MODEL_REPO"]
token = os.environ.get("HF_TOKEN")   # needed for private repos

local = snapshot_download(repo_id=repo, token=token)
print(f"[startup] Snapshot at: {local}")

targets = [
    ("ml/models/autoencoder_v4.pt",              "ml/models/autoencoder_v4.pt"),
    ("ml/models/scaler_v4.pkl",                  "ml/models/scaler_v4.pkl"),
    ("data/processed/user_scores_v4.csv",        "data/processed/user_scores_v4.csv"),
    ("data/processed/shap_values_v4.parquet",    "data/processed/shap_values_v4.parquet"),
    ("data/processed/daily_features_v4.parquet", "data/processed/daily_features_v4.parquet"),
]

for src_rel, dst in targets:
    src = os.path.join(local, src_rel)
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f"[startup]   copied {src_rel}")
    else:
        print(f"[startup]   MISSING in hub repo: {src_rel} (app will degrade gracefully)")
PYEOF
else
    echo "[startup] HF_MODEL_REPO not set — using files already in the container."
fi

echo "[startup] Starting uvicorn on port ${PORT:-7860} ..."
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-7860}"
