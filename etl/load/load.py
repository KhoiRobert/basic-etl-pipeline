"""Load DataFrames into PostgreSQL."""

from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def load(df: pd.DataFrame, table_name: str, engine: Engine) -> int:
    """Write ``df`` to ``table_name`` using pandas ``to_sql``. Returns rows loaded."""
    if df.empty:
        logger.warning("DataFrame is empty; skipping load to %s", table_name)
        return 0

    n = len(df)
    df.to_sql(table_name, engine, if_exists="replace", index=False)
    logger.info("Loaded %s rows into %s", n, table_name)
    return n
