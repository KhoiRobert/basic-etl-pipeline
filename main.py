"""CLI entrypoint: extract → transform → load."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from pandas.errors import ParserError

from config.settings import get_engine
from etl.errors import ConfigError, ExtractError, LoadError, TransformError
from etl.extract import extract
from etl.load import load_all
from etl.transform import transform

_DEFAULT_CSV = Path(__file__).resolve().parent / "data.csv"


def _configure_logging() -> None:
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> int:
    _configure_logging()
    log = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description="CSV → PostgreSQL ETL pipeline")
    parser.add_argument(
        "filepath",
        nargs="?",
        default=str(_DEFAULT_CSV),
        help=f"Path to the input CSV file (default: {_DEFAULT_CSV})",
    )
    parser.add_argument(
        "--table",
        default="records",
        help='Target table name for job rows (default: "records")',
    )
    parser.add_argument(
        "--locations-table",
        default="job_locations",
        help='Target table name for job ↔ location rows (default: "job_locations")',
    )
    args = parser.parse_args()

    # ── Extract ───────────────────────────────────────────────────────────────
    try:
        raw_df = extract(args.filepath)
    except FileNotFoundError as exc:
        log.error("Extract failed – file not found: %s", exc)
        return 1
    except (ExtractError, ParserError, OSError) as exc:
        log.error("Extract failed: %s", exc)
        return 1

    # ── Transform ─────────────────────────────────────────────────────────────
    try:
        clean_df, job_locations = transform(raw_df)
    except TransformError as exc:
        log.error("Transform failed: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected transform error: %s", exc, exc_info=True)
        return 1

    # ── Load (single transaction) ─────────────────────────────────────────────
    try:
        engine = get_engine()
    except ConfigError as exc:
        log.error("Configuration error: %s", exc)
        return 1

    try:
        counts = load_all(
            [(clean_df, args.table), (job_locations, args.locations_table)],
            engine,
        )
    except LoadError as exc:
        log.error("Load failed: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected load error: %s", exc, exc_info=True)
        return 1

    log.info(
        "rows extracted: %d / loaded: %d %s, %d %s",
        len(raw_df), counts[0], args.table, counts[1], args.locations_table,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
