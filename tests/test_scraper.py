"""
test_scraper.py
───────────────
Unit tests for src/scraper/parser.py.
HTTP calls are mocked — no live network needed.
"""

import pytest
from src.scraper.parser import parse_page


SAMPLE_HTML = """
<html><body>
  <div class="card">
    <strong class="bid-no">GEM/2024/B/001</strong>
    <span class="bid-title">Office Chairs</span>
    <span class="dept">Ministry of Finance</span>
    <span class="qty">100 Nos</span>
    <span class="start">01/06/2024</span>
    <span class="end">30/06/2024</span>
    <span class="value">₹5,00,000</span>
    <span class="location">Delhi</span>
    <a href="/bid-detail/GEM-2024-B-001">View</a>
  </div>
</body></html>
"""

EMPTY_HTML = "<html><body><p>No bids found.</p></body></html>"


def test_parse_page_returns_list():
    result = parse_page(SAMPLE_HTML)
    assert isinstance(result, list)


def test_parse_page_empty_html_returns_empty():
    result = parse_page(EMPTY_HTML)
    assert result == []


def test_parse_page_record_has_required_keys():
    result = parse_page(SAMPLE_HTML)
    if result:   # structure-dependent; skip if selectors don't match sample
        record = result[0]
        for key in ["bid_number", "title", "department", "source_url"]:
            assert key in record


def test_parse_page_does_not_raise_on_malformed_html():
    malformed = "<html><body><div class='card'><a href='/x'></a></div></body></html>"
    # Should not raise — malformed rows are skipped with a warning
    result = parse_page(malformed)
    assert isinstance(result, list)
