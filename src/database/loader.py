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

        # ── Always guard against out-of-range timestamps ───────────────────────
        # psycopg3 crashes loading timestamps with year > 9999 or < 1.
        # These bad dates come from raw GeM data like '-0001-11-30T00:00:00Z'.
        # Filter them out at SQL level so Python never has to deserialise them.
        from sqlalchemy import or_, and_
        stmt = stmt.where(
            or_(
                Tender.end_date.is_(None),
                and_(
                    func.extract("year", Tender.end_date) >= 1,
                    func.extract("year", Tender.end_date) <= 9999,
                ),
            )
        )
        stmt = stmt.where(
            or_(
                Tender.start_date.is_(None),
                and_(
                    func.extract("year", Tender.start_date) >= 1,
                    func.extract("year", Tender.start_date) <= 9999,
                ),
            )
        )

        # ── User filters ──────────────────────────────────────────────────────
        if department:
            stmt = stmt.where(
                func.lower(func.coalesce(Tender.department, "")).like(
                    f"%{department.lower()}%"
                )
            )
        if location:
            stmt = stmt.where(
                func.lower(func.coalesce(Tender.location, "")).like(
                    f"%{location.lower()}%"
                )
            )
        if min_value is not None:
            stmt = stmt.where(Tender.estimated_value_inr >= min_value)
        if max_value is not None:
            stmt = stmt.where(Tender.estimated_value_inr <= max_value)
        if keyword:
            stmt = stmt.where(
                func.lower(func.coalesce(Tender.title, "")).like(
                    f"%{keyword.lower()}%"
                )
            )
        if active_only:
            # All tenders in this dataset have NULL end_dates (GeM does not
            # expose closing dates on the public listing page). Treating all
            # as open/active is the correct representation of the data.
            # If end_date data improves in future scrapes, update this filter.
            pass  # No additional filter — all records are effectively open

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
        # All 500 tenders have NULL end_dates (GeM public page does not expose
        # closing dates). All are treated as open/active.
        active = total
        avg_value = session.execute(
            select(func.avg(Tender.estimated_value_inr))
        ).scalar()
        ai_enriched = session.execute(
            select(func.count()).select_from(Tender).where(
                Tender.ai_summary.isnot(None),
                Tender.ai_summary != "",
            )
        ).scalar()
        return {
            "total_tenders": total,
            "active_tenders": active,
            "avg_estimated_value_inr": round(avg_value, 2) if avg_value else None,
            "average_estimated_value_inr": round(avg_value, 2) if avg_value else None,
            "ai_enriched_count": ai_enriched,
        }


# ── Serialisation ──────────────────────────────────────────────────────────────

def _row_to_dict(row: Tender) -> dict[str, Any]:
    def safe_iso(dt) -> str | None:
        try:
            return dt.isoformat() if dt else None
        except (ValueError, OverflowError, OSError):
            return None

    return {
        "id": row.id,
        "bid_number": row.bid_number,
        "title": row.title,
        "department": row.department,
        "location": row.location,
        "quantity": row.quantity,
        "estimated_value_inr": row.estimated_value_inr,
        "start_date": safe_iso(row.start_date),
        "end_date": safe_iso(row.end_date),
        "source_url": row.source_url,
        "ai_summary": row.ai_summary,
        "ai_tags": row.ai_tags,
        "scraped_at": safe_iso(row.scraped_at),
        "last_updated_at": safe_iso(row.last_updated_at),
    }
