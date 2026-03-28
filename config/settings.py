"""Application settings and database engine factory."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env")

RAW_DIR = _BASE_DIR / "data" / "raw"
PROCESSED_DIR = _BASE_DIR / "data" / "processed"
FAILED_DIR = _BASE_DIR / "data" / "failed"

for _dir in (RAW_DIR, PROCESSED_DIR, FAILED_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

_REQUIRED_ENV = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")


def get_engine() -> Engine:
    """Return a SQLAlchemy engine using credentials from the environment.

    Raises:
        ConfigError: one or more required environment variables are missing.
    """
    from etl.errors import ConfigError  # local import to avoid circular deps

    missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        raise ConfigError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Copy .env.example to .env and fill in the values."
        )

    host = os.environ["DB_HOST"]
    port = os.environ["DB_PORT"]
    name = os.environ["DB_NAME"]
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    u = quote_plus(user)
    p = quote_plus(password)
    url = f"postgresql+psycopg2://{u}:{p}@{host}:{port}/{name}"
    return create_engine(url, future=True)
