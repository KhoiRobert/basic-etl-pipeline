"""Unit tests for address parsing."""

import pytest
from etl.transform.address import parse_address, parse_address_locations


# ── parse_address_locations — colon-block format ──────────────────────────────

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


# ── (mới) badge stripping ─────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    # badge on single city
    ("Hồ Chí Minh (mới)",
     [("Hồ Chí Minh", None)]),

    # badge on second city
    ("Bắc Ninh (mới)",
     [("Bắc Ninh", None)]),

    # city without badge unchanged
    ("Hà Nội",
     [("Hà Nội", None)]),
])
def test_badge_stripped(text, expected):
    assert parse_address_locations(text) == expected


# ── & multi-city separator ────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    # two clean cities
    ("Hà Nội & Đà Nẵng",
     [("Hà Nội", None), ("Đà Nẵng", None)]),

    # badge on second city
    ("Hà Nội & Hồ Chí Minh (mới)",
     [("Hà Nội", None), ("Hồ Chí Minh", None)]),

    # badge on first city
    ("Hồ Chí Minh (mới) & Hà Nội",
     [("Hồ Chí Minh", None), ("Hà Nội", None)]),

    # three cities with badges
    ("Hà Nội & Hồ Chí Minh (mới) & Đà Nẵng (mới)",
     [("Hà Nội", None), ("Hồ Chí Minh", None), ("Đà Nẵng", None)]),

    # badge + port city
    ("Hải Phòng (mới) & Hà Nội",
     [("Hải Phòng", None), ("Hà Nội", None)]),
])
def test_ampersand_multi_city(text, expected):
    assert parse_address_locations(text) == expected


# ── "X nơi khác" discard ─────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    # single vague entry — nothing kept
    ("5 nơi khác",
     []),

    # city + vague remainder
    ("Hà Nội & 5 nơi khác",
     [("Hà Nội", None)]),

    # city with badge + vague remainder
    ("Hồ Chí Minh (mới) & 2 nơi khác",
     [("Hồ Chí Minh", None)]),

    # large number
    ("Hà Nội & 33 nơi khác",
     [("Hà Nội", None)]),
])
def test_other_places_discarded(text, expected):
    assert parse_address_locations(text) == expected


# ── parse_address (first pair only) ──────────────────────────────────────────

def test_parse_address_returns_first():
    assert parse_address("Hà Nội: Cầu Giấy: Hồ Chí Minh: Quận 7") == ("Hà Nội", "Cầu Giấy")


def test_parse_address_no_district():
    assert parse_address("Hà Nội") == ("Hà Nội", None)


def test_parse_address_none():
    assert parse_address(None) == (None, None)


def test_parse_address_badge():
    assert parse_address("Hồ Chí Minh (mới)") == ("Hồ Chí Minh", None)


def test_parse_address_ampersand_returns_first():
    assert parse_address("Hà Nội & Hồ Chí Minh (mới)") == ("Hà Nội", None)
