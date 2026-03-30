#!/usr/bin/env python3
"""Crawl new TopCV job listings and write them to a raw CSV batch.

Deduplication
-------------
Known job links are fetched directly from PostgreSQL (``records.link_description``).
This replaces the old ``known_links.txt`` approach, which grew indefinitely and
was fragile (file drift if a run failed mid-way).  The database is the single
source of truth; no auxiliary state file is required.

If the database is unreachable at crawl time, the script raises a hard error
and exits immediately.  Crawling without known links would silently insert
duplicates into PostgreSQL, which is worse than not running at all.

Archiving
---------
Before overwriting ``data/raw/data.csv``, the previous file is copied to
``data/raw/archive/data_YYYYMMDD_HHMMSS_utc.csv``.  Only the most recent
``--archive-keep`` files are retained; older archives are pruned automatically.
This enables replay / reprocessing without relying on git history for data.

Usage
-----
  # Standard scheduled run
  python scripts/crawl_topcv.py --max-pages 15

  # Quick local test (3 pages, verbose)
  python scripts/crawl_topcv.py --max-pages 3 -v

Then run the ETL pipeline:
  python main.py data/raw/data.csv
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.engine import Engine

from config.settings import get_engine
from etl.errors import ConfigError, CrawlError
from etl.extract.topcv_crawl import DEFAULT_LISTING, crawl_topcv

log = logging.getLogger(__name__)

_DEFAULT_OUTPUT  = ROOT / "data" / "raw" / "data.csv"
_DEFAULT_ARCHIVE = ROOT / "data" / "raw" / "archive"


# ── DB-backed deduplication ───────────────────────────────────────────────────

def fetch_known_links(engine: Engine) -> set[str]:
    """Query PostgreSQL for every job link already loaded into ``records``.

    This is a hard dependency: if the query fails for any reason the function
    raises immediately.  Crawling without known links would treat every job as
    new and insert duplicates, so failing loudly is always preferable.

    On the very first run, ``records`` does not yet exist.  PostgreSQL raises
    ``UndefinedTable`` (a subclass of ``ProgrammingError``), which we catch and
    treat as an empty set — the only legitimate case where the table is absent.

    Args:
        engine: Live SQLAlchemy engine connected to the pipeline's database.

    Returns:
        Set of canonical job URL strings (empty on first-ever run).

    Raises:
        RuntimeError: DB is unreachable or query fails for any reason other
            than the table not existing yet.
    """
    from sqlalchemy.exc import ProgrammingError

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT link_description FROM records "
                    "WHERE link_description IS NOT NULL"
                )
            )
            links = {row[0] for row in rows}
        log.info("Fetched %d known links from database.", len(links))
        return links
    except ProgrammingError:
        # Table does not exist yet — first-ever run, safe to treat as empty.
        log.info("'records' table not found — assuming first run, known links = empty set.")
        return set()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Cannot fetch known links from database: {exc}. "
            "Crawl aborted — running without deduplication would insert duplicates."
        ) from exc


# ── Raw-file archiving ────────────────────────────────────────────────────────

def archive_raw_file(src: Path, archive_dir: Path, *, keep: int = 14) -> Path | None:
    """Copy *src* to *archive_dir* with a UTC timestamp suffix.

    Args:
        src: Source file to archive (typically ``data/raw/data.csv``).
        archive_dir: Destination directory for archive copies.
        keep: Maximum number of archive files to retain.  Oldest files beyond
            this limit are deleted automatically.

    Returns:
        Path to the newly created archive file, or ``None`` if *src* did not
        exist (nothing to archive on the very first run).
    """
    if not src.exists():
        return None

    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_utc")
    dest = archive_dir / f"data_{stamp}.csv"
    shutil.copy2(src, dest)
    log.info("Archived %s → %s", src.name, dest.name)

    existing = sorted(archive_dir.glob("data_*.csv"))
    for old in existing[:-keep]:
        old.unlink(missing_ok=True)
        log.debug("Pruned old archive: %s", old.name)

    return dest


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crawl new TopCV job listings and write a raw CSV batch."
    )
    parser.add_argument(
        "-o", "--output",
        default=str(_DEFAULT_OUTPUT),
        help=f"Output CSV path (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--archive-dir",
        default=str(_DEFAULT_ARCHIVE),
        help=f"Directory for timestamped raw archives (default: {_DEFAULT_ARCHIVE})",
    )
    parser.add_argument(
        "--archive-keep",
        type=int,
        default=14,
        help="Number of archive files to retain (default: 14)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_LISTING,
        help=f"First listing page URL (default: {DEFAULT_LISTING})",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=15,
        help="Listing pages to crawl (default: 15 ≈ 600 jobs)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Polite pause between page requests in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="HTTP retry attempts per page on transient failure (default: 3)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    out         = Path(args.output)
    archive_dir = Path(args.archive_dir)
    out.parent.mkdir(parents=True, exist_ok=True)

    # ── Step 1: fetch known links from DB ─────────────────────────────────────
    try:
        engine = get_engine()
    except ConfigError as exc:
        log.error(
            "DB not configured: %s. "
            "Crawl aborted — cannot deduplicate without a database connection.",
            exc,
        )
        return 1

    known_links = fetch_known_links(engine)

    # ── Step 2: crawl (skips known links, stops early on all-known page) ──────
    try:
        new_df = crawl_topcv(
            args.url,
            max_pages=args.max_pages,
            delay_seconds=args.delay,
            max_retries=args.max_retries,
            known_links=known_links,
        )
    except CrawlError as exc:
        log.error("Crawl aborted: %s", exc)
        return 1

    log.info("Crawled %d new rows from TopCV.", len(new_df))

    if new_df.empty:
        log.info("No new jobs found — nothing to write.")
        return 0

    # Safety dedup within this session (TopCV shouldn't show dupes, but guard anyway)
    before = len(new_df)
    new_df = new_df.drop_duplicates(subset=["link_description"], keep="first")
    if (removed := before - len(new_df)):
        log.info("Removed %d intra-session duplicate(s).", removed)

    # ── Step 3: archive previous batch before overwriting ─────────────────────
    archive_raw_file(out, archive_dir, keep=args.archive_keep)

    # ── Step 4: write new batch ───────────────────────────────────────────────
    new_df.to_csv(out, index=False, encoding="utf-8")
    log.info("Wrote %d rows to %s (overwrite).", len(new_df), out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
