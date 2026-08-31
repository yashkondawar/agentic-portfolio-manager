"""AMC monthly portfolio disclosure downloader.

Downloads SEBI-mandated monthly portfolio disclosure Excel files, published
by Indian Mutual Fund AMCs on their own websites, for the last N months.
Download-only: this pipeline discovers links and saves the raw .xls/.xlsx
files under data/raw/amc_portfolios/<AMC_SLUG>/ and registers one row per
file in `amc_portfolio_files`. Parsing the Excel contents is explicitly
future scope — see the AI-Native Fund plan file.

WHY THIS ISN'T A SIMPLE ONE-PATTERN SCRAPER
--------------------------------------------
AMFI's own disclosure directory (amfiindia.com/online-center/portfolio-disclosure)
is a JavaScript-rendered page with no static list of AMC links — it can't be
scraped with a plain HTTP request. More importantly, AMFI is only a
directory: the actual portfolio files always live on each AMC's own website
(that's the SEBI disclosure requirement), so this pipeline targets AMC sites
directly, via config/sources.yaml's `amc_portfolios` group.

Those AMC sites split into two genuinely different architectures (see each
entry's `architecture` field in sources.yaml):

  1. STATIC sites (e.g. Nippon India Mutual Fund) still render a plain HTML
     list with a real <a href="...xls"> link for every past month. These are
     scraped with `requests` + BeautifulSoup — fast, reliable, no browser
     needed. Fully live in this pipeline.

  2. DYNAMIC sites (e.g. HDFC, SBI, Kotak) have been rebuilt as JS
     single-page apps: you pick Frequency/Year/Month from dropdowns and an
     AJAX call fills in a results table. These need a real browser
     (Playwright) to render the JavaScript and click through the filters.
     Playwright is an OPTIONAL dependency (not installed by default — it
     pulls a full Chromium download). If it's not importable, this pipeline
     skips dynamic-architecture AMCs with a clear one-line instruction
     rather than failing the whole run:

         playwright not installed -- dynamic AMCs skipped (HDFC/SBI/Kotak...);
         install with: pip install playwright && playwright install chromium

Vendored from a standalone research tool (amc_downloader.py, July 2026);
adapted into this project's Pipeline base-class style (fetch/parse/upsert +
job_runs logging via afund.data.base.Pipeline) and config/sources.yaml
source-of-truth convention instead of its own amc_config.json.

Downloads land in data/raw/amc_portfolios/<AMC_SLUG>/<YYYY-MM>_<orig_name>.xlsx.
Idempotent: a file already on disk (matched by local path) is not
re-downloaded; a DB row already present for (amc, period, url) is upserted,
never duplicated. Polite throttling (POLITE_DELAY_SECONDS between requests)
and a robots.txt courtesy check are preserved from the source tool.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
import time
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from afund.config import REPO_ROOT
from afund.data.base import Pipeline
from afund.data.http import make_session
from afund.sources import load_sources

RAW_AMC_PORTFOLIOS_DIR = REPO_ROOT / "data" / "raw" / "amc_portfolios"

USER_AGENT = (
    "Mozilla/5.0 (compatible; AI-Native-Fund-Research-Bot/1.0; "
    "personal/research use; contact: ishankulkarni97@gmail.com)"
)
REQUEST_TIMEOUT = 30
RETRY_COUNT = 3
RETRY_BACKOFF_SECONDS = 2.0
POLITE_DELAY_SECONDS = 1.5

PLAYWRIGHT_INSTALL_MESSAGE = (
    "playwright not installed -- dynamic AMCs skipped (HDFC/SBI/Kotak...); "
    "install with: pip install playwright && playwright install chromium"
)

FILE_EXT_RE = re.compile(r"\.(xlsx?|xlsb|zip|csv)(\?.*)?$", re.IGNORECASE)

DEFAULT_INCLUDE_KEYWORDS = ["monthly portfolio"]
DEFAULT_EXCLUDE_KEYWORDS = [
    "fortnightly", "risk parameter", "factsheet", "fundamentals",
    "riskometer", "half yearly", "half-yearly", "annual report",
]

MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_ALTS = "|".join(sorted(MONTH_MAP.keys(), key=len, reverse=True))
MONTH_RE = re.compile(rf"\b({_MONTH_ALTS})\b", re.IGNORECASE)
YEAR4_RE = re.compile(r"\b(19|20)\d{2}\b")
ORDINAL_NUM_RE = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)\b", re.IGNORECASE)
BARE_2DIGIT_RE = re.compile(r"\b\d{2}\b")
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\b")
MONTH_FULLNAME = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November",
    12: "December",
}

# AMCs whose sources.yaml `architecture` is playwright_dynamic — used only
# for the install-hint message (see PLAYWRIGHT_INSTALL_MESSAGE / run.py logs).
_DYNAMIC_AMC_EXAMPLES = "HDFC/SBI/Kotak"


# ============================================================================
# Date / period extraction (unchanged from the source tool — tested against
# every real label & filename format observed while researching AMC sites,
# see tests/test_pipelines/test_amc_portfolios.py)
# ============================================================================

def extract_year_month(raw_text: str) -> Optional[tuple[int, int]]:
    """Best-effort (year, month) extraction from disclosure label text or a
    filename. Returns None if no confident match is found. Deliberately
    avoids naive dateutil fuzzy-parsing, which silently misreads 2-digit
    years like 'DEC-23' as day-of-month-23-of-the-current-year."""
    if not raw_text:
        return None
    text = raw_text.replace("​", " ").replace("﻿", " ")
    text = re.sub(r"[_.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    month_match = MONTH_RE.search(text)

    if not month_match:
        m = NUMERIC_DATE_RE.search(raw_text)
        if not m:
            return None
        d, mo, y = m.groups()
        mo, y = int(mo), int(y)
        if y < 100:
            y += 2000
        if 1 <= mo <= 12 and 1 <= int(d) <= 31:
            return (y, mo)
        return None

    month = MONTH_MAP[month_match.group(1).lower()]

    year4_match = YEAR4_RE.search(text)
    if year4_match:
        return (int(year4_match.group(0)), month)

    text_wo_ordinals = ORDINAL_NUM_RE.sub(" ", text)
    candidates = BARE_2DIGIT_RE.findall(text_wo_ordinals)
    if candidates:
        year = int(candidates[-1]) + 2000
        return (year, month)

    return None


def compute_target_periods(n_months: int, as_of: Optional[dt.date] = None) -> list[tuple[int, int]]:
    """Returns [(year, month), ...] for the last n_months, most recent first,
    including the current month (it may or may not be published yet -- that's
    fine, unmatched periods are simply not found)."""
    if as_of is None:
        as_of = dt.date.today()
    periods = []
    y, m = as_of.year, as_of.month
    for _ in range(n_months):
        periods.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return periods


def matches_disclosure_keywords(label: str, include_kw: list[str], exclude_kw: list[str]) -> bool:
    t = label.lower()
    if any(bad in t for bad in exclude_kw):
        return False
    return any(good in t for good in include_kw)


def is_scraping_allowed(url: str, user_agent: str) -> bool:
    """robots.txt courtesy check. Best-effort — a lookup failure defaults to
    "allowed" rather than blocking a legitimate download (see caveats in the
    original tool's README: a network-sandboxed 403 on robots.txt itself can
    look identical to a real disallow, so this only warns/skips on an actual
    parsed disallow, not on a fetch failure)."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:150]


