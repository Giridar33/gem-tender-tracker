"""
test_api.py
───────────
Integration tests for the FastAPI endpoints using an in-memory SQLite DB.
No real database connection or live scraping needed.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

# ── Set DATABASE_URL before any src imports ─────────────────────────────────────
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Patch the engine BEFORE importing any src modules that use it.
# StaticPool forces all connections to share one in-memory sqlite3 connection.
import src.database.models as _models_module

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_models_module.engine = _test_engine  # monkey-patch before any other import

import src.database.loader as _loader_module
_loader_module.engine = _test_engine  # patch loader too

from src.api.main import app
from src.database.models import Base, Tender


# Build client ONCE — lifespan runs create_all_tables via the patched engine
client = TestClient(app)


def _seed(session: Session) -> None:
    from sqlalchemy import select
    if not session.execute(select(Tender).where(Tender.bid_number == "TEST/001")).scalar_one_or_none():
        session.add(Tender(
            bid_number="TEST/001",
            title="test laptops",
            department="ministry of it",
            location="mumbai",
            quantity=10.0,
            estimated_value_inr=500000.0,
            start_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2099, 12, 31, tzinfo=timezone.utc),
            source_url="https://example.com/test-001",
            last_updated_at=datetime.now(timezone.utc),
        ))
        session.commit()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(_test_engine)
    with Session(_test_engine) as session:
        _seed(session)
    yield
    Base.metadata.drop_all(_test_engine)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_tenders_returns_results():
    resp = client.get("/tenders")
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert data["count"] >= 1


def test_list_tenders_keyword_filter():
    resp = client.get("/tenders?keyword=laptop")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


def test_list_tenders_no_match():
    resp = client.get("/tenders?keyword=xyznonexistent")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_get_tender_by_id():
    results = client.get("/tenders").json()["results"]
    assert len(results) > 0, "Seed failed — no records found"
    tender_id = results[0]["id"]
    resp = client.get(f"/tenders/{tender_id}")
    assert resp.status_code == 200
    assert resp.json()["bid_number"] == "TEST/001"


def test_get_tender_not_found():
    resp = client.get("/tenders/999999")
    assert resp.status_code == 404


def test_summary_stats():
    resp = client.get("/stats/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_tenders" in data
    assert data["total_tenders"] >= 1
