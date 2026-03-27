"""Add min_salary, max_salary, salary_unit; job_id; job_locations rows (no city/district on main)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from etl.transform.address import parse_address_locations
from etl.transform.salary import parse_salary

logger = logging.getLogger(__name__)

OUT = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "salary_cleaned.csv"
LOC_OUT = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "job_locations.csv"


def transform(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if "salary" not in df.columns:
        raise KeyError("DataFrame must contain a 'salary' column")

    out = df.copy()
    out.insert(0, "job_id", range(len(out)))

    tuples = out["salary"].apply(parse_salary).tolist()
    out[["min_salary", "max_salary", "salary_unit"]] = pd.DataFrame(
        tuples, index=out.index, columns=["min_salary", "max_salary", "salary_unit"]
    )

    if "address" in out.columns:
        loc_rows: list[dict[str, object]] = []
        for _, row in out.iterrows():
            jid = int(row["job_id"])
            for order, (city, district) in enumerate(parse_address_locations(row["address"])):
                loc_rows.append(
                    {
                        "job_id": jid,
                        "sort_order": order,
                        "city": city,
                        "district": district,
                    }
                )
        locations = pd.DataFrame(loc_rows)
    else:
        locations = pd.DataFrame(columns=["job_id", "sort_order", "city", "district"])

    n = len(out)
    ok = int((out["min_salary"].notna() | out["max_salary"].notna()).sum())
    sal = out["salary"].astype(str)
    bad = sal.str.contains(r"\d", regex=True, na=False) & out["min_salary"].isna() & out["max_salary"].isna()
    bad_n = int(bad.sum())
    samples = out.loc[bad, "salary"].dropna().astype(str).unique().tolist()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8")
    locations.to_csv(LOC_OUT, index=False, encoding="utf-8")

    print(f"rows: {n} | parsed (min/max set): {ok} | not parsed (had digit): {bad_n}")
    if samples:
        for v in sorted(samples, key=lambda x: (len(x), x))[:50]:
            print(f"  {v!r}")
        if len(samples) > 50:
            print(f"  ... +{len(samples) - 50} more")

    logger.info("Wrote %s and %s", OUT, LOC_OUT)
    return out, locations
