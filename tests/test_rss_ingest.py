from unittest.mock import MagicMock, patch

from mena_agent import rss_ingest


class _FakeEntry:
    def __init__(self, i):
        self.link = f"https://example.com/{i}"
        self.title = f"Title {i}"
        self.published = "2026-01-01"


def _fake_parse_feed(url):
    feed = MagicMock()
    if "big" in url:
        feed.entries = [_FakeEntry(i) for i in range(50)]
    elif "small" in url:
        feed.entries = [_FakeEntry(i) for i in range(2)]
    else:
        feed.entries = [_FakeEntry(i) for i in range(10)]
    return feed


def test_per_source_cap_and_interleaving():
    sources = [
        {"name": "Big Source", "url": "https://big.example.com/rss"},
        {"name": "Small Source", "url": "https://small.example.com/rss"},
        {"name": "Mid Source", "url": "https://mid.example.com/rss"},
    ]

    with patch.object(rss_ingest, "_parse_feed", side_effect=_fake_parse_feed):
        items = rss_ingest.fetch_rss_feeds(sources, per_source_limit=8)

    from collections import Counter

    counts = Counter(i["source_name"] for i in items)

    # Every source should be capped at per_source_limit (or its actual total if smaller).
    assert counts["Big Source"] == 8
    assert counts["Small Source"] == 2
    assert counts["Mid Source"] == 8

    # The first few items should include all three sources (round-robin),
    # not just the "Big Source" filling the whole prefix.
    first_six_sources = {i["source_name"] for i in items[:6]}
    assert first_six_sources == {"Big Source", "Small Source", "Mid Source"}


def test_empty_sources_returns_empty_list():
    with patch.object(rss_ingest, "_parse_feed", side_effect=_fake_parse_feed):
        assert rss_ingest.fetch_rss_feeds([]) == []


def test_source_missing_url_is_skipped():
    sources = [{"name": "No URL"}]
    with patch.object(rss_ingest, "_parse_feed", side_effect=_fake_parse_feed):
        assert rss_ingest.fetch_rss_feeds(sources) == []
