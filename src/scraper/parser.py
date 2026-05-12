"""
parser.py
---------
Parses a single HTML page of GeM bid listings into structured dicts.

Selectors verified against live bidplus.gem.gov.in/all-bids on 2026-05-12.

Page structure (Bootstrap grid, card-style):
  div#pagi_content
    div.col-md-12.border.block   <-- one card per bid
      div.col-md-9
        p  > strong "BID NO:"  + a.bid_no_hover  (href=/showbidDocument/<id>)
        div (width:50%; float:left)
          p  > strong "Items:"  + a (title text)
          p  > strong "Quantity:"  + text
        div (width:50%; float:left)
          p  > strong "Department Name And Address:"
          p  (organisation name, e.g. "PMO")
          p  (ministry/dept, e.g. "Department of Atomic Energy")
      div.col-md-3
        p  > strong "Start Date:"  + span.start_date
        p  > strong "End Date:"    + span.end_date
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

BASE = "https://bidplus.gem.gov.in"


def _text(tag, default=None) -> str | None:
    """Strip and return text from a BS4 tag, or default if None."""
    if tag is None:
        return default
    t = tag.get_text(strip=True)
    return t if t else default


def parse_page(html: str) -> list[dict]:
    """
    Parse a GeM /all-bids HTML page.

    Returns a list of dicts with keys:
      bid_number, title, department, quantity,
      start_date, end_date, estimated_value, location, source_url
    """
    soup = BeautifulSoup(html, "lxml")
    records: list[dict] = []

    # Each bid is inside div.col-md-12.border.block
    cards = soup.select("div.col-md-12.border.block")
    logger.debug("Found %d bid cards on page.", len(cards))

    for card in cards:
        try:
            record = _extract(card)
            if record.get("bid_number"):
                records.append(record)
        except Exception as exc:          # noqa: BLE001
            logger.warning("Skipping malformed card: %s", exc)

    return records


def _extract(card: Tag) -> dict:
    # ── Bid number + source URL ────────────────────────────────────────────────
    bid_link = card.select_one("a.bid_no_hover")
    bid_number = _text(bid_link)
    href = bid_link.get("href", "") if bid_link else ""
    source_url = (BASE + href) if href and not href.startswith("http") else href or None

    # ── Left column (col-md-9) ────────────────────────────────────────────────
    left = card.select_one("div.col-md-9, div.col-xs-12")

    # Title: first <a> after "Items:" strong
    title = None
    items_label = _find_strong(card, "Items:")
    if items_label:
        items_a = items_label.find_next("a")
        title = _text(items_a)

    # Quantity: text after "Quantity:" strong
    quantity = None
    qty_label = _find_strong(card, "Quantity:")
    if qty_label:
        # The quantity text is a direct sibling after the <strong>
        qty_text = qty_label.next_sibling
        if qty_text:
            quantity = str(qty_text).strip() or None

    # Department: the <p> tags immediately after "Department Name And Address:"
    department = None
    dept_label = _find_strong(card, "Department Name And Address:")
    if dept_label:
        dept_p = dept_label.find_parent("p")
        if dept_p:
            # Grab the next 1-2 sibling <p> tags as department name
            siblings = [p for p in dept_p.find_next_siblings("p") if p.get_text(strip=True)][:2]
            department = " | ".join(p.get_text(strip=True) for p in siblings) or None

    # ── Right column (col-md-3) dates ─────────────────────────────────────────
    start_date = _text(card.select_one("span.start_date"))
    end_date = _text(card.select_one("span.end_date"))

    return {
        "bid_number": bid_number,
        "title": title,
        "department": department,
        "quantity": quantity,
        "start_date": start_date,
        "end_date": end_date,
        "estimated_value": None,   # not shown in listing cards; available in detail page
        "location": None,          # embedded in department address text
        "source_url": source_url,
    }


def _find_strong(card: Tag, label: str):
    """Return the <strong> tag whose text starts with label, or None."""
    for strong in card.find_all("strong"):
        if strong.get_text(strip=True).startswith(label.rstrip(":")):
            return strong
    return None
