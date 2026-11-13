---
title: Argus UEBA
emoji: 🔍
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
license: mit
pinned: false
---

# Argus — Multi-Cloud UEBA for Insider Threat Detection

**FYP · Universiti Malaya · Supervisor: Dr. Firdaus Sahran**

> *Argus Panoptes — the hundred-eyed giant who sees everything.*

---

## Overview

**Argus** is a User and Entity Behaviour Analytics (UEBA) platform that detects insider threats and cloud-based attacks by modelling normal user behaviour across multiple sources and flagging anomalies in real time.

Logs from AWS CloudTrail, Microsoft Entra ID, Cloudflare Access, GitHub activity events and the CMU CERT r4.2 benchmark can be normalized into an 8-field schema. Parser support does not imply a configured live connector for every provider.

- **Autoencoder detector**: a 71-feature CERT model and a separate 12-feature cloud model. IF and AE+IF remain evaluation baselines. Historical CERT results are **F1 = 0.787, AUROC = 0.976** in their recorded evaluation setup; these are not live cloud accuracy measurements.
- **Six supporting rarity signals**: first-time action, new IP, off-hours, high volume, sensitive resource and geo-rarity, subject to available fields and history.

The React/Next.js dashboard supports alert review and investigation. The existing CERT SHAP generation path explains the IF baseline, while seeded cloud views use residual diagnostics. Neither establishes faithful explanations of every live AE score. Live mode disables those explanation/AI routes pending a verified AE explanation path.

### Cloud-only monitoring (first competition implementation slice)

Set `ARGUS_MODE=live` before starting the backend. Live mode starts without CERT
score CSV, SHAP parquet or daily-feature files, and excludes benchmark users and
offline score-only seeds. It accepts supported cloud event payloads only.

```powershell
$env:ARGUS_MODE = 'live'
$env:DATABASE_URL = 'sqlite-local'
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Use a **fresh, dedicated database** for live monitoring. Local live SQLite and
investigations use `data/live/` (override with LIVE_STATE_DIR), separate from the
tracked benchmark investigation records. In PostgreSQL, use a separate live
database. Provider/account identity scoping and migration of
mixed historical data are separate workstreams.

Install the cloud model/scaler (`ml/models/cloud_ae_v1.pt`, `cloud_scaler_v1.pkl`)
from your verified model artifacts to enable inference. If scoring is unavailable,
the account has a null AE score and **Unknown** risk, not a benign/Low result.
Existing thresholds remain provisional; they have not been calibrated to your tenant.

`GET /` and `/stats` report `application_mode`. Live user ground-truth fields and
the insider count are null. `ARGUS_MODE=benchmark` loads the historical benchmark;
`ARGUS_MODE=demo` loads the demo fixture files. If ARGUS_MODE is unset, the legacy
DEMO_MODE selection is preserved. Explicit ARGUS_MODE takes precedence.

This is a local development workflow. Authentication, collector credentials,
provider-account identity resolution and faithful live AE explanations remain
release blockers. Do not expose this slice publicly with real logs. A supported
payload shape does not prove a genuine provider event; collector authentication
and source provenance still need implementation.

---

## Quick Start

```bash
# 1. Start the database (from project root)
docker compose up db -d

# 2. Run the backend — always from the project root so package imports resolve
pip install -r backend/requirements.txt
DEMO_MODE=true uvicorn backend.main:app --reload --port 8000
# With real data:  uvicorn backend.main:app --reload --port 8000

# 3. Run the frontend (Node 18+, in a second terminal)
cd frontend && npm install && npm run dev   # → http://localhost:3000
```

> **Important:** run `uvicorn` from the **project root** (not inside `backend/`).
> `main.py` imports `from backend.config import …` which requires the `backend`
> package to be on `sys.path`. Running from inside `backend/` breaks this.

API docs available at **http://localhost:8000/docs** once the backend is running.

### Docker (full stack)

```bash
# Builds and starts db + backend + frontend
docker compose --profile full up --build
```

### Generate demo data (once you have real scored outputs)

```bash
# Writes demo/demo_scores.csv and demo/demo_shap.parquet
python scripts/anonymise_demo.py --n 200

