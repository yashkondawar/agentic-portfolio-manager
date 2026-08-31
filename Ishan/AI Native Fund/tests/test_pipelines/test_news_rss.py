"""Offline parser test for news_rss.py's feed parser. No network.

Uses an explicit `now` reference point matching the fixture's pubDates
(2026-07-03) so the test stays deterministic regardless of when it's run.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from afund.data.news_rss import parse_feed

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE_NOW = dt.datetime(2026, 7, 3, 18, 0, 0, tzinfo=dt.timezone.utc)


def test_parse_feed_extracts_entries():
    raw = (FIXTURES / "rss_zerodha_sample.xml").read_text(encoding="utf-8")
    rows = parse_feed(raw, source_name="pulse_zerodha", now=FIXTURE_NOW)

    assert len(rows) > 0
    for row in rows:
        assert row["source"] == "pulse_zerodha"
        assert row["url"]
        assert row["raw_title"]
        assert row["raw_hash"]


def test_parse_feed_first_entry_fields():
    raw = (FIXTURES / "rss_zerodha_sample.xml").read_text(encoding="utf-8")
    rows = parse_feed(raw, source_name="pulse_zerodha", now=FIXTURE_NOW)
    first = rows[0]
    assert "Rupee closes at 95.21" in first["raw_title"]
    assert first["url"].startswith("https://economictimes.indiatimes.com/")
    assert first["event_date"] == "2026-07-03"


def test_parse_feed_filters_entries_older_than_lookback():
    raw = (FIXTURES / "rss_zerodha_sample.xml").read_text(encoding="utf-8")
    far_future_now = FIXTURE_NOW + dt.timedelta(days=30)
    rows = parse_feed(raw, source_name="pulse_zerodha", now=far_future_now)
    assert rows == []


def test_parse_feed_empty_text_returns_empty_list():
    rows = parse_feed("", source_name="pulse_zerodha", now=FIXTURE_NOW)
    assert rows == []
