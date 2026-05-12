"""
routes.py
─────────
All API endpoint definitions.

Endpoints
---------
GET /health             → service health check
GET /tenders            → filtered, paginated list of tenders
GET /tenders/{id}       → single tender detail
GET /stats/summary      → aggregated counts and value stats
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from src.database.loader import get_summary_stats, get_tender_by_id, query_tenders

router = APIRouter()


@router.get("/health", tags=["Meta"])
def health_check():
    """Returns 200 OK when the service is running."""
    return {"status": "ok"}


@router.get("/tenders", tags=["Tenders"])
def list_tenders(
    department: str | None = Query(None, description="Filter by buying department (partial match)"),
    location: str | None = Query(None, description="Filter by consignee location (partial match)"),
    keyword: str | None = Query(None, description="Keyword search in tender title"),
    min_value: float | None = Query(None, ge=0, description="Minimum estimated value (INR)"),
    max_value: float | None = Query(None, ge=0, description="Maximum estimated value (INR)"),
    active_only: bool = Query(False, description="Only return tenders whose closing date is in the future"),
    limit: int = Query(20, ge=1, le=200, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    List GeM tender listings with optional filters.

    Example usage:
    - `/tenders?department=defence&active_only=true`
    - `/tenders?keyword=laptop&min_value=100000&limit=50`
    """
    results = query_tenders(
        department=department,
        location=location,
        keyword=keyword,
        min_value=min_value,
        max_value=max_value,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return {"count": len(results), "results": results}


@router.get("/tenders/{tender_id}", tags=["Tenders"])
def get_tender(tender_id: int):
    """Fetch a single tender by its internal database ID."""
    tender = get_tender_by_id(tender_id)
    if tender is None:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} not found.")
    return tender


@router.get("/stats/summary", tags=["Stats"])
def summary_stats():
    """Return aggregated pipeline statistics (total, active, average value)."""
    return get_summary_stats()
