"""Add min_salary, max_salary, salary_unit; job_role_category; stable job_id; job_locations."""

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

OUT = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "salary_cleaned.csv"
LOC_OUT = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "job_locations.csv"

_ID_FIELDS = ("link_description", "company", "job_title", "created_date")


# ── Private step functions ───────────────────────────────────────────────────

def _make_job_id(row: pd.Series) -> str:
    """Stable 16-char hex ID from content fields (immune to row-order changes)."""
    key = "|".join(str(row.get(f, "") or "") for f in _ID_FIELDS)
    return hashlib.md5(key.encode()).hexdigest()[:16]


def _apply_salary(out: pd.DataFrame) -> pd.DataFrame:
    tuples = out["salary"].apply(parse_salary).tolist()
    out[["min_salary", "max_salary", "salary_unit"]] = pd.DataFrame(
        tuples, index=out.index, columns=["min_salary", "max_salary", "salary_unit"]
    )
    return out


def _apply_job_title(out: pd.DataFrame) -> pd.DataFrame:
    if "job_title" not in out.columns:
        return out
    out["job_role_category"] = out["job_title"].apply(normalize_job_title)
    return out


def _build_locations(out: pd.DataFrame) -> pd.DataFrame:
    """Vectorized: explode (city, district) pairs into one row each."""
    if "address" not in out.columns:
        logger.warning("No 'address' column found; job_locations will be empty.")
        return pd.DataFrame(columns=["job_id", "sort_order", "city", "district"])

    locs_series = out["address"].apply(parse_address_locations)
    loc_df = (
        pd.DataFrame({"job_id": out["job_id"], "_locs": locs_series})
        .explode("_locs")
        .dropna(subset=["_locs"])
        .reset_index(drop=True)
    )

    if loc_df.empty:
        return pd.DataFrame(columns=["job_id", "sort_order", "city", "district"])

    loc_df["sort_order"] = loc_df.groupby("job_id").cumcount()
    loc_df[["city", "district"]] = pd.DataFrame(
        loc_df["_locs"].tolist(), index=loc_df.index
    )
    return loc_df.drop(columns=["_locs"])[["job_id", "sort_order", "city", "district"]]


def _log_salary_stats(out: pd.DataFrame) -> None:
    n = len(out)
    ok = int((out["min_salary"].notna() | out["max_salary"].notna()).sum())
    bad_mask = (
        out["salary"].astype(str).str.contains(r"\d", regex=True, na=False)
        & out["min_salary"].isna()
        & out["max_salary"].isna()
    )
    bad_n = int(bad_mask.sum())
    logger.info("rows: %d | salary parsed: %d | unparseable (had digit): %d", n, ok, bad_n)
    if bad_n:
        samples = out.loc[bad_mask, "salary"].dropna().astype(str).unique().tolist()
        for v in sorted(samples, key=lambda x: (len(x), x))[:20]:
            logger.warning("  unparseable salary: %r", v)
        if len(samples) > 20:
            logger.warning("  ... +%d more unparseable", len(samples) - 20)


def write_processed(out: pd.DataFrame, locations: pd.DataFrame) -> None:
    """Persist the two processed DataFrames as CSV files.

    Separated from :func:`transform` so that the transform step is a pure
    function (no file-system side effects).  Call this from the pipeline
    entrypoint after a successful transform if you want a local CSV snapshot.

    Raises:
        TransformError: the output directory or files cannot be written.
    """
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(OUT, index=False, encoding="utf-8")
        locations.to_csv(LOC_OUT, index=False, encoding="utf-8")
    except OSError as exc:
        raise TransformError(f"Cannot write processed CSV: {exc}") from exc
    logger.info("Wrote %s and %s", OUT, LOC_OUT)


# ── Public API ────────────────────────────────────────────────────────────────

def transform(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run all transform steps; return ``(jobs_df, locations_df)``.

    Pure function: no file-system or database side effects.
    Call :func:`write_processed` afterwards if a CSV snapshot is wanted.

    Raises:
        TransformError: input DataFrame is unusable (empty or missing columns).
    """
    if df.empty:
        raise TransformError("Cannot transform an empty DataFrame.")
    if "salary" not in df.columns:
        raise TransformError("DataFrame must contain a 'salary' column.")

    out = df.copy()
    out.insert(0, "job_id", out.apply(_make_job_id, axis=1))

    out = _apply_salary(out)
    out = _apply_job_title(out)
    locations = _build_locations(out)

    _log_salary_stats(out)

    return out, locations
