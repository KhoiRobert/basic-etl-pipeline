"""Load DataFrames into PostgreSQL.

Append-load strategy per ``load_all()``:
    1. ALTER TABLE … ADD COLUMN IF NOT EXISTS for every column present in the
       DataFrame but absent from the existing table (zero-downtime schema drift).
       New columns default to NULL for pre-existing rows.  Tables are never dropped.
    2. INSERT new rows in **parent -> child** order (satisfies FK constraints).
       No TRUNCATE — existing rows are preserved so the database accumulates
       job history across runs.

Duplicate prevention:
    ``records`` declares ``job_id TEXT PRIMARY KEY``, so PostgreSQL will
    reject any row whose ``job_id`` already exists.  In practice this never
    fires because ``scripts/crawl_topcv.py`` queries the database for known
    links before crawling, ensuring each batch contains only new jobs.
    If a duplicate does slip through the load will raise ``LoadError`` and
    roll back, leaving the database unchanged.

All phases run inside a single ``engine.begin()`` transaction.
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
        raise LoadError(
            "Cannot reach the database. Is Postgres running and are DB_HOST/DB_PORT correct?"
        ) from exc


def _has_table(conn, table_name: str) -> bool:
    """Live existence check — bypasses SQLAlchemy inspector cache."""
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


def _migrate_schema(
    tables: list[tuple[pd.DataFrame, str]],
    conn,
) -> None:
    """Add missing columns to existing tables via ``ALTER TABLE … ADD COLUMN IF NOT EXISTS``.

    For each table that already exists in the database, any column present in
    the DataFrame but absent from the table is added as ``TEXT`` with a ``NULL``
    default.  Pre-existing rows receive ``NULL`` for the new column.

    This is a non-destructive, zero-downtime migration — no rows are deleted
    and no tables are dropped.  Column *type* mismatches (e.g. a column changed
    from TEXT to BIGINT) are not handled here; those require a manual migration.

    Args:
        tables: ``[(df, table_name), ...]`` in any order.
        conn: Active SQLAlchemy connection inside an open transaction.
    """
    for df, table_name in tables:
        if not _has_table(conn, table_name):
            continue
        missing = set(df.columns) - _columns_in_db(conn, table_name)
        if not missing:
            continue
        for col in sorted(missing):
            logger.warning(
                "Schema drift: adding column '%s' to table '%s' (existing rows → NULL).",
                col,
                table_name,
            )
            conn.execute(
                text(
                    f'ALTER TABLE "{table_name}" '
                    f'ADD COLUMN IF NOT EXISTS "{col}" TEXT'
                )
            )


def load_all(
    tables: list[tuple[pd.DataFrame, str]],
    engine: Engine,
) -> list[int]:
    """Append new rows to PostgreSQL tables in a single transaction.

    Pass tables in **parent-first** order (e.g. ``records`` before
    ``job_locations``).  Rows are inserted in that order so FK constraints
    are satisfied.  Existing rows are never deleted.

    Args:
        tables: ``[(df, table_name), ...]`` in parent-first order.
        engine: SQLAlchemy engine pointing at the target PostgreSQL database.

    Returns:
        Row counts inserted, in the same order as ``tables``.

    Raises:
        LoadError: DB is unreachable, a PK/FK constraint is violated (e.g.
            duplicate ``job_id``), or any other write failure.  All tables
            are rolled back together.
    """
    _check_connection(engine)

    counts: list[int] = []
    with engine.begin() as conn:
        # Phase 1: non-destructive schema migration (ADD COLUMN, never DROP TABLE)
        _migrate_schema(tables, conn)

        # Phase 2: INSERT (parent -> child) — no TRUNCATE, rows accumulate
        for df, table_name in tables:
            if df.empty:
                logger.warning("DataFrame for '%s' is empty; skipping.", table_name)
                counts.append(0)
                continue

            n = len(df)
            try:
                df.to_sql(table_name, conn, if_exists="append", index=False)
            except SQLAlchemyError as exc:
                raise LoadError(
                    f"Failed to insert {n} rows into '{table_name}'. "
                    "All tables rolled back. "
                    "Check for duplicate job_id values or schema mismatches."
                ) from exc

            logger.info("Inserted %d rows into '%s'", n, table_name)
            counts.append(n)

    return counts
