# AI/ML Enhancement — Write-up

## What Was Added

The module `src/ai/enrich.py` uses the **OpenAI Chat Completions API**
(model: `gpt-4o-mini` by default) to add two fields to each tender record:

| Field | Description |
|-------|-------------|
| `ai_summary` | One plain-English sentence describing the tender |
| `ai_tags` | 3–5 comma-separated procurement category tags |

## Why This Approach

**Problem:** GeM tender titles are often cryptic abbreviations or internal codes
(e.g., "PROC OF LPT (I5 GEN12 8GB 512SSD)"). A procurement manager scanning
hundreds of tenders needs instant comprehension.

**Solution:** An LLM can reliably paraphrase technical shorthand into plain English
and categorise tenders, enabling full-text search and faceted filtering by tag.

**Why GPT-4o-mini specifically:**
- Low cost (~$0.15 / 1M input tokens) — affordable for 1,000–5,000 daily records.
- Fast enough for batch enrichment without blocking the main pipeline.
- No fine-tuning required for this classification task.

## Trade-offs Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| OpenAI API | High quality, no infra | Cost, external dependency | ✅ Chosen |
| Local HuggingFace model | No API cost | GPU needed, lower quality | ❌ Overkill for MVP |
| Rule-based tagging | Zero cost | Brittle, misses edge cases | ❌ Not robust enough |
| No enrichment | Simplest | Zero added value | ❌ Misses bonus marks |

## Graceful Degradation

If `OPENAI_API_KEY` is not set, `enrich_tender()` returns the record unchanged.
This means the pipeline works identically without an API key — the AI layer
is purely additive and never blocks data ingestion.

## Future Improvements

- **Batch the API calls** (up to 20 records per request) to reduce latency and cost.
- **Cache by title hash** so re-runs on unchanged records skip the API entirely.
- **Add urgency classification** ("High / Medium / Low") based on days until closing.
- **Semantic search** using embeddings stored in pgvector for "find similar tenders".
