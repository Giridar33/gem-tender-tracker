"""
scheduler.py
────────────
Pipeline entry-point.  Can be:
  1. Run manually:    python -m src.scheduler
  2. Run by cron:     same command via GitHub Actions / platform cron
  3. Run as a daemon: set RUN_DAEMON=true to keep APScheduler alive

Environment variables (see .env.example):
  DATABASE_URL, SCRAPE_BASE_URL, MAX_PAGES, REQUEST_DELAY, REQUEST_TIMEOUT,
  SCHEDULE_CRON, RUN_DAEMON
"""

from __future__ import annotations

import logging
import os
import sys

import pandas as pd
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

# -- Logging setup --------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scheduler")


def run_pipeline() -> None:
    """Execute one full scrape -> clean -> load cycle."""
    from src.scraper.fetcher import save_raw, scrape_all_bids
    from src.cleaning.transform import clean
    from src.database.loader import upsert_tenders
    from src.database.models import create_all_tables
    from src.ai.enrich import enrich_batch

    logger.info("=== Pipeline started ===")

    # 0. Ensure tables exist
    create_all_tables()

    # 1. Scrape
    base_url = os.getenv("SCRAPE_BASE_URL", "https://bidplus.gem.gov.in/all-bids")
    max_pages = int(os.getenv("MAX_PAGES", "50"))
    request_delay = float(os.getenv("REQUEST_DELAY", "1.5"))
    timeout = int(os.getenv("REQUEST_TIMEOUT", "15"))

    raw_records = scrape_all_bids(
        base_url=base_url,
        max_pages=max_pages,
        request_delay=request_delay,
        timeout=timeout,
    )
    if not raw_records:
        logger.warning("No records scraped — aborting pipeline.")
        return

    save_raw(raw_records)

    # 2. Clean
    df_raw = pd.DataFrame(raw_records)
    df_clean = clean(df_raw)

    # 3. AI Enrichment (skipped gracefully if GEMINI_API_KEY is not set)
    records = df_clean.to_dict(orient="records")
    enriched_records = enrich_batch(records)
    df_enriched = pd.DataFrame(enriched_records)

    # 4. Load
    upserted = upsert_tenders(df_enriched)
    logger.info("=== Pipeline complete. %d records upserted. ===", upserted)


# -- Entry-point ----------------------------------------------------------------

if __name__ == "__main__":
    run_daemon = os.getenv("RUN_DAEMON", "false").lower() == "true"

    if run_daemon:
        cron_expr = os.getenv("SCHEDULE_CRON", "0 2 * * *")
        logger.info("Daemon mode: scheduling pipeline with cron '%s'", cron_expr)
        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(run_pipeline, CronTrigger.from_crontab(cron_expr))
        # Run once immediately on start
        run_pipeline()
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")
    else:
        # Single-shot mode (used by GitHub Actions / manual runs)
        run_pipeline()
