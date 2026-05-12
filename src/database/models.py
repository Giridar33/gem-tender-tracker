"""
models.py
─────────
SQLAlchemy ORM models for the GEM tender tracker.

The `Tender` table is the single source of truth.
Alembic manages schema migrations (see alembic/).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gem_tenders.db").strip()

# Build connect_args based on the database type
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
elif "psycopg" in DATABASE_URL:
    # psycopg3 + pgbouncer Transaction pooler (port 6543):
    # Must disable prepared statements or pgbouncer will reject them.
    _connect_args = {"prepare_threshold": None}
else:
    _connect_args = {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    # Reduce pool size for Railway free tier (512 MB RAM)
    pool_size=2,
    max_overflow=5,
)


class Base(DeclarativeBase):
    pass


class Tender(Base):
    """Represents a single GeM bid / tender listing."""

    __tablename__ = "tenders"

    # ── Identity ──────────────────────────────────────────────────────────────
    # Integer maps to SQLite ROWID (autoincrement); on PostgreSQL it becomes SERIAL.
    id = Column(Integer, primary_key=True, autoincrement=True)
    bid_number = Column(Text, nullable=False, unique=True)   # natural key for upsert
    source_url = Column(Text, nullable=True)

    # ── Core fields ───────────────────────────────────────────────────────────
    title = Column(Text, nullable=True)
    department = Column(Text, nullable=True)
    location = Column(Text, nullable=True)

    # ── Numeric fields ────────────────────────────────────────────────────────
    quantity = Column(Float, nullable=True)
    estimated_value_inr = Column(Float, nullable=True)

    # ── Dates ─────────────────────────────────────────────────────────────────
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    # ── Bonus: AI enrichment ──────────────────────────────────────────────────
    ai_summary = Column(Text, nullable=True)
    ai_tags = Column(Text, nullable=True)     # comma-separated tags

    # ── Metadata ──────────────────────────────────────────────────────────────
    scraped_at = Column(DateTime(timezone=True), nullable=True)
    last_updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_tenders_department", "department"),
        Index("ix_tenders_location", "location"),
        Index("ix_tenders_end_date", "end_date"),
        Index("ix_tenders_estimated_value", "estimated_value_inr"),
    )


def create_all_tables() -> None:
    """Create tables if they do not exist (idempotent)."""
    Base.metadata.create_all(engine)
