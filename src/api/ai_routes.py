"""
ai_routes.py
────────────
Gemini AI enrichment endpoints.

Endpoints
---------
POST /tenders/{id}/enrich        → enrich a single tender with Gemini
POST /ai/enrich-batch            → background-enrich all un-enriched tenders
GET  /ai/status                  → check whether Gemini is configured
"""

from __future__ import annotations

import logging
import os
import threading

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.ai.enrich import enrich_tender, _get_model
from src.database.loader import _row_to_dict, upsert_tenders
from src.database.models import Tender, engine

import pandas as pd

logger = logging.getLogger(__name__)
ai_router = APIRouter(tags=["AI Enrichment"])

# Prevent concurrent batch jobs
_batch_lock = threading.Lock()
_batch_running = False


# ── Status ────────────────────────────────────────────────────────────────────

@ai_router.get("/ai/status")
def ai_status():
    """Return whether Gemini AI enrichment is enabled and the model in use."""
    model = _get_model()
    if model is None:
        return {
            "enabled": False,
            "reason": "GEMINI_API_KEY is not set or google-generativeai is not installed.",
            "model": None,
        }
    return {
        "enabled": True,
        "model": "gemini-2.0-flash",
        "free_tier_rpm": 15,
        "free_tier_daily": 1500,
    }


@ai_router.get("/ai/test-gemini")
def test_gemini():
    """Debug endpoint: call Gemini with a simple prompt and return the raw response."""
    client = _get_model()
    if client is None:
        return {"success": False, "error": "GEMINI_API_KEY not configured"}
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents='Respond ONLY with this exact JSON: {"summary": "test ok", "tags": "test"}',
        )
        return {"success": True, "raw_response": response.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Single tender enrichment ───────────────────────────────────────────────────

@ai_router.post("/tenders/{tender_id}/enrich")
def enrich_single(tender_id: int):
    """
    Enrich a single tender with a Gemini-generated summary and tags.

    Overwrites any existing ai_summary / ai_tags for this record.
    Returns 503 if GEMINI_API_KEY is not configured.
    """
    model = _get_model()
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="Gemini AI is not configured. Set GEMINI_API_KEY in your environment.",
        )

    with Session(engine) as session:
        tender = session.get(Tender, tender_id)
        if tender is None:
            raise HTTPException(status_code=404, detail=f"Tender {tender_id} not found.")
        record = _row_to_dict(tender)

    enriched = enrich_tender(record)

    # Persist back to DB
    df = pd.DataFrame([enriched])
    upsert_tenders(df)

    return {
        "tender_id": tender_id,
        "bid_number": enriched.get("bid_number"),
        "ai_summary": enriched.get("ai_summary"),
        "ai_tags": enriched.get("ai_tags"),
    }


# ── Batch enrichment ──────────────────────────────────────────────────────────

def _run_batch_enrichment():
    """Background task: enrich all tenders that have no ai_summary yet."""
    global _batch_running
    from src.ai.enrich import enrich_batch
    from sqlalchemy import func, or_, and_

    try:
        with Session(engine) as session:
            stmt = (
                select(Tender)
                .where(
                    (Tender.ai_summary == None) | (Tender.ai_summary == "")  # noqa: E711
                )
                # Safety: exclude rows with out-of-range timestamps that crash psycopg3
                .where(
                    or_(
                        Tender.end_date.is_(None),
                        and_(
                            func.extract("year", Tender.end_date) >= 1,
                            func.extract("year", Tender.end_date) <= 9999,
                        ),
                    )
                )
                .where(
                    or_(
                        Tender.start_date.is_(None),
                        and_(
                            func.extract("year", Tender.start_date) >= 1,
                            func.extract("year", Tender.start_date) <= 9999,
                        ),
                    )
                )
            )
            rows = session.execute(stmt).scalars().all()
            records = [_row_to_dict(r) for r in rows]

        if not records:
            logger.info("Batch enrichment: no un-enriched tenders found.")
            return

        logger.info("Batch enrichment: processing %d tenders.", len(records))
        enriched = enrich_batch(records)
        df = pd.DataFrame(enriched)
        upsert_tenders(df)
        logger.info("Batch enrichment complete.")
    except Exception as exc:
        logger.error("Batch enrichment failed: %s", exc, exc_info=True)
    finally:
        _batch_running = False


@ai_router.post("/ai/enrich-batch")
def trigger_batch_enrichment(background_tasks: BackgroundTasks):
    """
    Kick off a background job to enrich all tenders that have no AI summary yet.

    Only one batch job runs at a time.
    Returns 503 if GEMINI_API_KEY is not configured.
    """
    global _batch_running

    model = _get_model()
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="Gemini AI is not configured. Set GEMINI_API_KEY in your environment.",
        )

    with _batch_lock:
        if _batch_running:
            raise HTTPException(
                status_code=409,
                detail="A batch enrichment job is already running. Please wait.",
            )
        _batch_running = True

    background_tasks.add_task(_run_batch_enrichment)

    return {
        "status": "started",
        "message": "Batch enrichment is running in the background. "
                   "Check /tenders to see ai_summary fields populate.",
    }
