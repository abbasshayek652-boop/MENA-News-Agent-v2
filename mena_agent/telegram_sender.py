"""Send the generated review pack to Telegram with proper formatting.

The report content is Markdown (headers, **bold**, "- " bullets). Telegram's
Bot API does not render Markdown unless you tell it to and escape correctly,
so the previous version of this module was sending literal "#" and "**"
characters as plain text, and silently truncating anything past 4000 chars.

This version:
  1. Converts the Markdown into Telegram-safe HTML (bold headers, real bullet
     points) instead of dumping raw Markdown as plain text.
  2. Splits long reports into multiple messages at paragraph boundaries,
     respecting Telegram's ~4096 character-per-message limit, instead of
     truncating and losing content.
  3. Sends each part with retries and honors Telegram's rate-limit
     (HTTP 429) responses instead of failing silently on the first hiccup.
"""

from __future__ import annotations

import logging
import os
import re
import textwrap
import time
from html import escape as _html_escape

import requests

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096
# Leave headroom below the hard limit for the "(Part i/n)" footer we add.
SAFE_CHUNK_LIMIT = 3800
# Telegram rejects text with no content and enforces per-chat rate limits;
# a small delay between multi-part sends keeps us well clear of those limits.
DELAY_BETWEEN_PARTS_SECONDS = 0.6
MAX_SEND_RETRIES = 3

_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


def _format_line(raw_line: str) -> str:
    """Convert a single line of Markdown into a Telegram-HTML-safe line.

    Headers (#, ##, ###) become bold lines. "**bold**" becomes <b>bold</b>.
    "- " bullets become a real bullet character. Everything else is
    HTML-escaped so stray & < > in article titles/URLs can't break parsing.
    """
    line = raw_line.rstrip()

    heading_match = re.match(r"^(#{1,3})\s+(.*)$", line)
    if heading_match:
        level = len(heading_match.group(1))
        content = _html_escape(heading_match.group(2))
        if level == 1:
            return f"<b>📌 {content}</b>"
        if level == 2:
            return f"<b>▪️ {content}</b>"
        return f"<b>{content}</b>"

    bullet_match = re.match(r"^[-*]\s+(.*)$", line)
    if bullet_match:
        content = bullet_match.group(1)
        content = _BOLD_PATTERN.sub(lambda m: f"\x00B{m.group(1)}\x00b", content)
        content = _html_escape(content)
        content = content.replace("\x00B", "<b>").replace("\x00b", "</b>")
        return f"• {content}"

    # Inline **bold** on an ordinary paragraph line. Escape everything else
    # first, using placeholder markers so escape() doesn't mangle our tags.
    content = _BOLD_PATTERN.sub(lambda m: f"\x00B{m.group(1)}\x00b", line)
    content = _html_escape(content)
    content = content.replace("\x00B", "<b>").replace("\x00b", "</b>")
    return content


def _wrap_long_line(line: str, max_len: int = 500) -> list[str]:
    """Word-wrap a single very long line (e.g. a long attribution/URL list
    entry) so no individual line blows past the chunk size on its own."""
    if len(line) <= max_len:
        return [line]
    return textwrap.wrap(line, width=max_len, break_long_words=False, break_on_hyphens=False) or [line]


def markdown_report_to_html_chunks(report_text: str) -> list[str]:
    """Convert the full Markdown report into a list of HTML message chunks,
    each within Telegram's message size limit, split on blank-line
    (paragraph) boundaries wherever possible."""
    formatted_lines: list[str] = []
    for raw_line in report_text.splitlines():
        if not raw_line.strip():
            formatted_lines.append("")
            continue
        for sub_line in _wrap_long_line(raw_line):
            formatted_lines.append(_format_line(sub_line))

    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for line in formatted_lines:
        line_len = len(line) + 1  # +1 for the newline that will join it
        # Prefer to break on a blank line once we're already close to the
        # limit, so paragraphs/sections aren't split mid-thought.
        if current_lines and (
            current_len + line_len > SAFE_CHUNK_LIMIT
            or (line == "" and current_len > SAFE_CHUNK_LIMIT * 0.6)
        ):
            chunks.append("\n".join(current_lines).strip())
            current_lines = []
            current_len = 0
            if line == "":
                continue

        current_lines.append(line)
        current_len += line_len

    if current_lines:
        chunks.append("\n".join(current_lines).strip())

    return [c for c in chunks if c]


def _send_single_message(url: str, chat_id: str, html_text: str) -> bool:
    payload = {
        "chat_id": chat_id,
        "text": html_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    for attempt in range(1, MAX_SEND_RETRIES + 1):
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                return True

            if response.status_code == 429:
                retry_after = 1
                try:
                    retry_after = response.json().get("parameters", {}).get("retry_after", 1)
                except Exception:
                    pass
                logger.warning("Telegram rate limit hit; retrying after %ss", retry_after)
                time.sleep(retry_after + 0.5)
                continue

            logger.error(
                "Telegram send failed (HTTP %s): %s", response.status_code, response.text[:500]
            )
            return False
        except requests.RequestException as exc:
            logger.warning("Telegram send attempt %s/%s failed: %s", attempt, MAX_SEND_RETRIES, exc)
            time.sleep(1.5 * attempt)

    return False


def send_telegram_message(text: str) -> bool:
    """Send the report to Telegram, formatted and split across as many
    messages as needed. Returns True only if every part sent successfully."""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.warning("Missing TELEGRAM_BOT_TOKEN/TELEGRAM_TOKEN or TELEGRAM_CHAT_ID; skipping Telegram send.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = markdown_report_to_html_chunks(text)

    if not chunks:
        logger.warning("Report was empty after formatting; nothing sent to Telegram.")
        return False

    total = len(chunks)
    all_sent = True
    for index, chunk in enumerate(chunks, start=1):
        message = chunk if total == 1 else f"{chunk}\n\n<i>(Part {index}/{total})</i>"
        sent = _send_single_message(url, chat_id, message)
        all_sent = all_sent and sent
        if sent:
            logger.info("Telegram message part %s/%s sent successfully.", index, total)
        else:
            logger.error("Telegram message part %s/%s failed to send.", index, total)
        if index < total:
            time.sleep(DELAY_BETWEEN_PARTS_SECONDS)

    return all_sent
