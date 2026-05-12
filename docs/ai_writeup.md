# AI/ML Enhancement — Write-up

## What Was Added

The module `src/ai/enrich.py` uses the **Google Gemini 1.5 Flash** model
(FREE tier — no credit card required) to add two fields to each tender record:

| Field | Description |
|-------|-------------|
| `ai_summary` | 1–2 sentence plain-English explanation of what is being procured and who is buying it |
| `ai_tags` | 3–5 comma-separated procurement category tags |

Three new API endpoints are exposed:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ai/status` | GET | Check whether Gemini is configured and active |
| `/tenders/{id}/enrich` | POST | On-demand enrich a single tender |
| `/ai/enrich-batch` | POST | Background-enrich all un-enriched tenders |

---

## Why This Approach

**Problem:** GeM tender titles are often cryptic abbreviations or internal codes
(e.g., `"PROC OF LPT (I5 GEN12 8GB 512SSD)"`). A procurement manager scanning
hundreds of tenders needs instant comprehension, plus category-level filtering.

**Solution:** Gemini 1.5 Flash reliably paraphrases technical shorthand into plain
English and categorises tenders, enabling full-text search and faceted filtering
by tag — with zero running cost on the free tier.

**Why Gemini 1.5 Flash specifically:**

| Factor | Detail |
|--------|--------|
| Cost | **FREE** — 1,500 requests/day, 15 RPM, no credit card |
| Quality | On par with GPT-3.5 for structured JSON classification tasks |
| Latency | ~1–2 s per record — acceptable for nightly batch enrichment |
| Integration | Official `google-generativeai` Python SDK, one `pip install` |

---

## Trade-offs Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **Gemini 1.5 Flash (free)** | Zero cost, high quality, no infra | External API dependency | ✅ Chosen |
| OpenAI GPT-4o-mini | Very high quality | Costs ~$0.15 / 1M tokens | ❌ Unnecessary cost |
| Local HuggingFace model | No API cost | GPU needed, lower quality | ❌ Overkill for MVP |
| Rule-based tagging | Zero cost | Brittle, misses edge cases | ❌ Not robust enough |
| No enrichment | Simplest | Zero added value | ❌ Misses bonus marks |

---

## Pipeline Integration

```
Scrape → Clean → AI Enrich (Gemini) → Upsert to DB
```

In `src/scheduler.py`, step 3 calls `enrich_batch()` between the clean and upsert
steps. If `GEMINI_API_KEY` is not set, `enrich_batch()` returns records unchanged
and logs `"GEMINI_API_KEY not set — skipping AI enrichment."` — the pipeline
continues without any failure.

A 4-second sleep between calls keeps throughput well within the free-tier
15 RPM limit.

---

## Graceful Degradation

If `GEMINI_API_KEY` is not set (or `google-generativeai` is not installed):

- `enrich_tender()` returns the record **unchanged** — no exception raised.
- `enrich_batch()` returns the full record list immediately with an INFO log.
- All three `/ai/*` endpoints return `503 Service Unavailable` with a clear message.
- The main `/tenders` and `/stats` endpoints are **completely unaffected**.

---

## Future Improvements

- **Cache by title hash** — skip re-enriching records whose title hasn't changed.
- **Urgency classification** — "High / Medium / Low" based on days until closing.
- **Semantic search** — store Gemini embeddings in pgvector for "find similar tenders".
- **Batch API calls** — Gemini supports batched prompts to reduce per-record latency.
- **Streaming enrichment** — stream summaries to the API response for large batches.
