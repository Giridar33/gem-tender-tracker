# GeM Tender Tracker

> **Production-ready B2B data pipeline** that scrapes, cleans, AI-enriches, and serves
> [Government e-Marketplace (GeM)](https://bidplus.gem.gov.in/all-bids)
> tender listings via a filtered REST API — updated daily, zero manual intervention.

---

## Live Demo

| | Link |
|--|------|
| **Dashboard (Streamlit)** | https://gem-tender-trackergit-sgfaj5nph4c2ywvfa6hijb.streamlit.app/ |
| **API Base** | https://web-production-761eb.up.railway.app |
| **Interactive Docs (Swagger)** | https://web-production-761eb.up.railway.app/docs |
| **Health Check** | https://web-production-761eb.up.railway.app/health |
| **AI Status** | https://web-production-761eb.up.railway.app/ai/status |

---

## Problem Statement

Indian procurement teams and vendors waste hours manually browsing the GeM portal
to find relevant tenders. This project automates the entire process:

1. A **daily pipeline** pulls all active bids from GeM.
2. Raw data is **cleaned and normalised** (dates, currency, dedup).
3. **Gemini AI** enriches each tender with a plain-English summary and category tags.
4. A **fast REST API** lets any business user filter and discover tenders in seconds.

---

## Architecture

```
GeM Portal (bidplus.gem.gov.in)
        │
        ▼
┌──────────────────────────────┐
│  Scraper  (fetcher.py)       │  Paginated HTTP · retries · exponential back-off
└────────────┬─────────────────┘
             │ raw JSON records
             ▼
    data/raw/<timestamp>.json
             │
             ▼
┌──────────────────────────────┐
│  Cleaner  (transform.py)     │  dedup · normalise text · parse dates / currency / quantity
└────────────┬─────────────────┘
             │ clean DataFrame
             ▼
┌──────────────────────────────┐
│  AI Enrichment  (enrich.py)  │  Gemini 1.5 Flash → ai_summary + ai_tags  (FREE tier)
└────────────┬─────────────────┘
             │ enriched records
             ▼
┌──────────────────────────────┐
│  Database  (PostgreSQL)      │  upsert on bid_number · 4 indexes
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│  FastAPI  (routes + ai_routes│  9 REST endpoints · Swagger UI · CORS
└──────────────────────────────┘

──── Automation ────────────────────────────────────────────────────────────
GitHub Actions cron  →  python -m src.scheduler   (daily @ 02:00 UTC)
APScheduler daemon   →  RUN_DAEMON=true            (self-hosted option)
```

---

## Feature Summary

| Layer | What it does |
|-------|-------------|
| **Scraper** | Paginates all GeM bids, retries failures with exponential back-off via `tenacity` |
| **Parser** | Extracts 9 fields per record with safe defaults for missing/malformed values |
| **Cleaner** | Deduplicates, strips whitespace, normalises text, parses dates / Indian currency (L, Cr) / quantities |
| **AI Enrichment** | Gemini 1.5 Flash generates `ai_summary` and `ai_tags` for each tender (free tier, no credit card) |
| **Database** | PostgreSQL (Supabase) with upsert-safe schema and 4 query-optimised indexes |
| **API** | 9 endpoints — filter by department, location, keyword, value range, active status; on-demand AI enrichment |
| **Automation** | GitHub Actions daily cron **or** APScheduler daemon mode |
| **Tests** | 37 unit + integration tests; in-memory SQLite; zero external services needed |

---

## Quick Start (Local)

### 1. Clone and set up the virtual environment

```bash
git clone https://github.com/Giridar33/gem-tender-tracker.git
cd gem-tender-tracker

python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Open .env and fill in the values (see Environment Variables section below)
```

For a **local SQLite** setup (no database server needed):
```
DATABASE_URL=sqlite:///./gem_tenders.db
```

### 3. Run the pipeline once

```bash
python -m src.scheduler
```

This scrapes GeM → cleans → AI-enriches (if `GEMINI_API_KEY` is set) → loads into DB.

### 4. Start the API server

```bash
uvicorn src.api.main:app --reload
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive Swagger UI.

---

## API Reference

### Core Endpoints

#### `GET /health`
Service liveness check.
```json
{ "status": "ok" }
```

#### `GET /tenders`
Filtered, paginated list of GeM tenders.

| Query param | Type | Default | Description |
|-------------|------|---------|-------------|
| `department` | string | — | Partial match on buying department |
| `location` | string | — | Partial match on consignee location |
| `keyword` | string | — | Full-text search on tender title |
| `min_value` | float | — | Minimum estimated value (INR) |
| `max_value` | float | — | Maximum estimated value (INR) |
| `active_only` | bool | `false` | Only return tenders whose closing date is in the future |
| `limit` | int | `20` | Max results (1–200) |
| `offset` | int | `0` | Pagination offset |

**Examples:**
```
GET /tenders?department=defence&active_only=true&limit=50
GET /tenders?keyword=laptop&min_value=100000
GET /tenders?location=mumbai&max_value=500000
```

**Response:**
```json
{
  "count": 42,
  "results": [
    {
      "id": 1,
      "bid_number": "GEM/2024/B/4567890",
      "title": "Procurement of Laptops",
      "department": "Ministry of Defence",
      "location": "New Delhi",
      "quantity": 50.0,
      "estimated_value_inr": 2500000.0,
      "start_date": "2024-06-01T00:00:00Z",
      "end_date": "2024-06-30T00:00:00Z",
      "ai_summary": "The Ministry of Defence is procuring 50 laptops for office use.",
      "ai_tags": "IT Equipment, Laptops, Defence, Procurement",
      "source_url": "https://bidplus.gem.gov.in/...",
      "scraped_at": "2024-06-05T02:10:00Z"
    }
  ]
}
```

#### `GET /tenders/{id}`
Fetch a single tender by its internal database ID.
- Returns `404` if not found.

#### `GET /stats/summary`
Aggregated pipeline statistics.
```json
{
  "total_tenders": 12450,
  "active_tenders": 3210,
  "average_estimated_value_inr": 847500.0
}
```

---

### AI Enrichment Endpoints

#### `GET /ai/status`
Check whether Gemini AI enrichment is enabled.

**When key is set:**
```json
{
  "enabled": true,
  "model": "gemini-1.5-flash",
  "free_tier_rpm": 15,
  "free_tier_daily": 1500
}
```

**When key is missing:**
```json
{
  "enabled": false,
  "reason": "GEMINI_API_KEY is not set or google-generativeai is not installed.",
  "model": null
}
```

#### `POST /tenders/{id}/enrich`
On-demand enrich a single tender with Gemini.
- Returns `503` if `GEMINI_API_KEY` is not configured.
- Returns `404` if the tender ID does not exist.
- Writes `ai_summary` and `ai_tags` back to the database.

```json
{
  "tender_id": 42,
  "bid_number": "GEM/2024/B/4567890",
  "ai_summary": "The Ministry of Defence is procuring 50 laptops for administrative use at New Delhi.",
  "ai_tags": "IT Equipment, Laptops, Defence, Procurement, Hardware"
}
```

#### `POST /ai/enrich-batch`
Trigger a background job to enrich **all** tenders that have no `ai_summary` yet.
- Only one batch job runs at a time (returns `409` if already running).
- Returns `503` if `GEMINI_API_KEY` is not configured.
- Returns immediately; enrichment continues in the background.

```json
{
  "status": "started",
  "message": "Batch enrichment is running in the background. Check /tenders to see ai_summary fields populate."
}
```

---

## AI Enrichment — How It Works

When `GEMINI_API_KEY` is set, `src/ai/enrich.py` adds two fields to every tender:

| Field | Description |
|-------|-------------|
| `ai_summary` | 1–2 sentence plain-English explanation of what is being procured and who is buying it |
| `ai_tags` | 3–5 comma-separated procurement category tags (e.g. `IT Equipment, Laptops, Defence`) |


**Graceful degradation:** If the key is not set, enrichment is silently skipped — the pipeline and all core API endpoints continue working normally.

Get a free key at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).

---

## Running Tests

```bash
pytest tests/ -v
```

**37 tests** across 3 test files — all run against an **in-memory SQLite database** with no external services required.

```
tests/test_api.py        11 tests  — all 9 endpoints incl. AI enrichment
tests/test_cleaning.py   22 tests  — date/currency/quantity parsers, dedup, whitespace
tests/test_scraper.py     4 tests  — HTML parser, malformed input, required keys
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` |`sqlite:///./gem_tenders.db` | PostgreSQL or SQLite connection string |
| `GEMINI_API_KEY` | — | Enables Gemini AI enrichment (free tier) |
| `SCRAPE_BASE_URL` | `https://bidplus.gem.gov.in/all-bids` | GeM scrape source |
| `MAX_PAGES` | `50` | Pages per scrape run |
| `REQUEST_DELAY` | `1.5` | Seconds between page requests (politeness) |
| `REQUEST_TIMEOUT` | `15` | HTTP timeout in seconds |
| `RUN_DAEMON` | `false` | `true` = APScheduler daemon mode |
| `SCHEDULE_CRON` | `0 2 * * *` | Cron expression for daemon mode |

---

## Deployment

### Railway (current production)

The app is deployed on [Railway](https://railway.app):

- **Start command:** `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`
- **Database:** Supabase PostgreSQL (via `psycopg` driver)
- **Required environment variables:** `DATABASE_URL`, `GEMINI_API_KEY`

The **GitHub Actions** workflow (`.github/workflows/pipeline.yml`) runs the scrape → clean → AI enrich → upsert pipeline daily at 02:00 UTC, pushing fresh data to the production database automatically.

### Self-hosted Daemon

```bash
RUN_DAEMON=true python -m src.scheduler
```

Runs the pipeline immediately on start, then on the configured cron schedule.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.13 |
| Web Framework | FastAPI 0.111 + Uvicorn |
| Database ORM | SQLAlchemy 2.0 |
| Database | PostgreSQL (Supabase) / SQLite (local/test) |
| DB Driver | psycopg3 (binary wheels) |
| Scraping | requests + BeautifulSoup4 + lxml |
| Retries | tenacity (exponential back-off) |
| Data Processing | pandas + numpy + python-dateutil |
| AI Enrichment | Google Gemini 1.5 Flash (`google-generativeai`) |
| Scheduling | APScheduler 3 + GitHub Actions |
| Testing | pytest + httpx + responses |
| Logging | structlog |
| Deployment | Railway + Supabase |

---

## Project Structure

```
gem-tender-tracker/
├── README.md
├── requirements.txt
├── .env.example               # Copy to .env and fill in values
├── .gitignore
├── Procfile                   # Railway start command
├── conftest.py
├── data/
│   ├── raw/                   # Raw scraped JSON (gitignored)
│   └── processed/             # Optional cleaned snapshots
├── src/
│   ├── scraper/
│   │   ├── fetcher.py         # HTTP client · pagination · retry logic
│   │   └── parser.py          # BeautifulSoup field extraction
│   ├── cleaning/
│   │   └── transform.py       # pandas cleaning pipeline
│   ├── database/
│   │   ├── models.py          # SQLAlchemy ORM schema (Tender table)
│   │   └── loader.py          # Upsert + query helpers
│   ├── ai/
│   │   └── enrich.py          # Gemini 1.5 Flash enrichment (ai_summary, ai_tags)
│   ├── api/
│   │   ├── main.py            # FastAPI app factory · CORS · lifespan
│   │   ├── routes.py          # Core endpoints (health, tenders, stats)
│   │   └── ai_routes.py       # AI endpoints (status, enrich, batch)
│   └── scheduler.py           # Pipeline orchestrator (scrape→clean→enrich→load)
├── tests/
│   ├── test_scraper.py
│   ├── test_cleaning.py
│   └── test_api.py
├── docs/
│   ├── architecture.md
│   ├── cleaning_decisions.md
│   └── ai_writeup.md          # Gemini integration rationale & trade-offs
└── .github/
    └── workflows/
        └── pipeline.yml       # Daily cron: scrape → enrich → upsert
```

---

## Cleaning Decisions

All data transformation choices (date formats, Indian currency notation, deduplication strategy, null handling) are documented in [`docs/cleaning_decisions.md`](docs/cleaning_decisions.md).

---

## AI Design Rationale

Full design rationale, model selection trade-offs, graceful degradation behaviour, and future improvement ideas are documented in [`docs/ai_writeup.md`](docs/ai_writeup.md).

---

## Author

Built by **Giridar** for the **Coherent Market Data Engineering Intern Assignment**.
