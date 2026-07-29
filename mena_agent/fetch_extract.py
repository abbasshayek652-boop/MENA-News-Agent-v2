import logging
import os

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Below this many characters of extracted text, the page was almost
# certainly a bot-block/consent wall/empty shell rather than real article
# content, and should be treated as a failed extraction rather than kept
# with a near-empty snippet.
MIN_USABLE_TEXT_LENGTH = 200


def _fetch_html(url: str, timeout: int = 20) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        },
    )
    response.raise_for_status()
    return response.text


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "svg", "nav", "form"]):
        tag.decompose()

    # Prefer <article> content when the page provides it — it's far less
    # likely to be padded with nav/ad/cookie-banner boilerplate than the
    # whole page body.
    article_tag = soup.find("article")
    container = article_tag if article_tag is not None else soup
    text = container.get_text(separator=" ")
    return " ".join(text.split())


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else (text[:limit] + " …")


def process_items(items: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Extract full text for each item. Returns (processed_items, stats).

    `stats` reports how many items failed the HTTP fetch vs. were rejected
    for having too little usable text (bot-block pages, paywalls, consent
    walls), broken down so failures aren't just silently invisible in logs.
    """
    timeout = int(os.getenv("FETCH_TIMEOUT", "20"))
    text_limit = int(os.getenv("TEXT_LIMIT", "18000"))
    snippet_limit = int(os.getenv("ARTICLE_SNIPPET_LIMIT", "4500"))

    processed: list[dict] = []
    fetch_failed = 0
    too_short_rejected = 0

    for item in items:
        url = item.get("url", "")
        try:
            html = _fetch_html(url, timeout=timeout)
        except Exception as exc:
            fetch_failed += 1
            logger.warning("Failed to fetch article %s: %s", url, exc)
            continue

        text = _extract_text(html)
        if len(text) < MIN_USABLE_TEXT_LENGTH:
            too_short_rejected += 1
            logger.warning(
                "Rejected article %s: only %d chars extracted (likely bot-block/paywall/empty page)",
                url,
                len(text),
            )
            continue

        out = dict(item)
        out["snippet"] = _truncate(_truncate(text, text_limit), snippet_limit)
        processed.append(out)

    stats = {
        "attempted": len(items),
        "succeeded": len(processed),
        "fetch_failed": fetch_failed,
        "too_short_rejected": too_short_rejected,
    }
    if fetch_failed or too_short_rejected:
        logger.warning(
            "Extraction summary: %d/%d succeeded (%d fetch failures, %d rejected as too short)",
            len(processed),
            len(items),
            fetch_failed,
            too_short_rejected,
        )

    return processed, stats
