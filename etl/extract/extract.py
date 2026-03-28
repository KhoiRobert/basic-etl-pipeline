"""CSV extraction."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from etl.errors import ExtractError

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"salary"}


def extract(filepath: str | Path) -> pd.DataFrame:
    """Read a CSV file into a DataFrame.

    Raises:
        FileNotFoundError: path does not exist or is not a file.
        ExtractError: file is empty, unreadable, or missing required columns.
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")

    try:
        df = pd.read_csv(path, encoding="utf-8")
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(path, encoding="latin-1")
        except Exception as exc:
            raise ExtractError(f"Cannot decode {path}: {exc}") from exc
    except Exception as exc:
        raise ExtractError(f"Cannot parse {path}: {exc}") from exc

    df.columns = df.columns.str.strip()

    if df.empty:
        raise ExtractError(f"CSV is empty (no rows): {path}")

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ExtractError(
            f"CSV is missing required column(s): {', '.join(sorted(missing))} "
            f"(found: {', '.join(df.columns)})"
        )

    n = len(df)
    logger.info("Extracted %s rows from %s", n, path)
    return df