@dataclass
class DisclosureLink:
    amc_slug: str
    label: str
    url: str
    year: int
    month: int


# ============================================================================
# Static-site scraper (requests + BeautifulSoup)
# ============================================================================

def discover_links_static(
    amc_slug: str,
    url: str,
    session: requests.Session,
    target_periods: set[tuple[int, int]],
    include_kw: list[str] | None = None,
    exclude_kw: list[str] | None = None,
) -> list[DisclosureLink]:
    include_kw = include_kw if include_kw is not None else DEFAULT_INCLUDE_KEYWORDS
    exclude_kw = exclude_kw if exclude_kw is not None else DEFAULT_EXCLUDE_KEYWORDS

    if not is_scraping_allowed(url, USER_AGENT):
        return []

    resp = session.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    links: list[DisclosureLink] = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not FILE_EXT_RE.search(href):
            continue

        container = a.find_parent(["li", "p", "div", "tr"])
        label = container.get_text(" ", strip=True) if container else a.get_text(strip=True)

        if not matches_disclosure_keywords(label, include_kw, exclude_kw):
            continue

        period = extract_year_month(label) or extract_year_month(href)
        if period is None:
            continue
        if period not in target_periods:
            continue

        full_url = href if href.startswith("http") else urljoin(url, href)
        links.append(DisclosureLink(amc_slug, label, full_url, period[0], period[1]))

    return links


