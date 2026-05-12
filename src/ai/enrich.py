"""
enrich.py
---------
AI enrichment layer — adds Gemini-generated summaries and tags to tenders.

Uses Google Gemini 1.5 Flash (FREE tier: 1500 requests/day, 15 RPM).
Get a free API key at: https://aistudio.google.com/app/apikey
No credit card required.

Set GEMINI_API_KEY in your environment to enable this module.
Without the key, enrichment is silently skipped.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

# Lazily initialised — only created when the key is present
_model = None


def _get_model():
    """Return a cached Gemini GenerativeModel, or None if key is missing."""
    global _model
    if _model is not None:
        return _model

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        import google.generativeai as genai  # lazy import
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel("gemini-1.5-flash")
        logger.info("Gemini AI enrichment enabled (gemini-1.5-flash).")
    except ImportError:
        logger.warning("google-generativeai not installed. Run: pip install google-generativeai")
    except Exception as exc:
        logger.warning("Failed to initialise Gemini client: %s", exc)

    return _model


def enrich_tender(record: dict) -> dict:
    """
    Add `ai_summary` and `ai_tags` to a single tender record dict.

    If the API key is missing or the call fails, the record is returned unchanged.
    """
    model = _get_model()
    if model is None:
        return record

    prompt = _build_prompt(record)

    try:
        response = model.generate_content(prompt)

        # Safely access response text (may raise if blocked by safety filters)
        try:
            raw = response.text
        except ValueError as safety_exc:
            logger.warning(
                "Gemini safety filter blocked bid %s: %s",
                record.get("bid_number"), safety_exc,
            )
            time.sleep(4)
            return record

        parsed = _extract_json(raw)
        if parsed is None:
            logger.warning(
                "Could not extract JSON from Gemini response for bid %s. Raw: %r",
                record.get("bid_number"), raw[:200],
            )
        else:
            record["ai_summary"] = str(parsed.get("summary", "")).strip() or None
            record["ai_tags"]    = str(parsed.get("tags",    "")).strip() or None
            logger.debug("Enriched bid %s.", record.get("bid_number"))

    except Exception as exc:   # noqa: BLE001
        logger.warning("AI enrichment failed for bid %s: %s", record.get("bid_number"), exc)

    # Stay well within the free-tier 15 RPM limit
    time.sleep(4)
    return record


def _extract_json(text: str) -> dict | None:
    """Robustly pull the first JSON object out of an arbitrary response string."""
    # Strip markdown code fences anywhere in the string
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text).strip()
    # Find the outermost { ... } block
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Last resort: try parsing the whole cleaned string
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def enrich_batch(records: list[dict]) -> list[dict]:
    """
    Enrich a list of tender records with AI summaries and tags.

    Skips entirely if GEMINI_API_KEY is not set.
    Returns the original records (possibly enriched in-place).
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("GEMINI_API_KEY not set — skipping AI enrichment.")
        return records

    total = len(records)
    logger.info("Starting AI enrichment for %d records ...", total)

    enriched = []
    for i, record in enumerate(records, start=1):
        if i % 20 == 0:
            logger.info("AI enrichment progress: %d / %d", i, total)
        enriched.append(enrich_tender(record))

    logger.info("AI enrichment complete: %d / %d records processed.", total, total)
    return enriched


def _build_prompt(record: dict) -> str:
    title = record.get("title") or "N/A"
    department = record.get("department") or "N/A"
    quantity = record.get("quantity") or "N/A"
    value = record.get("estimated_value_inr") or "N/A"

    return f"""You are a Government procurement analyst.
Analyse this GeM (Government e-Marketplace) tender and respond ONLY with valid JSON.

Tender:
- Category / Item: {title}
- Buying Department: {department}
- Quantity: {quantity}
- Estimated Value (INR): {value}

Respond with exactly this JSON (no markdown, no explanation):
{{
  "summary": "<1-2 sentence plain-English explanation of what is being procured and who is buying it>",
  "tags": "<3 to 5 comma-separated category tags, e.g. IT Equipment, Office Furniture, Medical Supplies>"
}}"""
