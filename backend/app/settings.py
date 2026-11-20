from __future__ import annotations
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_BUCKET_NAME = os.getenv("SUPABASE_BUCKET_NAME", "cu-photo-images")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:5174",
    ).split(",") if origin.strip()
]
REQUIRE_APP_CHECK = env_bool("REQUIRE_APP_CHECK", False)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(3 * 1024 * 1024)))
MAX_PHOTOS_PER_SAMPLE = int(os.getenv("MAX_PHOTOS_PER_SAMPLE", "8"))
MAX_PREDICTIONS_PER_MINUTE_PER_PROCESS = int(os.getenv("MAX_PREDICTIONS_PER_MINUTE_PER_PROCESS", "6"))
MODEL_STORAGE_PREFIX = os.getenv("MODEL_STORAGE_PREFIX", "models")


def validate_firebase_config() -> None:
    if not PROJECT_ID:
        raise RuntimeError("FIREBASE_PROJECT_ID is not configured")


def validate_supabase_config() -> None:
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is not configured")
    if not SUPABASE_BUCKET_NAME:
        raise RuntimeError("SUPABASE_BUCKET_NAME is not configured")
    if not SUPABASE_SECRET_KEY or SUPABASE_SECRET_KEY == "PASTE_YOUR_SECRET_KEY_HERE":
        raise RuntimeError("SUPABASE_SECRET_KEY is not configured")