# ============================================================================
# Dynamic-site scraper (Playwright) -- BEST EFFORT, guarded import.
#
# Generic strategy: find <select> elements on the page, guess which one is
# "Frequency"/"Year"/"Month" from their associated label text, set them, then
# click whatever button looks like a search/submit action, then harvest any
# resulting file links. Deliberately generic rather than hard-coded per AMC
# since exact DOM selectors were never verified against live sites (per
# sources.yaml `notes` for each playwright_dynamic entry) — will likely need
# adjustment per site.
#
# CRITICAL: a fresh page.goto() is used for every single (year, month) query.
# Reusing one page across sequential dropdown selections returns the
# PREVIOUS query's stale results (the results element already exists in the
# DOM, so a naive wait_for_selector succeeds immediately without the content
# actually having updated) -- do not "optimize" this into one shared page
# without re-solving that.
# ============================================================================

SEARCH_BUTTON_PATTERN = re.compile(r"search|submit|view|apply|filter|go\b", re.IGNORECASE)


def _select_best_effort(page, keyword_pattern: str, value_options: list[str]) -> bool:
    """Try to find a <select> whose accessible label matches keyword_pattern
    and set it to one of value_options (tried as label text, then as raw
    value). Returns True if something was selected."""
    pattern = re.compile(keyword_pattern, re.IGNORECASE)
    selects = page.locator("select")
    count = selects.count()
    for i in range(count):
        sel = selects.nth(i)
        try:
            label_text = ""
            sel_id = sel.get_attribute("id")
            if sel_id:
                label_loc = page.locator(f'label[for="{sel_id}"]')
                if label_loc.count() > 0:
                    label_text = label_loc.first.inner_text()
            if not label_text:
                label_text = sel.get_attribute("aria-label") or sel.get_attribute("name") or ""
            if not pattern.search(label_text):
                continue
            for value in value_options:
                # Explicit short timeout: Playwright's default action timeout
                # is 30s and does NOT fail fast when a label/value simply
                # doesn't exist among the <option>s -- without this a single
                # not-yet-published month (a routine, expected case) would
                # hang for minutes per attempt.
                try:
                    sel.select_option(label=value, timeout=800)
                    return True
                except Exception:
                    pass
                try:
                    sel.select_option(value=value, timeout=800)
                    return True
                except Exception:
                    pass
        except Exception:
            pass
    return False


