import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _get(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing setting '{name}' in .env")
    return value


DB_PATH = PROJECT_ROOT / _get("DB_PATH")
API_BASE_URL = _get("API_BASE_URL").rstrip("/")
BASE_CURRENCY = _get("BASE_CURRENCY").upper()
TARGET_CURRENCIES = [
    code.strip().upper()
    for code in _get("TARGET_CURRENCIES").split(",")
    if code.strip()
]
BACKFILL_START_DATE = _get("BACKFILL_START_DATE")
LOG_LEVEL = _get("LOG_LEVEL").upper()

SCHEDULE_TIMEZONE = _get("SCHEDULE_TIMEZONE")
SCHEDULE_HOUR = int(_get("SCHEDULE_HOUR"))
SCHEDULE_MINUTE = int(_get("SCHEDULE_MINUTE"))

SQL_DIR = PROJECT_ROOT / "sql"
LOG_DIR = PROJECT_ROOT / "logs"

REFERENCE_DIR = PROJECT_ROOT / "reference"
VIEWS_DIR = SQL_DIR / "views"