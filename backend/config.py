import os
from pathlib import Path

# Load .env if present (development convenience — production uses real env vars)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

BASE_DIR   = Path(__file__).resolve().parent.parent
DEMO_MODE  = os.getenv('DEMO_MODE', 'false').lower() == 'true'
DATA_DIR   = Path(os.getenv('DATA_DIR', str(BASE_DIR / 'data' / 'processed')))
DEMO_DIR   = Path(os.getenv('DEMO_DIR', str(BASE_DIR / 'demo')))
DB_URL     = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/ueba')
PORT       = int(os.getenv('PORT', '8000'))

# File paths
if DEMO_MODE:
    SCORES_PATH          = DEMO_DIR / 'demo_scores.csv'
    SHAP_PATH            = DEMO_DIR / 'demo_shap.parquet'
    DAILY_FEATURES_PATH  = DEMO_DIR / 'demo_daily_features.parquet'
else:
    SCORES_PATH          = DATA_DIR / 'user_scores_v4.csv'
    SHAP_PATH            = DATA_DIR / 'shap_values_v4.parquet'
    DAILY_FEATURES_PATH  = DATA_DIR / 'daily_features_v4.parquet'
