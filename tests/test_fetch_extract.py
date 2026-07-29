from unittest.mock import MagicMock, patch

from mena_agent import fetch_extract


def _fake_get(url, timeout=None, headers=None):
    resp = MagicMock()
    if "blocked" in url:
        def raise_for_status():
            raise Exception("403 Forbidden")
        resp.raise_for_status = raise_for_status
    elif "thin" in url:
        resp.raise_for_status = lambda: None
        resp.text = "<html><body><div>Enable JavaScript</div></body></html>"
    else:
        resp.raise_for_status = lambda: None
        resp.text = "<html><body><article>" + ("Real content. " * 50) + "</article></body></html>"
    return resp


def test_process_items_reports_stats_and_filters_junk():
    items = [
        {"title": "Good", "url": "https://good.example.com/1"},
        {"title": "Blocked", "url": "https://blocked.example.com/1"},
        {"title": "Thin", "url": "https://thin.example.com/1"},
    ]

    with patch("requests.get", side_effect=_fake_get):
        processed, stats = fetch_extract.process_items(items)

    assert [p["title"] for p in processed] == ["Good"]
    assert stats == {
        "attempted": 3,
        "succeeded": 1,
        "fetch_failed": 1,
        "too_short_rejected": 1,
    }


def test_process_items_empty_input():
    processed, stats = fetch_extract.process_items([])
    assert processed == []
    assert stats["attempted"] == 0
