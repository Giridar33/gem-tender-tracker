"""
fetcher.py
──────────
Handles all HTTP communication with bidplus.gem.gov.in.

Responsibilities:
 - Paginate through /all-bids until no records remain.
 - Retry transient failures with exponential back-off (tenacity).
 - Save raw JSON to data/raw/ with a UTC timestamp in the filename.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.scraper.parser import parse_page

logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://bidplus.gem.gov.in/all-bids"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Retry decorator ────────────────────────────────────────────────────────────

@retry(
    retry=retry_if_exception_type(requests.RequestException),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _get(session: requests.Session, url: str, params: dict, timeout: int) -> requests.Response:
    response = session.get(url, params=params, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response


# ── Main scrape entry-point ────────────────────────────────────────────────────

def scrape_all_bids(
    base_url: str = BASE_URL,
    max_pages: int = 50,
    request_delay: float = 1.5,
    timeout: int = 15,
) -> list[dict]:
    """
    Iterate through paginated bid listings and return a list of raw record dicts.

    Parameters
    ----------
    base_url     : Landing page URL for GeM bid listings.
    max_pages    : Hard cap on pages fetched per run (safety valve).
    request_delay: Seconds to sleep between requests (politeness).
    timeout      : HTTP request timeout in seconds.

    Returns
    -------
    list[dict]   : Flat list of raw tender records.
    """
    results: list[dict] = []
    session = requests.Session()

    for page in range(1, max_pages + 1):
        params = {"page": page}
        logger.info("Fetching page %d …", page)

        try:
            response = _get(session, base_url, params, timeout)
        except requests.RequestException as exc:
            logger.error("Page %d permanently failed: %s — skipping.", page, exc)
            continue

        records = parse_page(response.text)
        if not records:
            logger.info("No records on page %d — stopping pagination.", page)
            break

        logger.info("Page %d → %d records.", page, len(records))
        results.extend(records)
        time.sleep(request_delay)

    logger.info("Scrape complete. Total records: %d", len(results))
    return results


# ── Raw-data persistence ───────────────────────────────────────────────────────

def save_raw(records: list[dict]) -> Path:
    """Persist raw records to data/raw/<timestamp>.json and return the path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RAW_DIR / f"gem_bids_{ts}.json"
    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Raw data saved → %s", out_path)
    return out_path
