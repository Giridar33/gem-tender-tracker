"""
transform.py
────────────
Cleans and standardises raw GeM tender records.

Design decisions are documented in docs/cleaning_decisions.md.
"""

from __future__ import annotations

import logging
import re
from datetime import timezone

import pandas as pd
from dateutil import parser as dateutil_parser

logger = logging.getLogger(__name__)


# ── Public entry-point ─────────────────────────────────────────────────────────

def clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Accept a raw DataFrame and return a business-ready one.

    Pipeline:
      1. Deduplicate on bid_number.
      2. Normalise text fields (strip, lowercase).
      3. Parse date strings → UTC-aware datetime objects.
      4. Parse estimated_value → float (INR).
      5. Parse quantity → float.
      6. Drop rows missing both bid_number and source_url (unidentifiable).
      7. Add a scraped_at column (UTC now).
    """
    original_len = len(df)

    # 0. Drop debug columns not needed in the database
    if "_raw" in df.columns:
        df = df.drop(columns=["_raw"])

    # 1. Drop exact duplicates, then deduplicate on bid_number (keep first)
    df = df.drop_duplicates()
    df = df.drop_duplicates(subset=["bid_number"], keep="first")
    logger.info("Deduplication: %d -> %d rows", original_len, len(df))

    # 2. Normalise text fields
    text_cols = ["title", "department", "location", "bid_number"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].str.strip().str.lower()

    # 3. Parse dates
    for date_col in ["start_date", "end_date"]:
        if date_col in df.columns:
            df[date_col] = df[date_col].apply(_parse_date)

    # 4. Parse estimated_value
    if "estimated_value" in df.columns:
        df["estimated_value_inr"] = df["estimated_value"].apply(_parse_currency)
        df.drop(columns=["estimated_value"], inplace=True)

    # 5. Parse quantity
    if "quantity" in df.columns:
        df["quantity"] = df["quantity"].apply(_parse_quantity)

    # 6. Drop completely unidentifiable rows
    before = len(df)
    df = df.dropna(subset=["bid_number"])
    if len(df) < before:
        logger.warning("Dropped %d rows with no bid_number.", before - len(df))

    # 7. Metadata timestamp
    df["scraped_at"] = pd.Timestamp.now(tz=timezone.utc)

    logger.info("Cleaning complete. Output rows: %d", len(df))
    return df.reset_index(drop=True)


# ── Helper functions ───────────────────────────────────────────────────────────

def _parse_date(raw: str | None) -> pd.Timestamp | None:
    """Parse a fuzzy date string into a UTC-aware Timestamp, or None."""
    if not raw or str(raw).strip().lower() in {"", "nan", "none", "n/a", "-"}:
        return None
    try:
        dt = dateutil_parser.parse(str(raw), dayfirst=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return pd.Timestamp(dt)
    except (ValueError, OverflowError):
        logger.debug("Could not parse date: %r", raw)
        return None


def _parse_currency(raw: str | None) -> float | None:
    """Strip INR symbols, commas, and text; return float or None."""
    if not raw or str(raw).strip().lower() in {"", "nan", "none", "n/a", "-"}:
        return None
    # Remove currency symbols, commas, whitespace, and unit suffixes
    cleaned = re.sub(r"[₹,\s]", "", str(raw))
    # Handle shorthand: 1.5L → 150000, 2.3Cr → 23000000
    lakh_match = re.match(r"^([\d.]+)[lL]$", cleaned)
    crore_match = re.match(r"^([\d.]+)[cC][rR]?$", cleaned)
    if lakh_match:
        return float(lakh_match.group(1)) * 1e5
    if crore_match:
        return float(crore_match.group(1)) * 1e7
    try:
        return float(re.sub(r"[^\d.]", "", cleaned))
    except ValueError:
        logger.debug("Could not parse currency: %r", raw)
        return None


def _parse_quantity(raw: str | None) -> float | None:
    """Extract the numeric portion of a quantity string, or None."""
    if not raw or str(raw).strip().lower() in {"", "nan", "none", "n/a", "-"}:
        return None
    match = re.search(r"[\d,]+\.?\d*", str(raw).replace(",", ""))
    if match:
        try:
            return float(match.group().replace(",", ""))
        except ValueError:
            pass
    return None
