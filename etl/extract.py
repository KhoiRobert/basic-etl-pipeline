"""CSV extraction."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def extract(filepath: str | Path) -> pd.DataFrame:
    """Read a CSV file into a DataFrame."""
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")

    try:
        df = pd.read_csv(path, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="latin-1")

    df.columns = df.columns.str.strip()
    n = len(df)
    logger.info("Extracted %s rows from %s", n, path)
    return df
