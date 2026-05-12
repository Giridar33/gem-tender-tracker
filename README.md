# GEM Tender Tracker

> **Real-time B2B data pipeline** that scrapes, cleans, and serves
> [Government e-Marketplace (GeM)](https://bidplus.gem.gov.in/all-bids)
> tender listings via a filtered REST API — updated daily, zero manual intervention.

---

## Problem Statement

Indian procurement teams and vendors waste hours manually browsing the GeM portal
to find relevant tenders. This project automates that process: a daily pipeline
pulls all active bids, standardises the data, and exposes a fast, filterable API
so any business user can find relevant opportunities in seconds.

---

## Architecture

```
GeM Portal (bidplus.gem.gov.in)
        │
        ▼
┌─────────────────────────────┐
│  Scraper (fetcher + parser) │  Paginated HTTP • retries • safe defaults
└───────────┬─────────────────┘
            │ raw records
            ▼
   data/raw/<timestamp>.json
            │
            ▼
┌──────────────────────────────┐
│  Cleaner (transform.py)      │  dedup • normalise • parse dates/currency
└───────────┬──────────────────┘
            │ clean DataFrame
            ▼
┌──────────────────────────────┐
│  Database (PostgreSQL/SQLite)│  upsert on bid_number
└───────────┬──────────────────┘
            │
            ▼
┌──────────────────────────────┐
│  FastAPI (routes.py)         │  GET /tenders • /tenders/{id} • /stats/summary
└──────────────────────────────┘

──────── Automation ─────────
GitHub Actions cron  →  python -m src.scheduler  (daily @ 02:00 UTC)
APScheduler daemon   →  RUN_DAEMON=true           (self-hosted)
```

Full details: [`docs/architecture.md`](docs/architecture.md)

---

## Features

| Layer | What it does |
|-------|-------------|
| **Scraper** | Paginates all GeM bids, retries failures with exponential back-off |
| **Parser** | Extracts 9 fields per record; uses safe defaults for missing values |
| **Cleaner** | Deduplicates, normalises text, parses dates/currency/quantity |
| **Database** | Upsert-safe schema with 4 indexes for common filter patterns |
| **API** | `/tenders` with filters: department, location, keyword, value range, active-only |
| **Automation** | GitHub Actions cron (daily) or APScheduler daemon |
| **AI Bonus** | GPT-4o-mini generates plain-English summaries and category tags |

---

## Quick Start (Local)

### 1. Clone and set up environment

```bash
git clone https://github.com/<your-username>/gem-tender-tracker.git
cd gem-tender-tracker

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env — at minimum set DATABASE_URL
```

For local development, SQLite works out of the box with no extra setup:
```
DATABASE_URL=sqlite:///./gem_tenders.db
```

### 3. Run the pipeline once

```bash
python -m src.scheduler
```

This scrapes GeM, cleans the data, and loads it into your database.

### 4. Start the API

```bash
uvicorn src.api.main:app --reload
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive API docs.

---

## API Reference

### `GET /health`
```json
{ "status": "ok" }
```

### `GET /tenders`

| Query param | Type | Description |
|-------------|------|-------------|
| `department` | string | Partial match on department name |
| `location` | string | Partial match on location |
| `keyword` | string | Full-text search on tender title |
| `min_value` | float | Minimum estimated value (INR) |
| `max_value` | float | Maximum estimated value (INR) |
| `active_only` | bool | Only return open tenders |
| `limit` | int | Max results (default 20, max 200) |
| `offset` | int | Pagination offset |

**Example:**
```
GET /tenders?department=defence&active_only=true&limit=50
```

### `GET /tenders/{id}`
Returns a single tender by database ID.

### `GET /stats/summary`
```json
{
  "total_tenders": 12450,
  "active_tenders": 3210,
  "average_estimated_value_inr": 847500.0
}
```

---

## Running Tests

```bash
pytest tests/ -v
```

Tests use an **in-memory SQLite database** — no external services required.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | ✅ | `sqlite:///./gem_tenders.db` | DB connection string |
| `SCRAPE_BASE_URL` | ❌ | `https://bidplus.gem.gov.in/all-bids` | Source URL |
| `MAX_PAGES` | ❌ | `50` | Pages per scrape run |
| `REQUEST_DELAY` | ❌ | `1.5` | Seconds between requests |
| `REQUEST_TIMEOUT` | ❌ | `15` | HTTP timeout (seconds) |
| `RUN_DAEMON` | ❌ | `false` | `true` = APScheduler daemon mode |
| `SCHEDULE_CRON` | ❌ | `0 2 * * *` | Cron expression for daemon mode |
| `OPENAI_API_KEY` | ❌ | — | Enables AI enrichment (bonus) |

---

## Deployment

### Option A — Render (recommended free tier)

1. Create a **PostgreSQL** instance on [Render](https://render.com) → copy the `DATABASE_URL`.
2. Create a **Web Service** pointing to this repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`
3. Add all env vars in the Render dashboard.
4. The GitHub Actions workflow handles daily scraping automatically.

### Option B — Self-hosted daemon

```bash
RUN_DAEMON=true python -m src.scheduler
```

The daemon runs the pipeline immediately on start, then on the configured cron schedule.

---

## Project Structure

```
gem-tender-tracker/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── data/
│   ├── raw/              # Raw scraped JSON (gitignored)
│   └── processed/        # Optional cleaned snapshots
├── src/
│   ├── scraper/
│   │   ├── fetcher.py    # HTTP + pagination + retry
│   │   └── parser.py     # BeautifulSoup extraction
│   ├── cleaning/
│   │   └── transform.py  # pandas cleaning pipeline
│   ├── database/
│   │   ├── models.py     # SQLAlchemy ORM schema
│   │   └── loader.py     # Upsert + query helpers
│   ├── api/
│   │   ├── main.py       # FastAPI app factory
│   │   └── routes.py     # Endpoint definitions
│   ├── ai/
│   │   └── enrich.py     # (Bonus) LLM enrichment
│   └── scheduler.py      # Pipeline orchestrator
├── tests/
│   ├── test_scraper.py
│   ├── test_cleaning.py
│   └── test_api.py
├── docs/
│   ├── architecture.md
│   ├── cleaning_decisions.md
│   └── ai_writeup.md
└── .github/
    └── workflows/
        └── pipeline.yml  # Daily cron job
```

---

## Bonus: AI Enrichment

When `OPENAI_API_KEY` is set, `src/ai/enrich.py` adds:
- **`ai_summary`** — plain-English one-sentence description of the tender.
- **`ai_tags`** — procurement category tags (e.g. `IT Equipment, Laptops, Defence`).

See [`docs/ai_writeup.md`](docs/ai_writeup.md) for the full design rationale and trade-offs.

---

## Cleaning Decisions

All data transformation choices are documented in [`docs/cleaning_decisions.md`](docs/cleaning_decisions.md).

---

## Live Demo

> 🔗 **API:** https://web-production-761eb.up.railway.app
> 📖 **Interactive Docs:** https://web-production-761eb.up.railway.app/docs
> 📹 **Demo video:** `<add Loom/YouTube link here>`

---

## Author

Built for the **Coherent Market Data Engineering Intern Assignment**.