# Then restart the backend in demo mode:
DEMO_MODE=true uvicorn backend.main:app --reload --port 8000
```

---

## System Architecture

```
Raw Logs
  ├── AWS CloudTrail  ──┐
  ├── Azure AD         ─┤
  ├── CERT logon        ├──► Normalizer ──► Feature Engineering
  ├── CERT file         │     (8-field           │
  ├── CERT device       │     unified schema)     │
  ├── CERT email        │                        ▼
  └── CERT http       ──┘              ┌─────────────────┐
                                       │  Model Ensemble  │
                                       │  AE · IF · Rule  │
                                       │  Weighted Avg    │
                                       └────────┬─────────┘
                                                │
                                          SHAP Values
                                                │
                                      ┌─────────▼──────────┐
                                      │  FastAPI Backend    │
                                      │  /users  /stats     │
                                      │  /ingest /shap      │
                                      └─────────┬───────────┘
                                                │
                                      ┌─────────▼──────────┐
                                      │  Next.js Dashboard  │
                                      │  SOC Analyst View   │
                                      │  + Live Demo Page   │
                                      └────────────────────┘
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/` | Health check — version, mode, user count |
| `GET`  | `/users` | Paginated user list with risk badges. Query: `risk`, `limit`, `offset` |
| `GET`  | `/users/{id}` | Full user detail with all model scores and top-5 SHAP features |
| `GET`  | `/users/{id}/shap` | Complete SHAP breakdown (top 10 features) and plain-English reason |
| `GET`  | `/stats` | Dataset summary: total users, risk distribution, insider count |
| `POST` | `/ingest` | Accept raw log event + source, return normalised 8-field schema |

All responses are validated against Pydantic schemas. Interactive docs: `http://localhost:8000/docs`

---

## Screenshots

> _Add after the frontend is running._
>
> Suggested captures:
> - Dashboard home page (stats bar + risk table)
> - User detail page (score cards + SHAP waterfall chart)
> - Live normalisation demo page (side-by-side panels)

---

## Dataset Setup

This project uses the **CMU CERT Insider Threat Dataset r4.2**.

1. Request access at https://resources.sei.cmu.edu/library/asset-view.cfm?assetid=508099
2. Extract the CSV files into `data/raw/`:
   ```
   data/raw/
   ├── logon.csv
   ├── file.csv
   ├── device.csv
   ├── email.csv
   ├── http.csv
   └── LDAP/
   ```
3. Run the preprocessing pipeline:
   ```bash
   python scripts/preprocess.py          # builds data/processed/
   python scripts/train.py               # trains models → ml/models/
   python scripts/score.py               # writes user_scores_v4.csv + shap_values_v4.parquet
   ```
4. Start the backend — it will load the processed files automatically.

**Demo mode** (no dataset required): set `DEMO_MODE=true` in `.env.local`. The backend will load `demo/demo_scores.csv` and `demo/demo_shap.parquet` instead.

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **ML pipeline** | Python 3.11 · PyTorch · scikit-learn · SHAP · pandas · NumPy |
| **Backend API** | FastAPI · Uvicorn · Pydantic v2 · PyArrow |
| **Frontend** | React 18 · Next.js 14 · Tailwind CSS · Recharts |
| **Database** | PostgreSQL 15 |
| **Infrastructure** | Docker · Docker Compose |
| **Testing** | pytest · FastAPI TestClient |

---

## Evaluation Results

> _Fill in from `CLAUDE_CONTEXT.md` once available._

### Model Comparison (CERT r4.2 test split)

| Model | Precision | Recall | F1 | AUROC |
|-------|-----------|--------|----|-------|
| Autoencoder (AE) | — | — | **0.787** | **0.976** |
| Isolation Forest | — | — | — | — |
| Rule-based | — | — | — | — |
| Ensemble (WA) | — | — | — | — |

### Risk Threshold (percentile-based)

| Tier | Threshold | Description |
|------|-----------|-------------|
| High | ≥ p90 | Immediate investigation recommended |
| Medium | ≥ p70 | Monitor and review activity history |
| Low | < p70 | Within normal behavioural range |

---

## Project Structure

```
fyp-ueba/
├── backend/
│   ├── config.py         # env-var configuration
│   ├── loader.py         # DataStore singleton (CSV + parquet)
│   ├── main.py           # FastAPI app + all endpoints
│   ├── models.py         # Pydantic response schemas
│   ├── normalizer.py     # Multi-cloud log normalisation layer
│   └── tests/
│       ├── test_api.py         # 32 endpoint tests
│       └── test_normalizer.py  # 25 parser tests
├── frontend/
│   ├── pages/
│   │   ├── index.js      # SOC analyst dashboard
│   │   ├── demo.js       # Live normalisation demo
│   │   └── users/[id].js # User detail + SHAP chart
│   ├── lib/api.js        # Typed fetch wrappers
│   └── styles/globals.css
├── ml/models/            # Trained model artefacts (gitignored)
├── data/
│   ├── raw/              # CERT CSV files (gitignored)
│   └── processed/        # Feature-engineered outputs (gitignored)
├── demo/                 # Pre-computed demo data (committed)
├── scripts/              # Preprocessing + training scripts
├── docker-compose.yml
└── .env.example
```

---

## Running Tests

```bash
# All tests (57 total)
pytest backend/tests/ -v

# Normaliser only
pytest backend/tests/test_normalizer.py -v

# API endpoints only
pytest backend/tests/test_api.py -v
```

---

## License

MIT
