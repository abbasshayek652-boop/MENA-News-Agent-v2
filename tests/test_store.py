from mena_agent.store import LocalStore, RunRecord


def _make_record(run_id="20260101T000000Z-abcdef"):
    return RunRecord(
        run_id=run_id,
        timestamp="2026-01-01T00:00:00+00:00",
        sources_configured=45,
        sources_with_items=10,
        raw_items=80,
        processed_items=60,
        final_items=25,
        is_real_analysis=True,
        used_seed_data=False,
        telegram_sent=True,
        report_markdown="# Report\nSome content.",
    )


def test_save_and_get_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from mena_agent.settings import get_settings

    get_settings.cache_clear()

    store = LocalStore()
    record = _make_record()
    store.save(record)

    fetched = store.get_run(record.run_id)
    assert fetched is not None
    assert fetched["report_markdown"] == "# Report\nSome content."
    assert fetched["final_items"] == 25


def test_list_runs_sorted_descending(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from mena_agent.settings import get_settings

    get_settings.cache_clear()

    store = LocalStore()
    store.save(_make_record("20260101T000000Z-aaa"))
    store.save(_make_record("20260102T000000Z-bbb"))

    runs = store.list_runs()
    assert [r["run_id"] for r in runs] == ["20260102T000000Z-bbb", "20260101T000000Z-aaa"]


def test_get_missing_run_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from mena_agent.settings import get_settings

    get_settings.cache_clear()

    store = LocalStore()
    assert store.get_run("does-not-exist") is None
