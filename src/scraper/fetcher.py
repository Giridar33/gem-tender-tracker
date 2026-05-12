"""
fetcher.py
----------
Fetches GeM bid listings via the internal JSON API used by the portal.

Discovery (2026-05-12):
  - The /all-bids page loads bids via a POST to /all-bids-data
  - Requires: session cookies from /all-bids + CSRF token matching the cookie
  - Payload:  JSON.stringify({ page: N, param: {}, filter: {} })
  - Response: { code: 200, response: { response: { numFound, docs: [...] } } }

Each doc in the response contains fields like:
  bid_number, bid_title, dept_name, quantity, start_date, end_date,
  estimated_value, location, source_url, etc.
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

logger = logging.getLogger(__name__)

BASE_URL = "https://bidplus.gem.gov.in"
DATA_URL = f"{BASE_URL}/all-bids-data"
LANDING_URL = f"{BASE_URL}/all-bids"

RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": LANDING_URL,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

PAGE_SIZE = 10   # GeM returns 10 records per page


# ── Retry decorator ────────────────────────────────────────────────────────────

@retry(
    retry=retry_if_exception_type(requests.RequestException),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _post(session: requests.Session, payload: dict, csrf: str, timeout: int) -> dict:
    data = {
        "payload": json.dumps(payload),
        "csrf_bd_gem_nk": csrf,
    }
    resp = session.post(DATA_URL, data=data, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ── Session bootstrap ──────────────────────────────────────────────────────────

def _init_session(timeout: int) -> tuple[requests.Session, str]:
    """
    GET the landing page to acquire session cookies and the CSRF token.
    Returns (session, csrf_token).
    """
    session = requests.Session()
    resp = session.get(LANDING_URL, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=timeout)
    resp.raise_for_status()
    csrf = session.cookies.get("csrf_gem_cookie", "")
    if not csrf:
        logger.warning("CSRF cookie not found — requests may be rejected.")
    logger.info("Session initialised. CSRF token: %s...", csrf[:8])
    return session, csrf


# ── Record extraction ──────────────────────────────────────────────────────────

def _val(doc: dict, key: str):
    """Extract the first element if value is a list, else return as-is."""
    v = doc.get(key)
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _parse_doc(doc: dict) -> dict:
    """Map a real GeM API doc dict to our standard record schema."""
    bid_number = _val(doc, "b_bid_number")
    min_name = _val(doc, "ba_official_details_minName") or ""
    dept_name = _val(doc, "ba_official_details_deptName") or ""
    department = " | ".join(filter(None, [min_name, dept_name])) or None

    return {
        "bid_number": bid_number,
        "title": _val(doc, "b_category_name") or _val(doc, "bd_category_name"),
        "department": department,
        "quantity": str(_val(doc, "b_total_quantity") or ""),
        "start_date": _val(doc, "final_start_date_sort"),
        "end_date": _val(doc, "final_end_date_sort"),
        "estimated_value": None,   # not in listing; requires detail page call
        "location": None,
        "source_url": (
            f"{BASE_URL}/showbidDocument/{bid_number}"
            if bid_number else None
        ),
        "_raw": doc,
    }


# ── Main entry-point ───────────────────────────────────────────────────────────

def scrape_all_bids(
    base_url: str = LANDING_URL,
    max_pages: int = 50,
    request_delay: float = 1.5,
    timeout: int = 15,
) -> list[dict]:
    """
    Fetch all GeM bids via the internal JSON API.

    Returns a flat list of raw record dicts.
    """
    session, csrf = _init_session(timeout)
    results: list[dict] = []

    for page in range(1, max_pages + 1):
        payload = {
            "page": page,
            "param": {},
            "filter": {},
        }
        logger.info("Fetching page %d ...", page)

        try:
            data = _post(session, payload, csrf, timeout)
        except requests.RequestException as exc:
            logger.error("Page %d permanently failed: %s -- skipping.", page, exc)
            continue

        if data.get("code") != 200:
            logger.warning("API returned code %s on page %d -- stopping.", data.get("code"), page)
            break

        try:
            docs = data["response"]["response"]["docs"]
        except (KeyError, TypeError):
            logger.warning("Unexpected API structure on page %d -- stopping.", page)
            logger.debug("Raw response: %s", str(data)[:500])
            break

        if not docs:
            logger.info("No records on page %d -- stopping pagination.", page)
            break

        records = [_parse_doc(doc) for doc in docs]
        logger.info("Page %d -> %d records.", page, len(records))
        results.extend(records)
        time.sleep(request_delay)

    logger.info("Scrape complete. Total records: %d", len(results))
    return results


# ── Raw-data persistence ───────────────────────────────────────────────────────

def save_raw(records: list[dict]) -> Path:
    """Persist raw records to data/raw/<timestamp>.json and return the path."""
    # Remove _raw field before saving to keep files smaller
    clean_records = [{k: v for k, v in r.items() if k != "_raw"} for r in records]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RAW_DIR / f"gem_bids_{ts}.json"
    out_path.write_text(
        json.dumps(clean_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Raw data saved -> %s", out_path)
    return out_path
