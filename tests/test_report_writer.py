from unittest.mock import patch

from mena_agent import report_writer
from mena_agent.llm_client import LLMError


def test_fallback_used_when_llm_unconfigured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    # Clear cached settings so the env changes above take effect.
    from mena_agent.settings import get_settings

    get_settings.cache_clear()

    items = [{"title": "Some headline", "source_name": "Test", "tier": "A", "url": "https://x.com", "snippet": ""}]
    report, is_real = report_writer.generate_report(items)

    assert is_real is False
    assert "PLACEHOLDER REPORT" in report
    assert "Some headline" in report


def test_fallback_used_when_llm_call_fails(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    from mena_agent.settings import get_settings

    get_settings.cache_clear()

    items = [{"title": "Headline", "source_name": "Test", "tier": "A", "url": "https://x.com", "snippet": ""}]

    with patch("mena_agent.report_writer.get_llm_client") as mock_get_client:
        mock_client = mock_get_client.return_value
        mock_client.generate.side_effect = LLMError("simulated failure")
        report, is_real = report_writer.generate_report(items)

    assert is_real is False
    assert "PLACEHOLDER REPORT" in report


def test_real_analysis_used_when_llm_succeeds(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    from mena_agent.settings import get_settings

    get_settings.cache_clear()

    items = [{"title": "Headline", "source_name": "Test", "tier": "A", "url": "https://x.com", "snippet": ""}]

    with patch("mena_agent.report_writer.get_llm_client") as mock_get_client:
        mock_client = mock_get_client.return_value
        mock_client.generate.return_value = "# Real Report\nSome real analysis."
        report, is_real = report_writer.generate_report(items)

    assert is_real is True
    assert report == "# Real Report\nSome real analysis."


def test_empty_items_returns_fallback():
    report, is_real = report_writer.generate_report([])
    assert is_real is False
    assert "PLACEHOLDER" in report
