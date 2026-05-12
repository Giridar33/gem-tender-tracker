"""
main.py
───────
FastAPI application factory for the GEM Tender Tracker API.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.api.ai_routes import ai_router
from src.database.models import create_all_tables

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure tables exist on first boot (idempotent)."""
    create_all_tables()
    yield


app = FastAPI(
    title="GEM Tender Tracker API",
    description=(
        "Live, filtered access to Government e-Marketplace (GeM) "
        "tender listings — updated daily via an automated pipeline."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(ai_router)
