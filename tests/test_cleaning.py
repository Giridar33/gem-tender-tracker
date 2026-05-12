"""
test_cleaning.py
────────────────
Unit tests for src/cleaning/transform.py.
"""

import pandas as pd
import pytest
from src.cleaning.transform import _parse_currency, _parse_date, _parse_quantity, clean


# ── _parse_date ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected_not_none", [
    ("01/06/2024", True),
    ("June 1, 2024", True),
    ("2024-06-01", True),
    ("", False),
    (None, False),
    ("N/A", False),
    ("not-a-date", False),
])
def test_parse_date(raw, expected_not_none):
    result = _parse_date(raw)
    if expected_not_none:
        assert result is not None
    else:
        assert result is None


# ── _parse_currency ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("₹5,00,000", 500000.0),
    ("2.5L", 250000.0),
    ("1Cr", 10000000.0),
    ("100000", 100000.0),
    ("", None),
    (None, None),
    ("N/A", None),
])
def test_parse_currency(raw, expected):
    assert _parse_currency(raw) == expected


# ── _parse_quantity ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("100 Nos", 100.0),
    ("50.5 Kg", 50.5),
    ("", None),
    (None, None),
])
def test_parse_quantity(raw, expected):
    assert _parse_quantity(raw) == expected


# ── clean() ───────────────────────────────────────────────────────────────────

def _make_df():
    return pd.DataFrame([
        {
            "bid_number": "GEM/2024/B/001",
            "title": "  Office Chairs  ",
            "department": "Ministry of Finance",
            "location": "Delhi",
            "quantity": "100 Nos",
            "start_date": "01/06/2024",
            "end_date": "30/06/2024",
            "estimated_value": "₹5,00,000",
            "source_url": "https://example.com/1",
        },
        # Duplicate — should be removed
        {
            "bid_number": "GEM/2024/B/001",
            "title": "Office Chairs",
            "department": "Ministry of Finance",
            "location": "Delhi",
            "quantity": "100 Nos",
            "start_date": "01/06/2024",
            "end_date": "30/06/2024",
            "estimated_value": "₹5,00,000",
            "source_url": "https://example.com/1",
        },
    ])


def test_clean_removes_duplicates():
    df = clean(_make_df())
    assert len(df) == 1


def test_clean_strips_whitespace():
    df = clean(_make_df())
    assert df.iloc[0]["title"] == "office chairs"


def test_clean_parses_currency():
    df = clean(_make_df())
    assert df.iloc[0]["estimated_value_inr"] == 500000.0


def test_clean_adds_scraped_at():
    df = clean(_make_df())
    assert "scraped_at" in df.columns
    assert df.iloc[0]["scraped_at"] is not None
