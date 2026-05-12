"""
enrich.py
─────────
(Bonus) AI enrichment layer — adds LLM-generated summaries and tags to tenders.

Uses the OpenAI Chat Completions API (gpt-4o-mini by default).
Only runs if OPENAI_API_KEY is set in the environment.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def enrich_tender(record: dict) -> dict:
    """
    Add `ai_summary` and `ai_tags` to a single tender record dict.

    If the API key is missing, the record is returned unchanged.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.debug("OPENAI_API_KEY not set — skipping AI enrichment.")
        return record

    try:
        from openai import OpenAI  # lazy import to avoid hard dependency

        client = OpenAI(api_key=api_key)
        prompt = _build_prompt(record)
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()
        # Expect format: SUMMARY: ...\nTAGS: tag1, tag2, tag3
        lines = content.splitlines()
        summary = next((l.replace("SUMMARY:", "").strip() for l in lines if l.startswith("SUMMARY:")), None)
        tags = next((l.replace("TAGS:", "").strip() for l in lines if l.startswith("TAGS:")), None)
        record["ai_summary"] = summary
        record["ai_tags"] = tags
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI enrichment failed for bid %s: %s", record.get("bid_number"), exc)

    return record


def _build_prompt(record: dict) -> str:
    return (
        "You are a procurement analyst. Given the following GeM (Government e-Marketplace) "
        "tender details, provide a one-sentence plain-English summary and 3–5 comma-separated "
        "category tags (e.g. IT Equipment, Defence, Furniture).\n\n"
        f"Title: {record.get('title', 'N/A')}\n"
        f"Department: {record.get('department', 'N/A')}\n"
        f"Estimated Value (INR): {record.get('estimated_value_inr', 'N/A')}\n"
        f"Location: {record.get('location', 'N/A')}\n\n"
        "Respond ONLY in this format:\n"
        "SUMMARY: <one sentence>\n"
        "TAGS: <tag1>, <tag2>, <tag3>"
    )
