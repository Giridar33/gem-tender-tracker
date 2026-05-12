"""
parser.py
─────────
Parses a single HTML page of GeM bid listings into structured dicts.

Responsibilities:
 - Accept raw HTML text.
 - Extract all tender record fields safely (return None for missing values).
 - Return a list of raw dicts — no cleaning here; that belongs in transform.py.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _safe_text(element, default=None) -> str | None:
    """Return stripped text from a BS4 element, or default if element is None."""
    if element is None:
        return default
    return element.get_text(strip=True) or default


def _safe_attr(element, attr: str, default=None) -> str | None:
    if element is None:
        return default
    return element.get(attr, default)


def parse_page(html: str) -> list[dict]:
    """
    Parse a GeM /all-bids HTML page and return a list of raw record dicts.

    Each dict contains the following keys (all may be None if missing):
      - bid_number       : Unique bid/tender reference number
      - title            : Short description / product name
      - department       : Buying organisation / ministry
      - quantity         : Quantity demanded (raw string)
      - start_date       : Bid opening date (raw string)
      - end_date         : Bid closing / last date (raw string)
      - estimated_value  : Estimated bid value (raw string)
      - location         : Delivery / consignee location
      - source_url       : Direct link to the bid detail page
    """
    soup = BeautifulSoup(html, "lxml")
    records: list[dict] = []

    # GeM renders bids inside a table or card structure.
    # Selector is based on the live page structure as of May 2026.
    # Update selectors if GeM changes its markup.
    rows = soup.select("div.bid-card, tr.bid-row, div.card")

    if not rows:
        # Fallback: try to grab any table rows that look like bid data
        rows = soup.select("table tbody tr")

    for row in rows:
        try:
            record = _extract_record(row)
            if record.get("bid_number"):   # must have at least a bid number
                records.append(record)
        except Exception as exc:           # noqa: BLE001
            logger.warning("Skipping malformed row: %s", exc)

    return records


def _extract_record(row) -> dict:
    """Extract a single bid record from a BS4 tag."""
    # ── Try card-style layout first ───────────────────────────────────────────
    bid_number = (
        _safe_text(row.select_one("[class*='bid-no'], [class*='bid_no'], td:nth-child(1)"))
        or _safe_text(row.select_one("strong"))
    )

    title = _safe_text(
        row.select_one("[class*='bid-title'], [class*='title'], td:nth-child(2)")
    )

    department = _safe_text(
        row.select_one("[class*='dept'], [class*='organisation'], td:nth-child(3)")
    )

    quantity = _safe_text(
        row.select_one("[class*='qty'], [class*='quantity'], td:nth-child(4)")
    )

    start_date = _safe_text(
        row.select_one("[class*='start'], [class*='open'], td:nth-child(5)")
    )

    end_date = _safe_text(
        row.select_one("[class*='end'], [class*='close'], [class*='last'], td:nth-child(6)")
    )

    estimated_value = _safe_text(
        row.select_one("[class*='value'], [class*='amount'], [class*='price'], td:nth-child(7)")
    )

    location = _safe_text(
        row.select_one("[class*='location'], [class*='consignee'], td:nth-child(8)")
    )

    # Build the detail URL
    link_tag = row.select_one("a[href]")
    raw_href = _safe_attr(link_tag, "href")
    if raw_href:
        source_url = (
            raw_href
            if raw_href.startswith("http")
            else f"https://bidplus.gem.gov.in{raw_href}"
        )
    else:
        source_url = None

    return {
        "bid_number": bid_number,
        "title": title,
        "department": department,
        "quantity": quantity,
        "start_date": start_date,
        "end_date": end_date,
        "estimated_value": estimated_value,
        "location": location,
        "source_url": source_url,
    }
