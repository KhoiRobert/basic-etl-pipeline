"""Salary string → (min_salary, max_salary, salary_unit). Integers; VND scaled, USD as-is."""

from __future__ import annotations

import re

import pandas as pd
from pandas.api.types import is_scalar

_N = r"\d[\d,\.]*"
_U = r"(triệu|trieu|tr|million|mil|m|k|ngàn|nghìn|ngan|nghin|đ|vnd|dong)\b"

# Pre-compiled (used on every row)
R = {
    "usd_dd": re.compile(rf"\$\s*({_N})\s*-\s*\$\s*({_N})"),
    "usd_r": re.compile(rf"\$?\s*({_N})\s*-\s*\$?\s*({_N})\s*(?:usd|\$)\b", re.I),
    "usd_up": re.compile(rf"(?:tới|lên\s+đến|up\s*to|upto)\s+\$?\s*({_N})\s*(?:usd|\$)\b", re.I),
    "usd_lo": re.compile(rf"(?:trên|từ)\s+\$?\s*({_N})\s*(?:usd|\$)\b", re.I),
    "usd_l": re.compile(rf"^\s*\$\s*({_N})\s*$"),
    "usd_t": re.compile(rf"^\s*({_N})\s*(?:\$|\busd\b)\s*$", re.I),
    "vnd_r": re.compile(rf"({_N})\s*-\s*({_N})\s*({_U})", re.I),
    "vnd_up": re.compile(rf"(?:tới|lên\s+đến|up\s*to|upto)\s+({_N})\s*({_U})", re.I),
    "vnd_lo": re.compile(rf"(?:trên|từ)\s+({_N})\s*({_U})", re.I),
    "vnd_ex": re.compile(rf"^[\s~∼～]*({_N})\s*({_U})\s*$", re.I),
    "vnd_tr": re.compile(rf"^[\s~∼～]*({_N})\s*tr(?=\s|$|[/.,;]|\)|\]|\}}|\Z)", re.I),
}

_USD = re.compile(r"\$|\busd\b", re.I)
_TILDE = re.compile(r"^[\s~∼～]+")
_HAS_DIGIT = re.compile(r"\d")

_MULT: dict[str, int] = {
    "tr": 1_000_000,
    "triệu": 1_000_000,
    "trieu": 1_000_000,
    "million": 1_000_000,
    "mil": 1_000_000,
    "m": 1_000_000,
    "k": 1_000,
    "ngàn": 1_000,
    "nghìn": 1_000,
    "ngan": 1_000,
    "nghin": 1_000,
    "đ": 1,
    "vnd": 1,
    "dong": 1,
}


def normalize_numeric_string(raw: str) -> str:
    s = raw.strip()
    if not s:
        raise ValueError("empty numeric token")
    m = re.match(r"^(\d{1,3}(?:\.\d{3})+),(\d+)$", s)
    if m:
        return f"{m.group(1).replace('.', '')}.{m.group(2)}"
    if s.count(",") == 1:
        left, right = s.split(",")
        if right.isdigit() and len(right) <= 2 and left.replace(".", "").isdigit():
            return f"{left.replace('.', '')}.{right}" if "." in left else f"{left}.{right}"
        s = s.replace(",", "")
    else:
        s = s.replace(",", "")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        return s.replace(".", "")
    return s


def to_int_salary(value: object, multiplier: int) -> int | None:
    if value is None:
        return None
    return int(float(value) * multiplier)


def _strip_dollar(t: str) -> str:
    t = t.lstrip()
    return t[1:].lstrip() if t.startswith("$") else t


def _clean(raw: str) -> str:
    s = raw.strip().lower().replace("\xa0", " ").replace("–", "-").replace("—", "-")
    return _TILDE.sub("", s)


def _m(unit: str) -> int:
    return _MULT[unit.strip().casefold()]


def parse_salary(text: object) -> tuple[int | None, int | None, str | None]:
    if text is None or (is_scalar(text) and pd.isna(text)):
        return (None, None, None)
    raw = str(text)
    if raw.strip().casefold() in ("nan", "none"):
        return (None, None, None)

    s = _clean(raw)
    # No digit → nothing to parse ("thoả thuận", "negotiable", empty, prose-only, …)
    if not _HAS_DIGIT.search(s):
        return (None, None, None)

    # Has at least one digit → try salary patterns (may still return all None if no match)
    usd = bool(_USD.search(s))

    if usd:
        for key in ("usd_dd", "usd_r"):
            m = R[key].search(s)
            if m:
                a = normalize_numeric_string(_strip_dollar(m.group(1)))
                b = normalize_numeric_string(_strip_dollar(m.group(2)))
                return to_int_salary(a, 1), to_int_salary(b, 1), "USD"
        for key in ("usd_up", "usd_lo"):
            m = R[key].search(s)
            if m:
                v = normalize_numeric_string(_strip_dollar(m.group(1)))
                x = to_int_salary(v, 1)
                return (None, x, "USD") if key == "usd_up" else (x, None, "USD")
        m = R["usd_l"].fullmatch(s)
        if m:
            v = normalize_numeric_string(m.group(1))
            x = to_int_salary(v, 1)
            return x, x, "USD"
        m = R["usd_t"].fullmatch(s)
        if m:
            v = normalize_numeric_string(m.group(1))
            x = to_int_salary(v, 1)
            return x, x, "USD"

    m = R["vnd_r"].search(s)
    if m:
        k = _m(m.group(3))
        a, b = normalize_numeric_string(m.group(1)), normalize_numeric_string(m.group(2))
        return to_int_salary(a, k), to_int_salary(b, k), "VND"
    for key in ("vnd_up", "vnd_lo"):
        m = R[key].search(s)
        if m:
            k, v = _m(m.group(2)), normalize_numeric_string(m.group(1))
            x = to_int_salary(v, k)
            return (None, x, "VND") if key == "vnd_up" else (x, None, "VND")
    m = R["vnd_ex"].fullmatch(s)
    if m:
        k, v = _m(m.group(2)), normalize_numeric_string(m.group(1))
        x = to_int_salary(v, k)
        return x, x, "VND"
    m = R["vnd_tr"].fullmatch(s)
    if m:
        v = normalize_numeric_string(m.group(1))
        x = to_int_salary(v, _MULT["tr"])
        return x, x, "VND"

    return (None, None, None)
