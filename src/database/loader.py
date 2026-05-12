"""
loader.py
─────────
Handles upsert logic and query helpers for the Tender table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from src.database.models import Tender, engine

logger = logging.getLogger(__name__)


# ── Write path ─────────────────────────────────────────────────────────────────

def upsert_tenders(df: pd.DataFrame) -> int:
    """
    Upsert a cleaned DataFrame into the tenders table.

    Uses per-dialect conflict handling so the same code works with
    SQLite (dev) and PostgreSQL (production).

    Returns the number of rows processed.
    """
    if df.empty:
        logger.warning("upsert called with empty DataFrame — skipping.")
        return 0

    records = df.to_dict(orient="records")
    now = datetime.now(timezone.utc)
    upserted = 0

    with Session(engine) as session:
        for rec in records:
            rec["last_updated_at"] = now
            bid_number = rec.get("bid_number")
            if not bid_number:
                logger.warning("Skipping record with no bid_number: %r", rec)
                continue

            existing = session.execute(
                select(Tender).where(Tender.bid_number == bid_number)
            ).scalar_one_or_none()

            if existing:
                for key, value in rec.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
            else:
                session.add(Tender(**{k: v for k, v in rec.items() if hasattr(Tender, k)}))

            upserted += 1

        session.commit()

    logger.info("Upserted %d records.", upserted)
    return upserted


# ── Read path ──────────────────────────────────────────────────────────────────

def query_tenders(
    department: str | None = None,
    location: str | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    keyword: str | None = None,
    active_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Return filtered tender records as a list of dicts."""
    with Session(engine) as session:
        stmt = select(Tender)

        if department:
            stmt = stmt.where(Tender.department.ilike(f"%{department}%"))
        if location:
            stmt = stmt.where(Tender.location.ilike(f"%{location}%"))
        if min_value is not None:
            stmt = stmt.where(Tender.estimated_value_inr >= min_value)
        if max_value is not None:
            stmt = stmt.where(Tender.estimated_value_inr <= max_value)
        if keyword:
            stmt = stmt.where(Tender.title.ilike(f"%{keyword}%"))
        if active_only:
            now = datetime.now(timezone.utc)
            stmt = stmt.where(Tender.end_date >= now)

        stmt = stmt.order_by(Tender.last_updated_at.desc()).limit(limit).offset(offset)
        rows = session.execute(stmt).scalars().all()
        return [_row_to_dict(r) for r in rows]


def get_tender_by_id(tender_id: int) -> dict | None:
    with Session(engine) as session:
        row = session.get(Tender, tender_id)
        return _row_to_dict(row) if row else None


def get_summary_stats() -> dict:
    """Return aggregated counts and value stats."""
    with Session(engine) as session:
        total = session.execute(select(func.count()).select_from(Tender)).scalar()
        now = datetime.now(timezone.utc)
        active = session.execute(
            select(func.count()).select_from(Tender).where(Tender.end_date >= now)
        ).scalar()
        avg_value = session.execute(
            select(func.avg(Tender.estimated_value_inr))
        ).scalar()
        return {
            "total_tenders": total,
            "active_tenders": active,
            "average_estimated_value_inr": round(avg_value, 2) if avg_value else None,
        }


# ── Serialisation ──────────────────────────────────────────────────────────────

def _row_to_dict(row: Tender) -> dict[str, Any]:
    return {
        "id": row.id,
        "bid_number": row.bid_number,
        "title": row.title,
        "department": row.department,
        "location": row.location,
        "quantity": row.quantity,
        "estimated_value_inr": row.estimated_value_inr,
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "end_date": row.end_date.isoformat() if row.end_date else None,
        "source_url": row.source_url,
        "ai_summary": row.ai_summary,
        "ai_tags": row.ai_tags,
        "scraped_at": row.scraped_at.isoformat() if row.scraped_at else None,
        "last_updated_at": row.last_updated_at.isoformat() if row.last_updated_at else None,
    }