def generic_dropdown_scrape(
    page,
    amc_slug: str,
    base_url: str,
    year: int,
    month: int,
) -> list[DisclosureLink]:
    month_name = MONTH_FULLNAME[month]
    try:
        page.goto(base_url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
    except PlaywrightError:
        return []

    _select_best_effort(page, r"freq|type|category", ["Monthly", "monthly"])
    got_year = _select_best_effort(page, r"year", [str(year)])
    got_month = _select_best_effort(
        page, r"month", [month_name, month_name[:3], str(month), f"{month:02d}"]
    )

    if not (got_year or got_month):
        return []

    for role in ("button", "link"):
        try:
            btn = page.get_by_role(role, name=SEARCH_BUTTON_PATTERN)
            if btn.count() > 0:
                btn.first.click(timeout=5000)
                break
        except Exception:
            continue

    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except PlaywrightError:
        pass

    # IMPORTANT: do not read the DOM immediately after networkidle -- that
    # event only tracks actual network requests, so it fires almost
    # instantly on pages where results are populated by a setTimeout or a
    # client-side render tick after a fetch already completed. Poll briefly
    # for a qualifying file link to actually appear instead of trusting one
    # signal (confirmed by testing on the mock dynamic-site fixture).
    anchors: list[dict] = []
    deadline = time.time() + 4.0
    while time.time() < deadline:
        try:
            anchors = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => ({href: e.href, text: e.innerText || e.textContent}))"
            )
        except PlaywrightError:
            return []
        if any(FILE_EXT_RE.search(a.get("href", "")) for a in anchors):
            break
        page.wait_for_timeout(400)

    links = []
    for a in anchors:
        href = a.get("href", "")
        if not FILE_EXT_RE.search(href):
            continue
        label = (a.get("text") or "").strip() or href
        links.append(DisclosureLink(amc_slug, label, href, year, month))
    return links


def discover_links_playwright(
    amc_slug: str,
    url: str,
    browser,
    target_periods: list[tuple[int, int]],
) -> list[DisclosureLink]:
    if not is_scraping_allowed(url, USER_AGENT):
        return []

    context = browser.new_context(user_agent=USER_AGENT)
    page = context.new_page()
    all_links: list[DisclosureLink] = []

    try:
        for (year, month) in target_periods:
            found = generic_dropdown_scrape(page, amc_slug, url, year, month)
            all_links.extend(found)
            time.sleep(POLITE_DELAY_SECONDS)
    finally:
        context.close()

    return all_links


# ============================================================================
# Downloading
# ============================================================================

def _dest_path_for(link: DisclosureLink) -> Path:
    amc_dir = RAW_AMC_PORTFOLIOS_DIR / link.amc_slug
    original_name = Path(urlparse(link.url).path).name or "file.xlsx"
    local_name = f"{link.year:04d}-{link.month:02d}_{sanitize_filename(original_name)}"
    return amc_dir / local_name


def download_one(session: requests.Session, link: DisclosureLink) -> dict:
    """Download one disclosure file to disk. Returns a dict shaped for
    upsert() — status in {'downloaded', 'skipped_exists', 'failed'}."""
    dest_path = _dest_path_for(link)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    period = f"{link.year:04d}-{link.month:02d}"

    if dest_path.exists():
        return {
            "amc": link.amc_slug, "period": period, "url": link.url,
            "local_path": str(dest_path), "file_size": dest_path.stat().st_size,
            "status": "skipped_exists",
        }

    last_error = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = session.get(link.url, timeout=REQUEST_TIMEOUT, stream=True)
            resp.raise_for_status()
            tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            tmp_path.rename(dest_path)
            return {
                "amc": link.amc_slug, "period": period, "url": link.url,
                "local_path": str(dest_path), "file_size": dest_path.stat().st_size,
                "status": "downloaded",
            }
        except requests.RequestException as e:
            last_error = str(e)
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    return {
        "amc": link.amc_slug, "period": period, "url": link.url,
        "local_path": None, "file_size": None,
        "status": "failed", "error": last_error,
    }


# ============================================================================
# Pipeline
# ============================================================================

