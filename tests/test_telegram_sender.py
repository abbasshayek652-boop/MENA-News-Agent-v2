import os
from unittest.mock import MagicMock, patch

from mena_agent import telegram_sender


def test_format_line_escapes_html_and_converts_markdown():
    assert telegram_sender._format_line("# Title with & and <tag>") == "<b>📌 Title with &amp; and &lt;tag&gt;</b>"
    assert telegram_sender._format_line("- item with **bold**") == "• item with <b>bold</b>"
    assert telegram_sender._format_line("Plain <b>fake</b> html") == "Plain &lt;b&gt;fake&lt;/b&gt; html"


def test_send_telegram_message_splits_long_reports(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    long_report = "# Section\n" + ("- bullet point with some text\n" * 400)

    sent_payloads = []

    def fake_post(url, json=None, timeout=None):
        sent_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 200
        return resp

    with patch("requests.post", side_effect=fake_post):
        result = telegram_sender.send_telegram_message(long_report)

    assert result is True
    assert len(sent_payloads) > 1
    for p in sent_payloads:
        assert p["parse_mode"] == "HTML"
        assert len(p["text"]) <= telegram_sender.TELEGRAM_MESSAGE_LIMIT


def test_send_telegram_message_returns_false_without_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    assert telegram_sender.send_telegram_message("hello") is False
