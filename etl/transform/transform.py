"""Transform raw job DataFrame into clean, load-ready tables.

Design
------
Each public ``step_*`` function is a pure, single-responsibility transformer:

    step_add_job_id          DataFrame → DataFrame   (inserts job_id column)
    step_parse_salary        DataFrame → DataFrame   (adds min/max/unit columns)
    step_classify_job_title  DataFrame → DataFrame   (adds job_role_category)
    step_extract_locations   DataFrame → DataFrame   (returns child locations table)

These steps are composable and independently testable.  The ``transform()``
orchestrator chains them in order and is the only entry-point callers need.

Side effects (file I/O) are isolated in ``write_processed()``, which is called
explicitly by the pipeline entrypoint *after* a successful transform — keeping
the transform step itself a pure function.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pandas as pd

from etl.errors import TransformError
from etl.transform.address import parse_address_locations
from etl.transform.job_title import normalize_job_title
from etl.transform.salary import parse_salary

logger = logging.getLogger(__name__)

_PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
_SALARY_OUT    = _PROCESSED_DIR / "salary_cleaned.csv"
_LOCATIONS_OUT = _PROCESSED_DIR / "job_locations.csv"

_ID_FIELDS = ("link_description", "company", "job_title", "created_date")


# ── Private helpers ───────────────────────────────────────────────────────────

def _make_job_id(row: pd.Series) -> str:
    """Return a stable 16-hex-char ID derived from content fields.

    The ID is immune to row-order changes and reproducible across runs as long
    as the four source fields are identical.  MD5 is used purely as a
    deterministic hash — not for cryptographic security.
    """
    key = "|".join(str(row.get(f, "") or "") for f in _ID_FIELDS)
    return hashlib.md5(key.encode()).hexdigest()[:16]


def _validate_input(df: pd.DataFrame) -> None:
    """Raise TransformError if the DataFrame cannot be meaningfully transformed.

    Args:
        df: Raw DataFrame from the extract step.

    Raises:
        TransformError: DataFrame is empty or missing the mandatory ``salary``
            column (the only column the transform pipeline strictly requires).
    """
    if df.empty:
        raise TransformError("Cannot transform an empty DataFrame.")
    if "salary" not in df.columns:
        raise TransformError(
            "DataFrame must contain a 'salary' column. "
            f"Found columns: {list(df.columns)}"
        )


def _log_salary_stats(df: pd.DataFrame) -> None:
    """Emit INFO / WARNING metrics about salary parse coverage."""
    n   = len(df)
    ok  = int((df["min_salary"].notna() | df["max_salary"].notna()).sum())
    bad_mask = (
        df["salary"].astype(str).str.contains(r"\d", regex=True, na=False)
        & df["min_salary"].isna()
        & df["max_salary"].isna()
    )
    bad_n = int(bad_mask.sum())
    logger.info(
        "Salary parse — rows: %d | parsed: %d (%.0f%%) | unparseable (had digit): %d",
        n, ok, 100 * ok / n if n else 0, bad_n,
    )
    if bad_n:
        samples = (
            df.loc[bad_mask, "salary"].dropna().astype(str).unique().tolist()
        )
        for v in sorted(samples, key=lambda x: (len(x), x))[:10]:
            logger.warning("  unparseable salary: %r", v)
        if len(samples) > 10:
            logger.warning("  … +%d more unparseable value(s)", len(samples) - 10)


# ── Composable transform steps ────────────────────────────────────────────────

def step_add_job_id(df: pd.DataFrame) -> pd.DataFrame:
    """Insert a stable, content-derived ``job_id`` as the first column.

    The ID is computed from ``link_description``, ``company``, ``job_title``,
    and ``created_date`` — the four fields that uniquely identify a posting.
    Rows with identical content across runs always produce the same ID, which
    makes the column safe to use as a PRIMARY KEY.

    Args:
        df: DataFrame containing at least the four ID source columns.

    Returns:
        Copy of *df* with ``job_id`` inserted at position 0.
    """
    out = df.copy()
    out.insert(0, "job_id", out.apply(_make_job_id, axis=1))
    return out


def step_parse_salary(df: pd.DataFrame) -> pd.DataFrame:
    """Expand the raw ``salary`` text column into structured numeric fields.

    Adds three columns to *df*:
      - ``min_salary``  (int | None) — lower bound in the detected currency unit
      - ``max_salary``  (int | None) — upper bound in the detected currency unit
      - ``salary_unit`` (str | None) — ``"VND"`` or ``"USD"``

    Rows with non-numeric salary text (e.g. ``"Thoả thuận"``) receive
    ``None`` for all three new columns.

    Args:
        df: DataFrame that must contain a ``salary`` column.

    Returns:
        Copy of *df* with the three salary columns appended.
    """
    if "salary" not in df.columns:
        logger.warning("'salary' column missing — skipping salary parse step.")
        return df

    out = df.copy()
    parsed = out["salary"].apply(parse_salary).tolist()
    out[["min_salary", "max_salary", "salary_unit"]] = pd.DataFrame(
        parsed,
        index=out.index,
        columns=["min_salary", "max_salary", "salary_unit"],
    )
    return out


def step_classify_job_title(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw ``job_title`` to a standardised ``job_role_category`` label.

    Classification runs through two stages:
      1. Rule-based keyword matching (fast, deterministic).
      2. TF-IDF char-n-gram cosine similarity fallback (requires scikit-learn).
      3. Defaults to ``"Other"`` when neither stage finds a match.

    Args:
        df: DataFrame that should contain a ``job_title`` column.  If absent,
            the DataFrame is returned unchanged with a warning.

    Returns:
        Copy of *df* with a ``job_role_category`` column appended.
    """
    if "job_title" not in df.columns:
        logger.warning("'job_title' column missing — skipping classification step.")
        return df

    out = df.copy()
    out["job_role_category"] = out["job_title"].apply(normalize_job_title)
    return out


