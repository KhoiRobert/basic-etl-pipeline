"""CLI entrypoint: extract → transform (optional) → load."""

from __future__ import annotations

import argparse
import logging
import sys

from pandas.errors import ParserError
from sqlalchemy.exc import SQLAlchemyError

from config.settings import get_engine
from etl.extract import extract
from etl.load import load


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
    parser.add_argument("filepath", help="Path to the input CSV file")
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

    # ✏️ TODO: import and call your transform function here
    # Example: from etl.transform import transform
    #          clean_df = transform(raw_df)
    clean_df = raw_df  # remove this line once transform is added

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
