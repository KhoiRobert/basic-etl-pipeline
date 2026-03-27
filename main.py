"""CLI entrypoint: extract → transform (optional) → load."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pandas.errors import ParserError
from sqlalchemy.exc import SQLAlchemyError

from config.settings import get_engine
from etl.extract import extract
from etl.load import load
from etl.transform import transform

_DEFAULT_CSV = Path(__file__).resolve().parent / "data.csv"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
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
        help='Target table name (default: "records")',
    )
    args = parser.parse_args()

    try:
        raw_df = extract(args.filepath)
    except (FileNotFoundError, OSError, ParserError, ValueError) as e:
        log.error("%s", e)
        return 1

    clean_df = transform(raw_df)

    try:
        engine = get_engine()
        loaded = load(clean_df, args.table, engine)
    except (KeyError, SQLAlchemyError) as e:
        log.error("Load failed: %s", e)
        return 1

    extracted = len(raw_df)
    print(f"rows extracted: {extracted} / rows loaded: {loaded}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
