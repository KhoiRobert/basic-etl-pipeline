"""Address → (city, district) rows: ``city: district`` blocks, districts may be comma-separated."""

from __future__ import annotations

import pandas as pd
from pandas.api.types import is_scalar


def _normalize(raw: str) -> str | None:
    s = raw.strip().replace("\xa0", " ")
    return s or None


def _district_names(blob: str) -> list[str]:
    return [p.strip() for p in blob.split(",") if p.strip()]


def parse_address_locations(text: object) -> list[tuple[str | None, str | None]]:
    """
    Split on ``:`` into ``city`` / ``district`` blocks. The district side may list
    several areas separated by commas, e.g.
    ``Hồ Chí Minh: Bình Thạnh, Phú Nhuận, Gò Vấp`` → three rows with city Hồ Chí Minh.
    Multiple regions repeat: ``city1: d1, d2: city2: d3``.
    """
    if text is None or (is_scalar(text) and pd.isna(text)):
        return []
    raw = str(text)
    if raw.strip().casefold() in ("nan", "none"):
        return []

    s = _normalize(raw)
    if not s:
        return []

    parts = [p.strip() for p in s.split(":")]
    parts = [p for p in parts if p]
    if not parts:
        return []
    if len(parts) == 1:
        return [(parts[0], None)]

    out: list[tuple[str | None, str | None]] = []
    i = 0
    while i + 1 < len(parts):
        city = parts[i]
        district_blob = parts[i + 1]
        names = _district_names(district_blob)
        if not names:
            out.append((city, None))
        else:
            for d in names:
                out.append((city, d))
        i += 2
    if i < len(parts):
        out.append((parts[i], None))
    return out


def parse_address(text: object) -> tuple[str | None, str | None]:
    """First ``(city, district)`` from the address, or ``(None, None)`` if none."""
    locs = parse_address_locations(text)
    if not locs:
        return (None, None)
    return locs[0]
