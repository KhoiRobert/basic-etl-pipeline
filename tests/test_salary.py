"""Unit tests for salary parsing."""

import pytest
from etl.transform.salary import parse_salary


# ── VND ranges ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("10 - 20 triệu",         (10_000_000, 20_000_000, "VND")),
    ("10 - 20 tr",             (10_000_000, 20_000_000, "VND")),
    ("10 - 20 trieu",          (10_000_000, 20_000_000, "VND")),
    ("10 - 20 million",        (10_000_000, 20_000_000, "VND")),
    ("2 - 5 k",                (2_000,      5_000,       "VND")),
])
def test_vnd_range(text, expected):
    assert parse_salary(text) == expected


# ── VND upper-bound (tới / up to) ────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("Tới 35 triệu",           (None, 35_000_000, "VND")),
    ("tới 50 tr",              (None, 50_000_000, "VND")),
    ("Up to 20 triệu",         (None, 20_000_000, "VND")),
    ("lên đến 30 triệu",       (None, 30_000_000, "VND")),
])
def test_vnd_up_to(text, expected):
    assert parse_salary(text) == expected


# ── VND lower-bound (trên / từ) ──────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("Trên 10 triệu",          (10_000_000, None, "VND")),
    ("từ 8 triệu",             (8_000_000,  None, "VND")),
])
def test_vnd_above(text, expected):
    assert parse_salary(text) == expected


# ── VND exact ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("15 triệu",               (15_000_000, 15_000_000, "VND")),
    ("~15 tr",                 (15_000_000, 15_000_000, "VND")),
])
def test_vnd_exact(text, expected):
    assert parse_salary(text) == expected


# ── USD ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("$1,500 - $2,000",        (1500, 2000, "USD")),
    ("1500 - 2000 USD",        (1500, 2000, "USD")),
    ("Tới 2,000 USD",          (None, 2000, "USD")),
    ("Trên 1,000 USD",         (1000, None, "USD")),
    ("$1,500",                 (1500, 1500, "USD")),
])
def test_usd(text, expected):
    assert parse_salary(text) == expected


# ── Negotiable / empty / None ─────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "thoả thuận",
    "Thoả Thuận",
    "Negotiable",
    "negotiable",
    None,
    "",
    "nan",
])
def test_no_salary(text):
    assert parse_salary(text) == (None, None, None)
