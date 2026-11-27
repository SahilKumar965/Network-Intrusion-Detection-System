"""Settings from environment variables (loaded from .env if present). No secrets in code."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
MODEL_PATH = Path(os.environ.get("MODEL_PATH", ROOT / "ml" / "artifacts" / "model.joblib"))
METRICS_PATH = Path(os.environ.get("METRICS_PATH", ROOT / "ml" / "artifacts" / "metrics.json"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "120"))
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
