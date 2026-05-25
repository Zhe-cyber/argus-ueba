# ============================================================
# Root Dockerfile — Hugging Face Spaces (Docker SDK)
#
# Exposes port 7860 (HF default).
# Data + model files are NOT in the GitHub repo (too large).
# After first deploy, add them directly to the HF Space repo:
#
#   git lfs install
#   git lfs track "*.pt" "*.pkl" "*.parquet" "*.csv"
#   # push ml/models/ and data/processed/ to the HF Space git repo
#
# Alternatively set HF_MODEL_REPO env var (HF Space secret) to a
# HuggingFace Hub dataset/model repo that contains those files —
# start.sh will download them at container startup.
# ============================================================

FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# PyTorch CPU-only — installed first so it can be cached separately.
# CPU build is ~250 MB vs ~2 GB for CUDA. Sufficient for inference.
RUN pip install --no-cache-dir \
        torch \
        --index-url https://download.pytorch.org/whl/cpu

# Remaining Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir huggingface_hub

# Application source
COPY backend/  ./backend/
COPY scripts/  ./scripts/

# Create expected directories — files are populated either by:
#   (a) git-lfs files committed directly to the HF Space repo, or
#   (b) the HF_MODEL_REPO download in start.sh
RUN mkdir -p data/processed data/events ml/models

# Startup script
COPY start.sh ./start.sh
RUN chmod +x ./start.sh

# HuggingFace Spaces expects port 7860
EXPOSE 7860
ENV PORT=7860

CMD ["./start.sh"]
