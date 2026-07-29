"""Orchestrates a full pipeline run: ingest -> extract -> rank -> analyze ->
deliver -> persist.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import yaml

from mena_agent.dedupe_rank import dedupe_and_rank
from mena_agent.fetch_extract import process_items
from mena_agent.paths import source_config_path
from mena_agent.report_writer import generate_report
from mena_agent.rss_ingest import fetch_rss_feeds
from mena_agent.settings import get_settings
from mena_agent.store import RunRecord, get_store
from mena_agent.telegram_sender import send_telegram_message

logger = logging.getLogger(__name__)

# Minimal seed data so the pipeline still produces *something* meaningful if
# every single configured source fails at once (e.g. total network outage),
# rather than sending an empty/broken report.
_SEED_ITEMS: list[dict[str, Any]] = [
    {
        "title": "No live items were retrieved this run",
        "source_name": "System",
        "tier": "C",
        "url": "",
        "snippet": "All configured sources failed to return usable content this run. "
        "This is seed placeholder content for pipeline continuity only.",
    }
]


def _load_sources() -> list[dict[str, Any]]:
    path = source_config_path()
    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return config.get("sources", [])


def run_pipeline(send_telegram: bool | None = None, dry_run_override: bool | None = None) -> dict[str, Any]:
    """Run the full pipeline once.

    `dry_run_override`, if set, forces use of the fallback report template
    regardless of LLM configuration — useful for testing pipeline plumbing
    without burning API calls. If not set, the LLM is used when configured
    and the fallback only kicks in on failure.
    """
    settings = get_settings()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    timestamp = datetime.now(timezone.utc).isoformat()

    send_telegram = settings.send_telegram_default if send_telegram is None else send_telegram
    dry_run = settings.dry_run_default if dry_run_override is None else dry_run_override

    sources = _load_sources()
    raw_items = fetch_rss_feeds(sources, per_source_limit=settings.per_source_item_limit)
    processed_items, extraction_stats = process_items(raw_items[: settings.max_total_items])

    used_seed_data = False
    if not processed_items:
        logger.warning("No items extracted from live sources; using seed items for continuity.")
        processed_items = _SEED_ITEMS
        used_seed_data = True

    final_items = dedupe_and_rank(processed_items)

    if dry_run:
        report_markdown, is_real_analysis = (
            _fallback_only(final_items) if final_items else ("No items available.", False)
        )
    else:
        report_markdown, is_real_analysis = generate_report(final_items)

    telegram_sent = False
    if send_telegram:
        telegram_sent = send_telegram_message(report_markdown)

    record = RunRecord(
        run_id=run_id,
        timestamp=timestamp,
        sources_configured=len(sources),
        sources_with_items=len({item.get("source_name") for item in raw_items}),
        raw_items=len(raw_items),
        processed_items=len(processed_items),
        final_items=len(final_items),
        is_real_analysis=is_real_analysis,
        used_seed_data=used_seed_data,
        telegram_sent=telegram_sent,
        report_markdown=report_markdown,
    )

    store = get_store()
    try:
        store.save(record)
    except Exception as exc:
        logger.error("Failed to persist run record: %s", exc)

    return {
        "run_id": run_id,
        "timestamp": timestamp,
        "sources_configured": len(sources),
        "sources_with_items": record.sources_with_items,
        "raw_items": len(raw_items),
        "processed_items": len(processed_items),
        "extraction_stats": extraction_stats,
        "final_items": len(final_items),
        "is_real_analysis": is_real_analysis,
        "used_seed_data": used_seed_data,
        "telegram_sent": telegram_sent,
        "dry_run": dry_run,
        "report_markdown": report_markdown,
    }


def _fallback_only(items: list[dict[str, Any]]) -> tuple[str, bool]:
    """Used when dry_run is explicitly requested — always the placeholder,
    even if a real LLM is configured, so testing doesn't burn API calls."""
    from mena_agent.report_writer import fallback_report

    return fallback_report(items, "dry_run was explicitly requested"), False
