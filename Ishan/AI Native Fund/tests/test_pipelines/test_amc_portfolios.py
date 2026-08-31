"""Offline tests for afund.data.amc_portfolios — AMC monthly portfolio
disclosure downloader.

Covers the pieces adapted from the source research tool (see module
docstring): date/period extraction (including the 2-digit-year regression
case), the static-site scraper + monthly-vs-fortnightly/factsheet keyword
filtering against a synthetic page mirroring Nippon India MF's real
structure, amc_portfolio_files upsert idempotency, and the guarded-import
dynamic-AMC skip path (with its install-hint message) when playwright is not
installed. No network."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import requests

from afund.data.amc_portfolios import (
    AmcPortfoliosPipeline,
    DisclosureLink,
    PLAYWRIGHT_AVAILABLE,
    PLAYWRIGHT_INSTALL_MESSAGE,
    compute_target_periods,
    discover_links_static,
    extract_year_month,
    matches_disclosure_keywords,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"
MOCK_DYNAMIC_SITE = REPO_ROOT / "tests" / "fixtures" / "mock_amc_dynamic_site.html"


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "afund_test.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()
    yield connection
    connection.close()


# ---------------------------------------------------------------------------
# Date / period extraction
# ---------------------------------------------------------------------------

DATE_CASES = [
    ("Monthly portfolio for the month of March 2026", (2026, 3)),
    ("Monthly portfolio as on 30th April 2025", (2025, 4)),
    ("Monthly portfolio for the month end 31st July 2015", (2015, 7)),
    ("Monthly portfolio for the month of​ ​November 2025", (2025, 11)),
    ("Debt Schemes Portfolio as on 15th June 2025", (2025, 6)),
    ("Monthly portfolio as on 28th February 2025", (2025, 2)),
    ("Fundamentals - August 2019", (2019, 8)),
    ("NIMF-MONTHLY-PORTFOLIO-31-May-26.xls", (2026, 5)),
    ("NIMF-MONTHLY-PORTFOLIO-30-April-25.xls", (2025, 4)),
    ("MONTHLY-PORTFOLIO-DEC-23.xls", (2023, 12)),               # 2-digit year regression case
    ("Reliance-Monthly-Portfolios-31.12.2015.xls", (2015, 12)),
    ("NIMF_MONTHLY_PORTFOLIO_31-Jan-25.xls", (2025, 1)),
    ("Reliance-Monthly-Portfolios-28.02.2018.xls", (2018, 2)),
    ("MONTHLY-PORTFOLIO-REPORT-March-24.xls", (2024, 3)),        # 2-digit year regression case
    ("Reliance-Monthly-Portfolios-30.11.2018.xls", (2018, 11)),
    ("NIMF-MONTHLY-PORTFOLIO-Nov-25.xls", (2025, 11)),
    ("Some totally unrelated file.pdf", None),
]


@pytest.mark.parametrize("text,expected", DATE_CASES)
def test_extract_year_month(text, expected):
    assert extract_year_month(text) == expected


def test_compute_target_periods_wraps_year_boundary():
    from datetime import date
    periods = compute_target_periods(4, as_of=date(2026, 2, 1))
    assert periods == [(2026, 2), (2026, 1), (2025, 12), (2025, 11)]


# ---------------------------------------------------------------------------
# Static HTML scraper + keyword filtering (mirrors Nippon India MF structure)
# ---------------------------------------------------------------------------

SAMPLE_HTML = """
<html><body><div class="page-content"><ul>
  <li>Debt Schemes Portfolio as on 30th June 2026
    <a href="/Docs/NIMF-FORTNIGHTLY-PORTFOLIO-30-Jun-26.xls">Download</a></li>
  <li>E- Factsheet: June 2026
    <a href="/Docs/Nippon-FS-JUNE-2026.pdf">Download</a></li>
  <li>Monthly portfolio for the month of June 2026
    <a href="/Docs/NIMF-MONTHLY-PORTFOLIO-30-Jun-26.xls">Download</a></li>
  <li>Monthly portfolio for the month of May 2026
    <a href="/Docs/NIMF-MONTHLY-PORTFOLIO-31-May-26.xls">Download</a></li>
