"""Address → (city, district) rows: ``city: district`` blocks, districts may be comma-separated.

TopCV address strings may contain:
  - UI badges like ``(mới)`` appended to city names  → stripped
  - Multiple cities joined by ``&``                  → split into separate entries
  - Vague trailing entries like ``"3 nơi khác"``     → discarded
"""

from __future__ import annotations

import re

import pandas as pd
from pandas.api.types import is_scalar

# Matches parenthesised UI badges appended by TopCV, e.g. "(mới)", "(moi)"
_BADGE_RE = re.compile(r"\s*\([^)]*\)")

# Matches "X nơi khác" / "X noi khac" — vague "X other places" entries
_OTHER_PLACES_RE = re.compile(r"^\d+\s+nơi\s+khác$", re.IGNORECASE)


def _normalize(raw: str) -> str | None:
    s = raw.strip().replace("\xa0", " ")
    return s or None


def _clean_city(name: str) -> str:
    """Strip UI badges (e.g. ``(mới)``) and normalise whitespace."""
    return _BADGE_RE.sub("", name).strip()


def _district_names(blob: str) -> list[str]:
    return [p.strip() for p in blob.split(",") if p.strip()]


def _parse_single_segment(segment: str) -> list[tuple[str | None, str | None]]:
    """Parse one ``&``-free address segment (may still contain ``city: district`` blocks)."""
    parts = [p.strip() for p in segment.split(":")]
    parts = [p for p in parts if p]
    if not parts:
        return []
    if len(parts) == 1:
        city = _clean_city(parts[0])
        return [(city, None)] if city else []

    out: list[tuple[str | None, str | None]] = []
    i = 0
    while i + 1 < len(parts):
        city = _clean_city(parts[i])
        district_blob = parts[i + 1]
        names = _district_names(district_blob)
        if not names:
            if city:
                out.append((city, None))
        else:
            for d in names:
                if city:
                    out.append((city, d))
        i += 2
    if i < len(parts):
        city = _clean_city(parts[i])
        if city:
            out.append((city, None))
    return out


def parse_address_locations(text: object) -> list[tuple[str | None, str | None]]:
    """Split address text into ``(city, district)`` pairs.

    Handles:
    - ``city: district1, district2`` colon-block format
    - ``city1 & city2`` multi-city format
    - TopCV ``(mới)`` badges on city names (stripped)
    - ``"X nơi khác"`` vague entries (discarded)
    """
    if text is None or (is_scalar(text) and pd.isna(text)):
        return []
    raw = str(text)
    if raw.strip().casefold() in ("nan", "none"):
        return []

    s = _normalize(raw)
    if not s:
        return []

    out: list[tuple[str | None, str | None]] = []
    for segment in s.split("&"):
        segment = segment.strip()
        if not segment:
            continue
        # Discard "X nơi khác" segments
        if _OTHER_PLACES_RE.match(segment):
            continue
        out.extend(_parse_single_segment(segment))
    return out


def parse_address(text: object) -> tuple[str | None, str | None]:
    """First ``(city, district)`` from the address, or ``(None, None)`` if none."""
    locs = parse_address_locations(text)
    if not locs:
        return (None, None)
    return locs[0]
