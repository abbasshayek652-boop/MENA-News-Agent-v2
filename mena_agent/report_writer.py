"""Generates the bilingual review-pack report from ranked items.

Calls the configured LLM backend (see llm_client.py). If the LLM is
unavailable or misconfigured, falls back to a placeholder report — but
unlike the previous version of this app, the placeholder is now clearly
labeled as such in its own output, so it can never be mistaken for a real
AI-generated analysis when read in Telegram or the dashboard.
"""

from __future__ import annotations

import logging

from mena_agent.llm_client import LLMError, get_llm_client
from mena_agent.prompting import build_prompts

logger = logging.getLogger(__name__)


def _fallback_report(items: list[dict], reason: str) -> str:
    bullet_lines_en = []
    bullet_lines_ar = []
    attribution_lines = []

    for item in items[:5]:
        title = item.get("title", "Untitled")
        source = item.get("source_name", "Unknown")
        url = item.get("url", "")
        bullet_lines_en.append(f"- {title}")
        bullet_lines_ar.append(f"- {title}")
        attribution_lines.append(f"- {source}: {url}")

    return f"""# ⚠️ PLACEHOLDER REPORT — NOT AI-GENERATED ANALYSIS
_This is a fallback template, not a real analysis. Reason: {reason}_

# Headlines collected this run
{chr(10).join(bullet_lines_en) if bullet_lines_en else "- No items available."}

# Source Attribution
{chr(10).join(attribution_lines) if attribution_lines else "- None"}
"""


def fallback_report(items: list[dict], reason: str) -> str:
    """Public wrapper — see module docstring. Kept as a separate name from
    generate_report() so callers can explicitly request the placeholder
    (e.g. dry-run testing) without going through the LLM at all."""
    return _fallback_report(items, reason)


def generate_report(items: list[dict]) -> tuple[str, bool]:
    """Returns (report_markdown, is_real_analysis).

    is_real_analysis is False whenever the fallback template was used, so
    callers (pipeline.py, the dashboard) can flag this clearly instead of
    presenting placeholder text as if it were genuine analysis.
    """
    if not items:
        return _fallback_report(items, "no items were available to analyze"), False

    try:
        client = get_llm_client()
    except LLMError as exc:
        logger.warning("LLM client unavailable, using fallback report: %s", exc)
        return _fallback_report(items, str(exc)), False

    try:
        system_prompt, user_prompt = build_prompts(items)
        report = client.generate(system_prompt, user_prompt)
        return report, True
    except LLMError as exc:
        logger.warning("LLM generation failed, using fallback report: %s", exc)
        return _fallback_report(items, str(exc)), False