</ul></div></body></html>
"""


def test_matches_disclosure_keywords():
    from afund.data.amc_portfolios import DEFAULT_INCLUDE_KEYWORDS, DEFAULT_EXCLUDE_KEYWORDS

    assert matches_disclosure_keywords(
        "Monthly portfolio for the month of June 2026", DEFAULT_INCLUDE_KEYWORDS, DEFAULT_EXCLUDE_KEYWORDS
    )
    assert not matches_disclosure_keywords(
        "Debt Schemes Portfolio as on 30th June 2026 (Fortnightly)",
        DEFAULT_INCLUDE_KEYWORDS, DEFAULT_EXCLUDE_KEYWORDS,
    )
    assert not matches_disclosure_keywords(
        "E- Factsheet: June 2026", DEFAULT_INCLUDE_KEYWORDS, DEFAULT_EXCLUDE_KEYWORDS
    )


class _MockResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


class _MockSession:
    """Stands in for requests.Session -- returns SAMPLE_HTML for any GET,
    so discover_links_static() is exercised end-to-end (including its own
    robots.txt check, which fails-open with no network) without touching
    the real site."""

    def get(self, url, timeout=None, **kwargs):
        return _MockResponse(SAMPLE_HTML)


def test_static_scraper_end_to_end_against_mock_nippon_page():
    target_periods = {(2026, 6), (2026, 5)}
    links = discover_links_static(
        "nippon_india", "https://mf.nipponindiaim.com/fake-listing-page",
        _MockSession(), target_periods,
    )
    assert len(links) == 2, f"Expected 2 monthly links (fortnightly/factsheet excluded), got {links}"
    periods = {(l.year, l.month) for l in links}
    assert periods == {(2026, 6), (2026, 5)}
    assert all(l.amc_slug == "nippon_india" for l in links)
    assert all(l.url.startswith("https://mf.nipponindiaim.com/Docs/") for l in links)


def test_static_scraper_filters_out_of_range_periods():
    # Only ask for June 2026 -- May 2026 link exists on the page but is out
    # of the requested target_periods window and must not come back.
    links = discover_links_static(
        "nippon_india", "https://mf.nipponindiaim.com/fake-listing-page",
        _MockSession(), {(2026, 6)},
    )
    assert len(links) == 1
    assert (links[0].year, links[0].month) == (2026, 6)


# ---------------------------------------------------------------------------
# amc_portfolio_files upsert idempotency
# ---------------------------------------------------------------------------

def test_upsert_idempotent_rerun_same_file(conn):
    pipeline = AmcPortfoliosPipeline(conn=conn)
    parsed = [
        {
            "amc": "nippon_india", "period": "2026-06",
            "url": "https://mf.nipponindiaim.com/Docs/NIMF-MONTHLY-PORTFOLIO-30-Jun-26.xls",
            "local_path": "data/raw/amc_portfolios/nippon_india/2026-06_NIMF-MONTHLY-PORTFOLIO-30-Jun-26.xls",
            "file_size": 123456, "status": "downloaded",
        }
    ]
    pipeline.upsert(parsed)
    pipeline.upsert(parsed)  # re-run: no duplicate row

    rows = conn.execute("SELECT * FROM amc_portfolio_files").fetchall()
    assert len(rows) == 1
    assert rows[0]["amc"] == "nippon_india"
    assert rows[0]["period"] == "2026-06"
    assert rows[0]["status"] == "downloaded"
    assert rows[0]["file_size"] == 123456


def test_upsert_distinguishes_by_amc_period_url(conn):
    pipeline = AmcPortfoliosPipeline(conn=conn)
    parsed = [
        {"amc": "nippon_india", "period": "2026-05", "url": "https://x/a.xls",
         "local_path": "p1", "file_size": 100, "status": "downloaded"},
        {"amc": "nippon_india", "period": "2026-06", "url": "https://x/b.xls",
         "local_path": "p2", "file_size": 200, "status": "downloaded"},
    ]
    rows_written = pipeline.upsert(parsed)
    assert rows_written == 2

    stored = conn.execute("SELECT period, file_size FROM amc_portfolio_files ORDER BY period").fetchall()
    assert [dict(r) for r in stored] == [
        {"period": "2026-05", "file_size": 100},
        {"period": "2026-06", "file_size": 200},
    ]


def test_upsert_failed_status_keeps_url_for_retry(conn):
    pipeline = AmcPortfoliosPipeline(conn=conn)
    parsed = [
        {"amc": "hdfc", "period": "2026-06", "url": "https://x/failed.xls",
         "local_path": None, "file_size": None, "status": "failed", "error": "timeout"},
    ]
    pipeline.upsert(parsed)
    row = conn.execute("SELECT * FROM amc_portfolio_files WHERE amc = 'hdfc'").fetchone()
    assert row["status"] == "failed"
    assert row["local_path"] is None


def test_upsert_coalesces_local_path_never_clobbers_with_null(conn):
    # First write succeeds with a local_path; a later re-run that (for
    # whatever reason) reports status without a local_path must not wipe
    # out the previously-recorded path (COALESCE semantics per project
    # hard rule: DB writes never clobber non-NULL with NULL).
    pipeline = AmcPortfoliosPipeline(conn=conn)
    pipeline.upsert([
        {"amc": "nippon_india", "period": "2026-06", "url": "https://x/c.xls",
         "local_path": "data/raw/c.xls", "file_size": 999, "status": "downloaded"},
    ])
    pipeline.upsert([
        {"amc": "nippon_india", "period": "2026-06", "url": "https://x/c.xls",
         "local_path": None, "file_size": None, "status": "skipped_exists"},
    ])
    row = conn.execute("SELECT * FROM amc_portfolio_files WHERE url = 'https://x/c.xls'").fetchone()
    assert row["local_path"] == "data/raw/c.xls"
    assert row["file_size"] == 999
    assert row["status"] == "skipped_exists"


# ---------------------------------------------------------------------------
# Dynamic-AMC guard path (playwright not installed in this environment)
# ---------------------------------------------------------------------------

def test_playwright_install_message_is_actionable():
    assert "pip install playwright" in PLAYWRIGHT_INSTALL_MESSAGE
    assert "playwright install chromium" in PLAYWRIGHT_INSTALL_MESSAGE


def test_pipeline_skips_dynamic_amcs_without_playwright(conn, monkeypatch):
    """When playwright isn't importable, a run scoped to a mix of static +
    dynamic AMCs must still process the static one and record the install
    hint rather than raising."""
    if PLAYWRIGHT_AVAILABLE:
        pytest.skip("playwright is installed in this environment; guard path not exercised")

    monkeypatch.setattr(
        "afund.data.amc_portfolios.discover_links_static",
        lambda *a, **kw: [],
    )
    pipeline = AmcPortfoliosPipeline(conn=conn, months=1, amcs=["nippon_india", "hdfc"])
    result = pipeline.run()

    assert result.status == "SUCCESS"
    assert any(PLAYWRIGHT_INSTALL_MESSAGE in note for note in result.extra.get("skip_notes", []))


def test_unconfigured_amcs_are_skipped_without_error(conn):
    pipeline = AmcPortfoliosPipeline(conn=conn, months=1, amcs=["axis"])  # architecture: unconfigured
    result = pipeline.run()
    assert result.status == "SUCCESS"
    assert result.rows_written == 0


# ---------------------------------------------------------------------------
# Dynamic (Playwright) scraper mechanics against the local mock page --
# only runs if playwright is actually installed (optional dependency).
# ---------------------------------------------------------------------------

def test_dynamic_scraper_no_stale_results_across_queries():
    """Regression test for the stale-page-state bug: sequential queries on
    fresh pages must each return their OWN month's result, not the previous
    query's leftover data."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("playwright not installed")
    if not MOCK_DYNAMIC_SITE.exists():
        pytest.skip("mock_amc_dynamic_site.html fixture not present")

    from afund.data.amc_portfolios import generic_dropdown_scrape
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for year, month, expected_substr in [(2026, 5, "May-2026"), (2026, 6, "June-2026"), (2026, 5, "May-2026")]:
                context = browser.new_context()
                page = context.new_page()
                links = generic_dropdown_scrape(
                    page, "mock_amc", f"file://{MOCK_DYNAMIC_SITE}", year, month
                )
                context.close()
                assert len(links) == 1, f"{year}-{month}: expected 1 link, got {links}"
                assert expected_substr in links[0].url, f"{year}-{month}: got wrong/stale result {links[0].url}"
        finally:
            browser.close()