def step_extract_locations(df: pd.DataFrame) -> pd.DataFrame:
    """Produce a normalised ``job_locations`` child table from address text.

    Each ``(city, district)`` pair becomes one row.  A single address like
    ``"Hà Nội: Cầu Giấy, Đống Đa"`` expands into two rows, both referencing
    the same ``job_id``.

    Args:
        df: DataFrame that must already contain a ``job_id`` column (produced
            by ``step_add_job_id``) and an ``address`` column.

    Returns:
        New DataFrame with columns ``["job_id", "sort_order", "city",
        "district"]``, ready to load into the ``job_locations`` table.
        Returns an empty DataFrame with those columns if ``address`` is absent
        or all values fail to parse.
    """
    _empty = pd.DataFrame(columns=["job_id", "sort_order", "city", "district"])

    if "address" not in df.columns:
        logger.warning("'address' column missing — job_locations will be empty.")
        return _empty

    locs_series = df["address"].apply(parse_address_locations)
    loc_df = (
        pd.DataFrame({"job_id": df["job_id"], "_locs": locs_series})
        .explode("_locs")
        .dropna(subset=["_locs"])
        .reset_index(drop=True)
    )

    if loc_df.empty:
        return _empty

    loc_df["sort_order"] = loc_df.groupby("job_id").cumcount()
    loc_df[["city", "district"]] = pd.DataFrame(
        loc_df["_locs"].tolist(), index=loc_df.index
    )
    return loc_df.drop(columns=["_locs"])[["job_id", "sort_order", "city", "district"]]


# ── Side-effect helper ────────────────────────────────────────────────────────

def write_processed(jobs: pd.DataFrame, locations: pd.DataFrame) -> None:
    """Persist the two transformed DataFrames as local CSV snapshots.

    Intentionally separated from ``transform()`` so that the transform step
    remains a pure function with no file-system side effects.  Call this from
    the pipeline entrypoint *after* a successful ``transform()`` call.

    Args:
        jobs: Cleaned jobs DataFrame (output of the transform pipeline).
        locations: Child locations DataFrame (from ``step_extract_locations``).

    Raises:
        TransformError: Either output directory cannot be created or a file
            cannot be written.
    """
    try:
        _PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        jobs.to_csv(_SALARY_OUT, index=False, encoding="utf-8")
        locations.to_csv(_LOCATIONS_OUT, index=False, encoding="utf-8")
    except OSError as exc:
        raise TransformError(f"Cannot write processed CSV: {exc}") from exc
    logger.info("Processed snapshots written to %s/", _PROCESSED_DIR)


# ── Orchestrator ──────────────────────────────────────────────────────────────

def transform(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run all transform steps in sequence and return load-ready tables.

    Steps (in order):
      1. ``_validate_input``       — raises early on unusable input
      2. ``step_add_job_id``       — stable primary key
      3. ``step_parse_salary``     — structured salary fields
      4. ``step_classify_job_title`` — role category label
      5. ``step_extract_locations`` — child locations table
      6. ``_log_salary_stats``     — observability metrics

    This function is **pure**: no file I/O or database access.  Call
    ``write_processed()`` afterwards if a CSV snapshot is needed.

    Args:
        df: Raw DataFrame from the extract step.

    Returns:
        Tuple ``(jobs_df, locations_df)`` both ready to pass to ``load_all()``.

    Raises:
        TransformError: Input validation failed (empty DataFrame or missing
            required columns).
    """
    _validate_input(df)

    df = step_add_job_id(df)
    df = step_parse_salary(df)
    df = step_classify_job_title(df)
    locations = step_extract_locations(df)

    _log_salary_stats(df)

    return df, locations
