"""Load DataFrames into PostgreSQL.

Full-load strategy per ``load_all()``:
    1. DROP any table whose columns no longer match the DataFrame (schema drift).
    2. TRUNCATE remaining existing tables in **child -> parent** order (respects FK).
    3. INSERT in **parent -> child** order (satisfies FK on insert).

All three phases run inside a single ``engine.begin()`` transaction, so either
every table commits or everything rolls back together.

Why TRUNCATE instead of pandas ``if_exists='replace'``?
    ``to_sql(if_exists='replace')`` issues DROP TABLE then CREATE TABLE, which:
    - destroys all FK constraints, indexes, and CHECK constraints,
    - leaves a window where the table does not exist (bad for live systems).
    TRUNCATE keeps the schema intact and is transactional in PostgreSQL.
"""

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
        # Avoid str(exc): may include connection details.
        raise LoadError(
            "Cannot reach the database. Is Postgres running and are DB_HOST/DB_PORT correct?"
        ) from exc


def _has_table(conn, table_name: str) -> bool:
    """Live existence check -- bypasses SQLAlchemy inspector cache."""
    result = conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table_name},
    )
    return result.fetchone() is not None


def _columns_in_db(conn, table_name: str) -> set[str]:
    """Return column names currently in the table (live query, no cache)."""
    result = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table_name},
    )
    return {row[0] for row in result}


def _drop_schema_mismatches(
    tables: list[tuple[pd.DataFrame, str]],
    conn,
) -> None:
    """Drop tables whose DB columns do not cover the DataFrame columns.

    Processed in **reverse** (child -> parent) order so FK constraints
    do not block the DROP.  CASCADE cleans up dependant tables too.
    """
    for df, table_name in reversed(tables):
        if not _has_table(conn, table_name):
            continue
        missing = set(df.columns) - _columns_in_db(conn, table_name)
        if missing:
            logger.warning(
                "Schema mismatch: %d column(s) in DataFrame not present in DB. "
                "Dropping and recreating the table.",
                len(missing),
            )
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))


def _truncate_tables(table_names: list[str], conn) -> None:
    """TRUNCATE existing tables in the given order (caller supplies child-first order)."""
    for name in table_names:
        if _has_table(conn, name):
            conn.execute(text(f'TRUNCATE TABLE "{name}"'))
            logger.debug("Truncated existing table before reload")


def load_all(
    tables: list[tuple[pd.DataFrame, str]],
    engine: Engine,
) -> list[int]:
    """Write multiple DataFrames in a single transaction.

    Pass tables in **parent-first** order (e.g. ``records`` before
    ``job_locations``).  The function automatically truncates in the reverse
    order and inserts in the supplied order so FK constraints are satisfied
    throughout.

    Args:
        tables: ``[(df, table_name), ...]`` in parent-first order.
        engine: SQLAlchemy engine pointing at the target PostgreSQL database.

    Returns:
        Row counts in the same order as ``tables``.

    Raises:
        LoadError: DB is unreachable or any write fails (all tables rolled back).
    """
    _check_connection(engine)

    counts: list[int] = []
    with engine.begin() as conn:
        # Phase 1: drop tables with schema drift (child -> parent)
        _drop_schema_mismatches(tables, conn)

        # Phase 2: TRUNCATE remaining existing tables (child -> parent)
        _truncate_tables([name for _, name in reversed(tables)], conn)

        # Phase 3: INSERT (parent -> child)
        for df, table_name in tables:
            if df.empty:
                logger.warning("DataFrame is empty; skipping table load")
                counts.append(0)
                continue

            n = len(df)
            try:
                df.to_sql(table_name, conn, if_exists="append", index=False)
            except SQLAlchemyError as exc:
                raise LoadError(
                    f"Failed to write {n} rows. All tables rolled back."
                ) from exc

            logger.info("Loaded %d rows", n)
            counts.append(n)

    return counts
