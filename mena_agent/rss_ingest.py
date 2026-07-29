import logging
import os
from itertools import zip_longest

import feedparser
import requests

logger = logging.getLogger(__name__)


def _parse_feed(rss_url: str) -> feedparser.FeedParserDict:
    try:
        response = requests.get(
            rss_url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (MENA-Agent/1.0)"},
        )
        response.raise_for_status()
        return feedparser.parse(response.content)
    except Exception as exc:
        logger.warning("Failed to fetch RSS URL %s: %s", rss_url, exc)
        return feedparser.parse("")


def fetch_rss_feeds(sources: list[dict], per_source_limit: int | None = None) -> list[dict]:
    """Fetch entries from every configured source and return them interleaved
    round-robin (source 1's 1st item, source 2's 1st item, ..., then source
    1's 2nd item, ...) rather than concatenated in source order.

    This matters because any later step that caps the total item count (e.g.
    `raw_items[:30]` in the pipeline) would otherwise silently favor whichever
    sources happen to appear first in sources.yaml, starving out every other
    configured source even though they were fetched. Interleaving means a
    downstream cap trims evenly across all sources instead of skipping most
    of them entirely.
    """
    per_source_limit = per_source_limit or int(os.getenv("PER_SOURCE_ITEM_LIMIT", "8"))

    per_source_items: list[list[dict]] = []
    sources_with_zero_entries: list[str] = []

    for source in sources:
        rss = (source.get("rss") or source.get("url") or "").strip()
        name = source.get("name", "Unknown")
        if not rss:
            continue

        feed = _parse_feed(rss)
        collected: list[dict] = []
        for entry in getattr(feed, "entries", []) or []:
            if len(collected) >= per_source_limit:
                break
            url = (getattr(entry, "link", "") or "").strip()
            title = (getattr(entry, "title", "") or "").strip()
            published = getattr(entry, "published", "") or getattr(entry, "updated", "") or ""
            if not url or not title:
                continue

            collected.append(
                {
                    "title": title,
                    "url": url,
                    "published": published,
                    "source_name": name,
                    "tier": source.get("tier", "C"),
                    "lang": source.get("lang", "any"),
                }
            )

        if not collected:
            sources_with_zero_entries.append(name)
        per_source_items.append(collected)

    if sources_with_zero_entries:
        logger.warning(
            "%d/%d sources returned no usable entries (dead feed, changed URL, or blocked request): %s",
            len(sources_with_zero_entries),
            len(sources),
            ", ".join(sources_with_zero_entries),
        )

    interleaved = [
        item for group in zip_longest(*per_source_items) for item in group if item is not None
    ]
    return interleaved
