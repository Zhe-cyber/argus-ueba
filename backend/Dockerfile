# backend/Dockerfile
# Multi-stage build: keep the final image lean by not shipping build tools.

# ── Stage 1: dependency builder ──────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies (needed to compile some Python extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime image ───────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Runtime system deps (libpq for psycopg2, if needed later)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
# Note: we copy the whole project root so `from backend.xxx import` works.
COPY backend/ ./backend/
COPY .env.example .env.example

# Create non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
 && chown -R appuser:appuser /app
USER appuser

# Expose the default port (can be overridden via PORT env var)
EXPOSE 8000

# Health check — FastAPI returns 200 on GET /
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
