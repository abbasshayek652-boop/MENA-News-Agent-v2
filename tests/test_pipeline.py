from unittest.mock import MagicMock, patch


def test_full_pipeline_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SOURCE_CONFIG", str(tmp_path / "sources.yaml"))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    (tmp_path / "sources.yaml").write_text(
        "sources:\n  - name: Test Source\n    url: https://test.example.com/rss\n    tier: A\n",
        encoding="utf-8",
    )

    from mena_agent.settings import get_settings

    get_settings.cache_clear()

    fake_feed = MagicMock()
    fake_entry = MagicMock()
    fake_entry.link = "https://test.example.com/article1"
    fake_entry.title = "Test Headline"
    fake_entry.published = "2026-01-01"
    fake_feed.entries = [fake_entry]

    fake_html_response = MagicMock()
    fake_html_response.raise_for_status = lambda: None
    fake_html_response.text = "<html><body><article>" + ("Content. " * 50) + "</article></body></html>"

    with patch("mena_agent.rss_ingest._parse_feed", return_value=fake_feed), patch(
        "requests.get", return_value=fake_html_response
    ):
        from mena_agent.pipeline import run_pipeline

        result = run_pipeline(send_telegram=False, dry_run_override=True)

    assert result["sources_configured"] == 1
    assert result["final_items"] == 1
    assert result["is_real_analysis"] is False
    assert result["telegram_sent"] is False
    assert "PLACEHOLDER REPORT" in result["report_markdown"]

    from mena_agent.store import get_store

    store = get_store()
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0]["run_id"] == result["run_id"]
