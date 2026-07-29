"""Validate every RSS source in config/sources.yaml.

Run this from an environment with normal internet access (e.g. Google Cloud
Shell, your local machine, or the Cloud Run container itself via `exec`) —
NOT from a network-restricted sandbox, since it needs to reach 40+ live news
sites directly.

Usage:
    python3 scripts/validate_sources.py

It reports, per source: HTTP status, whether feedparser could parse it as a
real feed, and how many entries it returned. Sources that fail are exactly
the ones silently contributing zero items to every report — this tells you
which to fix or remove instead of guessing from the final output alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

import feedparser
import requests
import yaml

SOURCES_PATH = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"
TIMEOUT = 15


def validate_source(source: dict) -> dict:
    name = source.get("name", "Unknown")
    url = source.get("rss") or source.get("url") or ""
    tier = source.get("tier", "C")

    result = {"name": name, "tier": tier, "url": url, "ok": False, "entries": 0, "error": ""}

    if not url:
        result["error"] = "No URL configured"
        return result

    try:
        response = requests.get(
            url,
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (MENA-Agent-Validator/1.0)"},
        )
        response.raise_for_status()
    except Exception as exc:
        result["error"] = f"HTTP error: {exc}"
        return result

    feed = feedparser.parse(response.content)
    entry_count = len(getattr(feed, "entries", []) or [])
    result["entries"] = entry_count

    if entry_count == 0:
        result["error"] = "Fetched OK but 0 entries parsed (not a valid RSS/Atom feed?)"
        return result

    result["ok"] = True
    return result


def main() -> int:
    with SOURCES_PATH.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    sources = config.get("sources", [])

    print(f"Validating {len(sources)} sources...\n")

    results = [validate_source(s) for s in sources]

    working = [r for r in results if r["ok"]]
    broken = [r for r in results if not r["ok"]]

    print(f"{'TIER':<5} {'STATUS':<7} {'ENTRIES':<8} NAME")
    print("-" * 70)
    for r in sorted(results, key=lambda x: (not x["ok"], x["tier"], x["name"])):
        status = "OK" if r["ok"] else "FAIL"
        print(f"{r['tier']:<5} {status:<7} {r['entries']:<8} {r['name']}")
        if not r["ok"]:
            print(f"      -> {r['error']}")

    print("\n" + "=" * 70)
    print(f"SUMMARY: {len(working)}/{len(results)} sources working, {len(broken)} broken\n")

    if broken:
        print("Broken sources (fix the URL or remove from sources.yaml):")
        for r in broken:
            print(f"  - {r['name']}: {r['url']}")

    return 0 if not broken else 1


if __name__ == "__main__":
    sys.exit(main())