class AmcPortfoliosPipeline(Pipeline):
    """Fetches the last N months of monthly portfolio disclosure Excel files
    from every AMC configured in config/sources.yaml's `amc_portfolios`
    group, and registers each download in `amc_portfolio_files`.

    Static-architecture AMCs (requests + BeautifulSoup) always run.
    Dynamic-architecture AMCs (Playwright) only run if the optional
    `playwright` package is importable; otherwise they're skipped with a
    logged install hint (see PLAYWRIGHT_INSTALL_MESSAGE) rather than failing
    the whole pipeline. `unconfigured`/no-URL entries are skipped silently
    (nothing to fetch yet — see sources.yaml notes).
    """

    job_name = "amc_portfolios"

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        months: int = 3,
        amcs: list[str] | None = None,
        headed: bool = False,
    ):
        super().__init__(conn)
        self.months = months
        self.amcs = amcs  # slugs to restrict to, or None = all configured
        self.headed = headed
        self.session = make_session(user_agent=USER_AGENT)
        self.skip_notes: list[str] = []  # human-readable notes surfaced via JobResult.extra

    def _amc_entries(self) -> dict[str, dict]:
        sources = load_sources()
        all_entries = sources.get("amc_portfolios", {})
        if self.amcs:
            wanted = set(self.amcs)
            return {slug: entry for slug, entry in all_entries.items() if slug in wanted}
        return all_entries

    def fetch(self) -> list[dict]:
        """Returns a flat list of download outcome dicts (see download_one),
        one per discovered disclosure link across all in-scope AMCs."""
        entries = self._amc_entries()
        target_periods_list = compute_target_periods(self.months)
        target_periods_set = set(target_periods_list)

        need_playwright = any(
            e.get("architecture") == "playwright_dynamic" for e in entries.values()
        )
        browser = None
        playwright_ctx = None
        if need_playwright:
            if not PLAYWRIGHT_AVAILABLE:
                self.skip_notes.append(PLAYWRIGHT_INSTALL_MESSAGE)
            else:
                playwright_ctx = sync_playwright().start()
                browser = playwright_ctx.chromium.launch(headless=not self.headed)

        outcomes: list[dict] = []
        try:
            for slug, entry in entries.items():
                architecture = entry.get("architecture")
                url = entry.get("url")

                if architecture == "unconfigured" or not url:
                    continue

                if architecture == "static_html":
                    try:
                        links = discover_links_static(slug, url, self.session, target_periods_set)
                    except requests.RequestException as e:
                        self.skip_notes.append(f"{slug}: fetch failed ({e})")
                        continue
                elif architecture == "playwright_dynamic":
                    if browser is None:
                        continue  # already recorded PLAYWRIGHT_INSTALL_MESSAGE above
                    links = discover_links_playwright(slug, url, browser, target_periods_list)
                else:
                    continue

                for link in links:
                    outcomes.append(download_one(self.session, link))
                    time.sleep(POLITE_DELAY_SECONDS)
        finally:
            if browser is not None:
                browser.close()
            if playwright_ctx is not None:
                playwright_ctx.stop()

        return outcomes

    def parse(self, raw: list[dict]) -> list[dict]:
        return raw  # download_one() already returns upsert-ready dicts

    def upsert(self, parsed: list[dict]) -> int:
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        rows_written = 0

        for item in parsed:
            before = self.conn.total_changes
            self.conn.execute(
                """
                INSERT INTO amc_portfolio_files
                    (amc, period, url, local_path, downloaded_at, file_size, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(amc, period, url) DO UPDATE SET
                    local_path    = COALESCE(excluded.local_path, amc_portfolio_files.local_path),
                    downloaded_at = excluded.downloaded_at,
                    file_size     = COALESCE(excluded.file_size, amc_portfolio_files.file_size),
                    status        = excluded.status
                """,
                (
                    item["amc"], item["period"], item["url"],
                    item.get("local_path"), now_iso, item.get("file_size"),
                    item["status"],
                ),
            )
            rows_written += max(self.conn.total_changes - before, 1)

        self.conn.commit()
        return rows_written

    def run(self):
        result = super().run()
        if self.skip_notes:
            result.extra["skip_notes"] = self.skip_notes
        return result
