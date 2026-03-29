"""Load DataFrames into PostgreSQL.

Full-load strategy per ``load_all()``:
    1. TRUNCATE existing tables in **child → parent** order (respects FK constraints).
    2. INSERT in **parent → child** order (satisfies FK on insert).

Both phases run inside a single ``engine.begin()`` transaction, so either every
table commits or everything rolls back together.

Why TRUNCATE instead of pandas ``if_exists='replace'``?
    ``to_sql(if_exists='replace')`` issues DROP TABLE then CREATE TABLE, which:
    - destroys all FK constraints, indexes, and CHECK constraints,
    - leaves a window where the table does not exist (bad for live systems).
    TRUNCATE keeps the schema intact and is transactional in PostgreSQL.
"""

from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import inspect as sa_inspect, text
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
            "Cannot reach the database. Is Postgres running and are DB_HOST/DB_PORT correct?\n"
            f"  Detail: {exc.__cause__ or exc}"
        ) from exc


def _truncate_tables(
    table_names: list[str],
    conn,
    insp,
) -> None:
    """TRUNCATE existing tables in the given order (caller supplies child-first order)."""
    for name in table_names:
        if insp.has_table(name):
            conn.execute(text(f'TRUNCATE TABLE "{name}"'))
            logger.debug("Truncated %s", name)


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
        tables: ``[(df, table_name), …]`` in parent-first order.
        engine: SQLAlchemy engine pointing at the target PostgreSQL database.

    Returns:
        Row counts in the same order as ``tables``.

    Raises:
        LoadError: DB is unreachable or any write fails (all tables rolled back).
    """
    _check_connection(engine)

    counts: list[int] = []
    with engine.begin() as conn:
        insp = sa_inspect(conn)

        # ── Phase 1: TRUNCATE child → parent ──────────────────────────────────
        _truncate_tables(
            [name for _, name in reversed(tables)],
            conn,
            insp,
        )

        # ── Phase 2: INSERT parent → child ────────────────────────────────────
        for df, table_name in tables:
            if df.empty:
                logger.warning("DataFrame is empty; skipping %s", table_name)
                counts.append(0)
                continue

            n = len(df)
            try:
                df.to_sql(table_name, conn, if_exists="append", index=False)
            except SQLAlchemyError as exc:
                raise LoadError(
                    f"Failed to write {n} rows to '{table_name}': {exc}. "
                    "All tables rolled back."
                ) from exc

            logger.info("Loaded %d rows into %s", n, table_name)
            counts.append(n)

    return counts
