# Architecture

## System Overview

```
GeM Portal (bidplus.gem.gov.in)
        │
        ▼
┌─────────────────────────┐
│  src/scraper/fetcher.py │  Paginated HTTP requests + retries (tenacity)
│  src/scraper/parser.py  │  BeautifulSoup HTML extraction
└───────────┬─────────────┘
            │ raw list[dict]
            ▼
   data/raw/<timestamp>.json   ← raw backup (gitignored)
            │
            ▼
┌─────────────────────────────┐
│  src/cleaning/transform.py  │  pandas dedup, normalise, parse dates/currency
└───────────┬─────────────────┘
            │ clean DataFrame
            ▼
┌──────────────────────────────┐
│  src/database/loader.py      │  upsert into PostgreSQL / SQLite
│  src/database/models.py      │  SQLAlchemy ORM schema
└───────────┬──────────────────┘
            │
            ▼
    PostgreSQL (production)
    SQLite    (development)
            │
            ▼
┌──────────────────────────────┐
│  src/api/main.py             │  FastAPI app
│  src/api/routes.py           │  GET /tenders, /tenders/{id}, /stats/summary
└──────────────────────────────┘
            │
            ▼
    Business User / Dashboard

──────── Automation ─────────
GitHub Actions cron → python -m src.scheduler (daily @ 02:00 UTC)
APScheduler daemon  → optional for self-hosted deployment
```

## Component Responsibilities

| Component | File(s) | Role |
|-----------|---------|------|
| Fetcher | `src/scraper/fetcher.py` | HTTP + pagination + retry |
| Parser | `src/scraper/parser.py` | HTML → raw dict list |
| Cleaner | `src/cleaning/transform.py` | Normalise + validate |
| Models | `src/database/models.py` | ORM schema + indexes |
| Loader | `src/database/loader.py` | Upsert + query helpers |
| API | `src/api/` | FastAPI endpoints |
| Scheduler | `src/scheduler.py` | Pipeline orchestrator |
| AI | `src/ai/enrich.py` | Optional LLM enrichment |

## Data Flow Sequence

1. **Cron trigger** fires (GitHub Actions or APScheduler).
2. `scheduler.py` calls `scraper → parser → save_raw`.
3. Raw data written to `data/raw/<ts>.json` (local backup).
4. `transform.clean()` normalises the DataFrame.
5. `loader.upsert_tenders()` inserts/updates the DB.
6. API reads from DB on every user request (live data).
