"""Unit tests for address parsing."""

import pytest
from etl.transform.address import parse_address, parse_address_locations


# ── parse_address_locations ───────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    # single city, no district
    ("Hà Nội",
     [("Hà Nội", None)]),

    # single city + single district
    ("Hà Nội: Cầu Giấy",
     [("Hà Nội", "Cầu Giấy")]),

    # single city + comma-separated districts
    ("Hồ Chí Minh: Bình Thạnh, Phú Nhuận, Gò Vấp",
     [("Hồ Chí Minh", "Bình Thạnh"),
      ("Hồ Chí Minh", "Phú Nhuận"),
      ("Hồ Chí Minh", "Gò Vấp")]),

    # two city:district blocks
    ("Hà Nội: Cầu Giấy: Hồ Chí Minh: Quận 7",
     [("Hà Nội", "Cầu Giấy"),
      ("Hồ Chí Minh", "Quận 7")]),

    # mixed: city+multi-district, then city+district
    ("Hồ Chí Minh: Bình Thạnh, Phú Nhuận: Hà Nội: Cầu Giấy",
     [("Hồ Chí Minh", "Bình Thạnh"),
      ("Hồ Chí Minh", "Phú Nhuận"),
      ("Hà Nội", "Cầu Giấy")]),

    # four-segment two-region pattern
    ("Hà Nội: Thanh Xuân: Hải Dương: TP Hải Dương",
     [("Hà Nội", "Thanh Xuân"),
      ("Hải Dương", "TP Hải Dương")]),

    # nationwide (no colon)
    ("Toàn Quốc",
     [("Toàn Quốc", None)]),
])
def test_parse_address_locations(text, expected):
    assert parse_address_locations(text) == expected


@pytest.mark.parametrize("text", [None, "", "nan"])
def test_parse_address_locations_empty(text):
    assert parse_address_locations(text) == []


# ── parse_address (first pair only) ──────────────────────────────────────────

def test_parse_address_returns_first():
    assert parse_address("Hà Nội: Cầu Giấy: Hồ Chí Minh: Quận 7") == ("Hà Nội", "Cầu Giấy")


def test_parse_address_no_district():
    assert parse_address("Hà Nội") == ("Hà Nội", None)


def test_parse_address_none():
    assert parse_address(None) == (None, None)
