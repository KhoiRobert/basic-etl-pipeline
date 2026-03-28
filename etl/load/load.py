"""Load DataFrames into PostgreSQL."""

from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from etl.errors import LoadError

logger = logging.getLogger(__name__)


def _check_connection(engine: Engine) -> None:
    """Verify the database is reachable.

    Raises:
        LoadError: DB is not reachable.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        raise LoadError(
            f"Cannot reach the database. Is Postgres running and are DB_HOST/DB_PORT correct?\n"
            f"  Detail: {exc.__cause__ or exc}"
        ) from exc


def load(df: pd.DataFrame, table_name: str, engine: Engine) -> int:
    """Write ``df`` to ``table_name``. Returns rows loaded.

    Raises:
        LoadError: DB is unreachable or the write fails.
    """
    if df.empty:
        logger.warning("DataFrame is empty; skipping load to %s", table_name)
        return 0

    _check_connection(engine)

    n = len(df)
    try:
        df.to_sql(table_name, engine, if_exists="replace", index=False)
    except SQLAlchemyError as exc:
        raise LoadError(f"Failed to write {n} rows to '{table_name}': {exc}") from exc

    logger.info("Loaded %d rows into %s", n, table_name)
    return n


def load_all(
    tables: list[tuple[pd.DataFrame, str]],
    engine: Engine,
) -> list[int]:
    """Write multiple DataFrames in a **single transaction**.

    Either every table commits or all roll back together.

    Raises:
        LoadError: DB is unreachable or any write fails.
    """
    _check_connection(engine)

    counts: list[int] = []
    with engine.begin() as conn:
        for df, table_name in tables:
            if df.empty:
                logger.warning("DataFrame is empty; skipping %s", table_name)
                counts.append(0)
                continue
            n = len(df)
            try:
                df.to_sql(table_name, conn, if_exists="replace", index=False)
            except SQLAlchemyError as exc:
                raise LoadError(
                    f"Failed to write to '{table_name}': {exc}. All tables rolled back."
                ) from exc
            logger.info("Loaded %d rows into %s", n, table_name)
            counts.append(n)

    return counts
