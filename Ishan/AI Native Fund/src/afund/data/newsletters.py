"""Newsletter fetch pipeline: DSP Netra + Aequitas monthly PDFs.

Both publishers' listing pages are scraped directly for PDF links (neither
site exposes a stable, guessable filename pattern reliable enough to
construct URLs without confirming they exist first — see the per-source
regex notes below). Downloaded PDFs are saved under
data/raw/newsletters/{publisher}/{filename} and registered in the
`newsletters` table (UNIQUE on (publisher, period), so re-running is safe).

Month-parametrized: `run(target_period=None)` defaults to "find whatever is
newest on the listing page" (the natural behavior for a monthly cron job);
passing an explicit "YYYY-MM" restricts to that period only (useful for
smoke tests / backfilling a specific missed month).
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from pathlib import Path

from bs4 import BeautifulSoup

from afund.config import REPO_ROOT
from afund.data.base import Pipeline
from afund.data.http import make_session
from afund.sources import get_source

RAW_NEWSLETTERS_DIR = REPO_ROOT / "data" / "raw" / "newsletters"

_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _period_from_dsp_filename(url: str) -> str | None:
    """DSP Netra filenames look like dspnetra-may26.pdf / dspnetra-april-26.pdf
    / dspnetra-mar26.pdf — inconsistent hyphenation, month name length 3+.
    Extract "{mon}{-}{yy}" and normalize to YYYY-MM."""
    filename = url.rsplit("/", 1)[-1]
    match = re.search(r"dspnetra-([a-zA-Z]+)-?(\d{2})\.pdf", filename, re.IGNORECASE)
    if not match:
        return None
    month_text, year_two = match.group(1).lower(), match.group(2)
    month_num = _MONTH_ABBR.get(month_text[:3])
    if month_num is None:
        return None
    year = 2000 + int(year_two)
    return f"{year:04d}-{month_num:02d}"


def _period_from_aequitas_url(url: str) -> str | None:
    """Aequitas PDFs live at .../wp-content/uploads/{YYYY}/{MM}/... — the URL
    path itself encodes the period, which is far more reliable than parsing
    the (inconsistent) filename."""
    match = re.search(r"/uploads/(\d{4})/(\d{2})/", url)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"


def find_dsp_netra_pdfs(session=None) -> list[dict]:
    """Scrape the DSP Netra listing page for PDF links, returning
    [{"url", "period"}] sorted newest period first."""
    source = get_source("newsletters", "dsp_netra")
    session = session or make_session()
    resp = session.get(source["url"], timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    seen: dict[str, str] = {}  # url -> period, dedupes duplicate <a> tags (READ + DOWNLOAD)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "dspnetra" in href.lower() and href.lower().endswith(".pdf"):
            period = _period_from_dsp_filename(href)
            if period:
                seen[href] = period

    results = [{"url": url, "period": period} for url, period in seen.items()]
    results.sort(key=lambda r: r["period"], reverse=True)
    return results


def find_aequitas_pdfs(session=None) -> list[dict]:
    """Scrape the Aequitas newsletter listing page for "Top Down Bottom Up"
    PDF links, returning [{"url", "period"}] sorted newest period first."""
    source = get_source("newsletters", "aequitas")
    session = session or make_session()
    resp = session.get(source["url"], timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    seen: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "top-down-bottom-up" in href.lower() and href.lower().endswith(".pdf"):
            period = _period_from_aequitas_url(href)
            if period:
                seen[href] = period

    results = [{"url": url, "period": period} for url, period in seen.items()]
    results.sort(key=lambda r: r["period"], reverse=True)
    return results


def _download_pdf(session, url: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = url.rsplit("/", 1)[-1]
    dest_path = dest_dir / filename
    if not dest_path.exists():
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        dest_path.write_bytes(resp.content)
    return dest_path


class NewslettersPipeline(Pipeline):
    """Fetches the latest (or a specific target_period) DSP Netra and
    Aequitas newsletter PDFs and registers them in the `newsletters` table."""

    job_name = "newsletters"

    def __init__(self, conn: sqlite3.Connection | None = None, target_period: str | None = None):
        super().__init__(conn)
        self.target_period = target_period  # "YYYY-MM" or None = newest available
        self.session = make_session()

    def fetch(self) -> dict[str, list[dict]]:
        return {
            "DSP_NETRA": find_dsp_netra_pdfs(self.session),
            "AEQUITAS": find_aequitas_pdfs(self.session),
        }

    def parse(self, raw: dict[str, list[dict]]) -> dict[str, dict | None]:
        selected: dict[str, dict | None] = {}
        for publisher, candidates in raw.items():
            if not candidates:
                selected[publisher] = None
                continue
            if self.target_period:
                match = next((c for c in candidates if c["period"] == self.target_period), None)
                selected[publisher] = match
            else:
                selected[publisher] = candidates[0]  # newest first (pre-sorted)
        return selected

    def upsert(self, parsed: dict[str, dict | None]) -> int:
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        rows_written = 0

        for publisher, item in parsed.items():
            if item is None:
                continue
            dest_dir = RAW_NEWSLETTERS_DIR / publisher
            try:
                local_path = _download_pdf(self.session, item["url"], dest_dir)
            except Exception:
                continue  # one publisher failing to download must not abort the other

            before = self.conn.total_changes
            self.conn.execute(
                """
                INSERT INTO newsletters (publisher, title, period, url, local_path, fetched_at, parsed)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(publisher, period) DO UPDATE SET
                    url = excluded.url,
                    local_path = excluded.local_path,
                    fetched_at = excluded.fetched_at
                """,
                (
                    publisher,
                    f"{publisher.replace('_', ' ').title()} {item['period']}",
                    item["period"],
                    item["url"],
                    str(local_path),
                    now_iso,
                ),
            )
            rows_written += max(self.conn.total_changes - before, 1)

        self.conn.commit()
        return rows_written
