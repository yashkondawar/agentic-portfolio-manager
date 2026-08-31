"""News staging pipeline: fetches RSS feeds, filters to recent entries, and
stages raw rows into news_items for later LLM enrichment (Phase 4).

This pipeline does NOT set event_scope/tag/impact/description — those stay
at their neutral defaults ('NA'/'NA', processed=0) here. Phase 4's
news_processor agent is responsible for filling them in.

Dedupe: url has a UNIQUE constraint in the schema (INSERT OR IGNORE handles
that); we additionally compute raw_hash = sha256(title) so a future
near-duplicate-detection pass (same story, different URL/query params) has
something to key off, per the spec.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import sqlite3
import time

import feedparser

from afund.data.base import Pipeline
from afund.data.http import make_session
from afund.sources import load_sources

LOOKBACK_DAYS = 3


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _entry_published(entry) -> dt.datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return dt.datetime(*parsed[:6], tzinfo=dt.timezone.utc)


def fetch_feed_text(url: str, timeout: float = 20.0) -> str:
    session = make_session()
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse_feed(feed_text: str, source_name: str, now: dt.datetime | None = None) -> list[dict]:
    """Parse one feed's raw XML/text into staged news_items row dicts,
    filtered to entries published within the last LOOKBACK_DAYS days.
    Entries with no parseable publish date are included (better to stage an
    undated item than silently drop it) with event_date = None.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=LOOKBACK_DAYS)

    parsed_feed = feedparser.parse(feed_text)
    rows: list[dict] = []
    for entry in parsed_feed.entries:
        url = entry.get("link")
        title = entry.get("title")
        if not url or not title:
            continue

        published_dt = _entry_published(entry)
        if published_dt is not None and published_dt < cutoff:
            continue

        rows.append(
            {
                "raw_title": title.strip(),
                "url": url.strip(),
                "source": source_name,
                "event_date": published_dt.date().isoformat() if published_dt else None,
                "raw_hash": _sha256(title.strip()),
            }
        )
    return rows


class NewsRssPipeline(Pipeline):
    """Fetches every feed in config/sources.yaml -> rss_feeds, filters to the
    last 3 days, and stages new rows into news_items. A single feed failing
    (broken URL, timeout, parse error) is logged and skipped — it does not
    abort the other feeds."""

    job_name = "news_rss"

    def __init__(self, conn: sqlite3.Connection | None = None, feed_names: list[str] | None = None):
        super().__init__(conn)
        self.feed_names = feed_names  # None = all feeds in sources.yaml
        self.feed_errors: dict[str, str] = {}

    def fetch(self) -> dict[str, str]:
        sources = load_sources()
        feeds = sources.get("rss_feeds", {})
        names = self.feed_names or list(feeds.keys())

        raw_texts: dict[str, str] = {}
        for name in names:
            entry = feeds.get(name)
            if entry is None:
                continue
            try:
                raw_texts[name] = fetch_feed_text(entry["url"])
            except Exception as exc:  # noqa: BLE001 - one broken feed must not kill the run
                self.feed_errors[name] = f"{type(exc).__name__}: {exc}"
            time.sleep(0.5)  # be polite across feeds even though each host is distinct
        return raw_texts

    def parse(self, raw: dict[str, str]) -> list[dict]:
        all_rows: list[dict] = []
        for name, text in raw.items():
            try:
                rows = parse_feed(text, source_name=name)
                all_rows.extend(rows)
            except Exception as exc:  # noqa: BLE001
                self.feed_errors[name] = f"parse {type(exc).__name__}: {exc}"
        return all_rows

    def upsert(self, parsed: list[dict]) -> int:
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        rows_written = 0
        for row in parsed:
            before = self.conn.total_changes
            self.conn.execute(
                """
                INSERT OR IGNORE INTO news_items
                    (event_scope, tag, impact, event_date, source, url, raw_title,
                     raw_hash, fetched_at, processed)
                VALUES ('NA', NULL, 'NA', ?, ?, ?, ?, ?, ?, 0)
                """,
                (row["event_date"], row["source"], row["url"], row["raw_title"], row["raw_hash"], now_iso),
            )
            rows_written += self.conn.total_changes - before
        self.conn.commit()

        if self.feed_errors:
            # Surface partial failures without raising: append to job error via a
            # second, informational job_runs row rather than failing the whole run.
            from afund.data.base import log_job_run

            error_summary = "; ".join(f"{k}: {v}" for k, v in self.feed_errors.items())
            log_job_run(
                self.conn,
                "news_rss_feed_errors",
                "PARTIAL",
                rows_written,
                now_iso,
                dt.datetime.now(dt.timezone.utc).isoformat(),
                error_summary,
            )
        return rows_written
