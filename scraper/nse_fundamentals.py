"""Historical quarterly results straight from NSE's own filings.

Why this exists
---------------
screener.in only exposes the last ~13 quarters, which caps any backtest at
roughly 2.5 years. NSE publishes every filed quarterly result going back to
2012, and serves it in two different shapes:

* **XBRL era** (~2019 onward) — a tagged ``*_WEB.xml`` document.
* **HTML era** (2012 to ~2019) — a ``financial_res_*.html`` detail page.

Both are reachable from the same index feed, so this module fetches the index
once per window and dispatches to the right parser per filing.

Two properties make this better than a commercial aggregator rather than merely
cheaper:

* It is **as-filed**, so it is genuinely point-in-time. Vendors silently
  backfill restatements, which is lookahead bias in a long backtest.
* Every row carries the **exact broadcast timestamp**, replacing the estimated
  announcement lags the backtest currently falls back on.

Units
-----
Everything is normalised to **crores** to match the screener.in cache, so the
two sources can be compared and used interchangeably. Per-share figures (EPS)
are never scaled.
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("scraper.nse_fundamentals")

_BASE = "https://www.nseindia.com"
_RESULTS_PAGE = f"{_BASE}/companies-listing/corporate-filings-financial-results"
_RESULTS_API = f"{_BASE}/api/corporates-financial-results"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": _RESULTS_PAGE,
}

# NSE rejects cookieless calls; re-bootstrap periodically.
_session: Optional[requests.Session] = None
_bootstrapped_at: float = 0.0
_BOOTSTRAP_TTL = 600.0

# Measured at ~14 req/s unthrottled with no blocking. We deliberately run far
# below that: a historical backfill is a one-off, so politeness costs us hours
# we do not care about and buys goodwill we do.
MIN_REQUEST_INTERVAL = 0.35
_last_request_at: float = 0.0

CRORE = 1e7          # XBRL reports absolute rupees
LAKH_PER_CRORE = 100.0  # HTML era reports lakhs


# ── session ─────────────────────────────────────────────────────────────────
def get_session() -> requests.Session:
    """Return a cookie-bootstrapped NSE session."""
    global _session, _bootstrapped_at
    now = time.time()
    if _session is not None and (now - _bootstrapped_at) < _BOOTSTRAP_TTL:
        return _session

    sess = requests.Session()
    sess.headers.update(_HEADERS)
    try:
        sess.get(f"{_BASE}/", timeout=20)
        sess.get(_RESULTS_PAGE, timeout=20)
        _bootstrapped_at = now
    except requests.RequestException as e:
        logger.warning("NSE cookie bootstrap failed: %s", e)
    _session = sess
    return sess


def _throttled_get(url: str, *, retries: int = 2, timeout: int = 30):
    """GET with a global rate limit and one forced re-bootstrap on failure."""
    global _last_request_at, _bootstrapped_at
    for attempt in range(retries + 1):
        wait = MIN_REQUEST_INTERVAL - (time.time() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        sess = get_session()
        try:
            _last_request_at = time.time()
            resp = sess.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp
            # 404 means the archive link is stale (renamed/delisted issuer).
            # Retrying will not help, so surface it immediately.
            if resp.status_code == 404:
                return None
            logger.debug("NSE %s -> HTTP %s", url, resp.status_code)
        except requests.RequestException as e:
            logger.debug("NSE request error %s: %s", url, e)
        _bootstrapped_at = 0.0
        time.sleep(1.0 * (attempt + 1))
    return None


# ── model ───────────────────────────────────────────────────────────────────
@dataclass
class QuarterlyResult:
    """One filed quarterly result, normalised to crores."""

    symbol: str
    isin: str = ""
    company: str = ""
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    relating_to: str = ""
    consolidated: bool = False
    audited: str = ""
    broadcast_at: Optional[datetime] = None
    sales: Optional[float] = None
    other_income: Optional[float] = None
    expenses: Optional[float] = None
    depreciation: Optional[float] = None
    finance_costs: Optional[float] = None
    operating_profit: Optional[float] = None
    bank_operating_profit: Optional[float] = None
    profit_before_tax: Optional[float] = None
    tax_expense: Optional[float] = None
    net_profit: Optional[float] = None
    eps: Optional[float] = None
    source: str = ""
    url: str = ""

    @property
    def is_bank(self) -> bool:
        """True when the issuer filed the bank/NBFC schedule."""
        return self.bank_operating_profit is not None

    @property
    def opm(self) -> Optional[float]:
        """Operating margin %, on the same base screener.in uses (sales)."""
        if self.operating_profit is None or not self.sales:
            return None
        return 100.0 * self.operating_profit / self.sales

    @property
    def quarter_label(self) -> Optional[str]:
        """screener.in-style label, e.g. ``Mar 2024``, for joining to its cache."""
        if self.period_end is None:
            return None
        return self.period_end.strftime("%b %Y")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["opm"] = self.opm
        d["is_bank"] = self.is_bank
        d["quarter_label"] = self.quarter_label
        return d


# ── date / number helpers ───────────────────────────────────────────────────
def parse_nse_date(raw: Optional[str]) -> Optional[date]:
    """Parse '01-Oct-2013' / '30-Mar-2024 12:46:07' / '2020-10-01'."""
    if not raw:
        return None
    token = str(raw).strip().split(" ")[0]
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def parse_nse_datetime(raw: Optional[str]) -> Optional[datetime]:
    """Parse the full broadcast timestamp, falling back to midnight."""
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    d = parse_nse_date(text)
    return datetime(d.year, d.month, d.day) if d else None


def _to_float(raw: Any) -> Optional[float]:
    """Parse a filing number. Handles commas, blanks and (1,234) negatives."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text in {"-", "--", "NA", "N.A.", "nil", "Nil"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "").replace("\u20b9", "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


# ── index feed ──────────────────────────────────────────────────────────────
def list_filings(
    from_date: date, to_date: date, *, period: str = "Quarterly"
) -> List[Dict[str, Any]]:
    """Every result filed in ``[from_date, to_date]`` (raw index rows).

    The window is bounded by NSE, not by us — very wide ranges are served but
    slowly, so callers should page by quarter.
    """
    url = (
        f"{_RESULTS_API}?index=equities"
        f"&from_date={from_date.strftime('%d-%m-%Y')}"
        f"&to_date={to_date.strftime('%d-%m-%Y')}"
        f"&period={period}"
    )
    resp = _throttled_get(url, timeout=60)
    if resp is None:
        logger.warning("NSE index fetch failed for %s..%s", from_date, to_date)
        return []
    try:
        data = resp.json()
    except ValueError:
        logger.warning("NSE index returned non-JSON for %s..%s", from_date, to_date)
        return []
    rows = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
    logger.info("NSE index %s..%s -> %d filings.", from_date, to_date, len(rows))
    return rows


# ── XBRL era ────────────────────────────────────────────────────────────────
# Tag -> field. Indian filings vary the tag for the same concept, so each field
# lists its aliases in priority order.
_XBRL_FIELDS: Dict[str, Tuple[str, ...]] = {
    # Banks/NBFCs file the banking taxonomy, whose comparable top line is
    # ``Income`` (interest earned + other income). It is listed last so a
    # corporate filing never prefers it.
    "sales": (
        "RevenueFromOperations",
        "Revenue",
        "TotalRevenueFromOperations",
        "Income",
    ),
    "other_income": ("OtherIncome",),
    "expenses": (
        "Expenses",
        "TotalExpenses",
        "ExpenditureExcludingProvisionsAndContingencies",
    ),
    "depreciation": (
        "DepreciationDepletionAndAmortisationExpense",
        "DepreciationAndAmortisationExpense",
    ),
    "finance_costs": ("FinanceCosts", "InterestExpended"),
    # Bank/NBFC schedule only. Kept separate so the corporate EBITDA add-back
    # never fires on a filing where interest expense *is* an operating cost.
    "bank_operating_profit": ("OperatingProfitBeforeProvisionAndContingencies",),
    "profit_before_tax": (
        "ProfitBeforeTax",
        "ProfitLossBeforeTax",
        "ProfitBeforeExceptionalItemsAndTax",
        "ProfitLossFromOrdinaryActivitiesBeforeTax",
    ),
    "tax_expense": ("TaxExpense", "IncomeTaxExpense", "TotalTaxExpense"),
    "net_profit": (
        "ProfitLossForPeriod",
        "ProfitLossForThePeriod",
        "NetProfitLossForThePeriod",
        "ProfitLossFromOrdinaryActivitiesAfterTax",
    ),
    "eps": (
        "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
        "BasicEarningsLossPerShareFromContinuingOperations",
        "BasicEarningsLossPerShare",
        "BasicEarningsPerShareAfterExtraordinaryItems",
        "BasicEarningsPerShareBeforeExtraordinaryItems",
    ),
}

_UNSCALED = {"eps"}

# NSE ships facts that reference contexts it never declares (``OneD`` and
# friends appear only as contextRef values). Those ids follow the Ind-AS
# taxonomy convention, so when date matching finds nothing we fall back to it:
#   OneD   current 3 months        FourD  year to date
#   TwoD   preceding 3 months      FiveD  prior year to date
#   ThreeD same quarter last year  SixD   previous full year
# Only the current quarter is ever what we want.
_QUARTER_CONTEXT = "OneD"

# Never fall back to one of these: they hold cumulative figures that would
# masquerade as a quarter.
_CUMULATIVE_CONTEXTS = {"FourD", "FiveD", "SixD"}


def _xbrl_duration_contexts(root: ET.Element) -> Dict[str, Tuple[str, str]]:
    """Map context id -> (startDate, endDate) for plain duration contexts.

    Contexts carrying a ``segment``/``scenario`` are dimensional breakdowns
    (per-product, per-segment). Including them would let a segment's revenue
    masquerade as the company total, so they are skipped.
    """
    out: Dict[str, Tuple[str, str]] = {}
    for ctx in root.iter():
        if ctx.tag.split("}")[-1] != "context":
            continue
        cid = ctx.get("id")
        if not cid:
            continue
        start = end = None
        dimensional = False
        for node in ctx.iter():
            tag = node.tag.split("}")[-1]
            if tag == "startDate":
                start = (node.text or "").strip()
            elif tag == "endDate":
                end = (node.text or "").strip()
            elif tag in ("segment", "scenario"):
                dimensional = True
        if start and end and not dimensional:
            out[cid] = (start, end)
    return out


def _pick_context(
    contexts: Dict[str, Tuple[str, str]],
    period_start: Optional[date],
    period_end: Optional[date],
) -> Optional[str]:
    """Choose the context matching the filing's own reporting quarter.

    A filing restates the same tags for the quarter, the year-to-date, and the
    prior year, so picking the first occurrence silently mixes a 3-month figure
    with a 9-month one. We match on the exact period, then fall back to the
    shortest duration ending on the period end.
    """
    if period_end is None:
        return None
    exact, ending = [], []
    for cid, (start_s, end_s) in contexts.items():
        start, end = parse_nse_date(start_s), parse_nse_date(end_s)
        if end != period_end:
            continue
        if period_start is not None and start == period_start:
            exact.append(cid)
        if start is not None:
            ending.append(((end - start).days, cid))
    if exact:
        return sorted(exact)[0]
    if ending:
        return sorted(ending)[0][1]
    return None


def parse_xbrl(
    content: bytes,
    *,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> Dict[str, Optional[float]]:
    """Extract the fields we need from one XBRL filing, in crores."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        logger.debug("XBRL parse error: %s", e)
        return {}

    contexts = _xbrl_duration_contexts(root)
    dated_ctx = _pick_context(contexts, period_start, period_end)
    # Convention first, dates second. NSE routinely declares ``FourD`` (the
    # year-to-date context) with the *quarter's* start/end dates while filling
    # it with the cumulative figure, so both contexts claim the same period and
    # date matching cannot separate them. The context id is the reliable signal;
    # date matching only helps on the rare filing that omits ``OneD``.
    candidates = [_QUARTER_CONTEXT]
    if dated_ctx and dated_ctx not in candidates:
        candidates.append(dated_ctx)

    # tag -> {context: value}
    facts: Dict[str, Dict[str, float]] = {}
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        ref = node.get("contextRef")
        if not ref or node.text is None:
            continue
        value = _to_float(node.text)
        if value is None:
            continue
        facts.setdefault(tag, {})[ref] = value

    out: Dict[str, Optional[float]] = {}
    for field_name, aliases in _XBRL_FIELDS.items():
        value = None
        for alias in aliases:
            by_ctx = facts.get(alias)
            if not by_ctx:
                continue
            for candidate in candidates:
                if candidate in by_ctx:
                    value = by_ctx[candidate]
                    break
            if value is None and len(by_ctx) == 1:
                only_ctx, only_value = next(iter(by_ctx.items()))
                # Unambiguous only if that lone context is not a cumulative one.
                if only_ctx not in _CUMULATIVE_CONTEXTS:
                    value = only_value
            if value is not None:
                break
        if value is not None and field_name not in _UNSCALED:
            value /= CRORE
        out[field_name] = value
    return out


# ── HTML era ────────────────────────────────────────────────────────────────
# Label -> field. Labels drift across the pre-Ind-AS / Ind-AS boundary, so each
# field lists the variants seen, matched as normalised substrings.
_HTML_FIELDS: Dict[str, Tuple[str, ...]] = {
    "sales": (
        "net sales/income from operations net of excise duty",
        "net sales/income from operations",
        "revenue from operations net",
        "revenue from operations",
        "income from operations",
        # Banks and NBFCs file a different schedule with no "sales" line; the
        # comparable top line is total income (interest earned + other income),
        # which is what screener reports as their revenue.
        "total income",
    ),
    "other_income": ("other income",),
    "expenses": ("total expenses", "total expenditure"),
    "depreciation": (
        "depreciation and amortisation expense",
        "depreciation & amortisation expense",
        "depreciation",
    ),
    "finance_costs": ("finance costs", "interest expended", "interest"),
    "operating_profit": (
        "profit / loss from operations before other income, finance costs "
        "and exceptional items",
        "profit from operations before other income, finance costs and "
        "exceptional items",
    ),
    "bank_operating_profit": (
        "operating profit before provisions and contingencies",
    ),
    "profit_before_tax": (
        "profit / loss from ordinary activities before tax",
        "profit / loss before tax",
        "profit before tax",
    ),
    "tax_expense": ("tax expense",),
    "net_profit": (
        "net profit / loss after taxes, minority interest and share of "
        "profit / loss of associates",
        "net profit / loss for the period",
        "net profit / loss from ordinary activities after tax",
    ),
    "eps": (
        "basic eps before extraordinary items in rs.",
        "basic eps after extraordinary items in rs.",
        "basic eps",
        "basic",
    ),
}


def _normalise_label(text: str) -> str:
    """Canonicalise a row label so punctuation drift stops breaking matches.

    Pre-Ind-AS filings write ``Net Profit(+) / Loss(-)`` where later ones write
    ``Net Profit / (Loss)``. Dropping sign markers and brackets collapses both
    onto one key.
    """
    text = re.sub(r"^\s*\(?[a-z0-9]{1,3}\)?[.)]\s+", "", text.strip().lower())
    text = text.replace("(+)", " ").replace("(-)", " ")
    text = re.sub(r"[()\[\]]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" :.")


# Match against the same canonical form as the scraped rows.
_HTML_FIELDS = {
    field: tuple(_normalise_label(label) for label in labels)
    for field, labels in _HTML_FIELDS.items()
}

# Mangled header rows flatten a whole table into one cell; a real line item is
# never this long.
_MAX_LABEL_LEN = 120


def _html_rows(soup: BeautifulSoup) -> List[Tuple[str, Optional[float]]]:
    """Flatten the detail table into (label, first numeric cell) pairs."""
    rows: List[Tuple[str, Optional[float]]] = []
    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) < 2:
            continue
        label = _normalise_label(cells[0])
        if not label or len(label) > _MAX_LABEL_LEN:
            continue
        value = None
        for cell in cells[1:]:
            value = _to_float(cell)
            if value is not None:
                break
        rows.append((label, value))
    return rows


def _detect_html_unit(text: str) -> float:
    """Divisor that converts the page's stated unit into crores."""
    lowered = text.lower()
    if "rs. in lakhs" in lowered or "rs. in lakh" in lowered:
        return LAKH_PER_CRORE
    if "rs. in crore" in lowered:
        return 1.0
    if "rs. in million" in lowered:
        return 10.0
    # NSE's own template is lakhs; assume it rather than silently mis-scaling.
    return LAKH_PER_CRORE


def parse_html(content: str) -> Dict[str, Optional[float]]:
    """Extract the fields we need from one pre-2019 detail page, in crores."""
    soup = BeautifulSoup(content, "html.parser")
    divisor = _detect_html_unit(soup.get_text(" ", strip=True)[:4000])
    rows = [(label, cell) for label, cell in _html_rows(soup) if cell is not None]

    out: Dict[str, Optional[float]] = {}
    for field_name, labels in _HTML_FIELDS.items():
        value = None
        # Exact match first across every alias, so a loose prefix alias never
        # shadows an exact hit from a later alias.
        for exact in (True, False):
            for wanted in labels:
                for label, cell in rows:
                    if label == wanted if exact else label.startswith(wanted):
                        value = cell
                        break
                if value is not None:
                    break
            if value is not None:
                break
        if value is not None and field_name not in _UNSCALED:
            value /= divisor
        out[field_name] = value
    return out


# ── fetch + assemble ────────────────────────────────────────────────────────
def _looks_like_xbrl(url: str) -> bool:
    return url.lower().endswith(".xml")


def result_from_row(row: Dict[str, Any]) -> Optional[QuarterlyResult]:
    """Build an empty result carrying only the index row's metadata."""
    symbol = str(row.get("symbol", "")).strip().upper()
    if not symbol:
        return None
    return QuarterlyResult(
        symbol=symbol,
        isin=str(row.get("isin", "") or "").strip(),
        company=str(row.get("companyName", "") or "").strip(),
        period_start=parse_nse_date(row.get("fromDate")),
        period_end=parse_nse_date(row.get("toDate")),
        relating_to=str(row.get("relatingTo", "") or "").strip(),
        consolidated=str(row.get("consolidated", "")).strip().lower()
        == "consolidated",
        audited=str(row.get("audited", "") or "").strip(),
        broadcast_at=parse_nse_datetime(
            row.get("broadCastDate") or row.get("filingDate")
        ),
    )


def derive_operating_profit(result: QuarterlyResult) -> QuarterlyResult:
    """Restate operating profit as EBITDA, in place.

    Screener-comparable operating profit excludes depreciation and finance
    costs. Both filing formats bundle them in (XBRL ``Expenses``, and the HTML
    "before other income, finance costs" line is still *after* depreciation),
    so they are added back explicitly.
    """
    if result.is_bank:
        # Interest expense is an operating cost for a bank, so no add-back —
        # take the figure the banking schedule states directly.
        result.operating_profit = result.bank_operating_profit
    elif result.sales is not None and result.expenses is not None:
        addback = (result.depreciation or 0.0) + (result.finance_costs or 0.0)
        result.operating_profit = result.sales - result.expenses + addback
    elif result.operating_profit is not None and result.depreciation is not None:
        result.operating_profit += result.depreciation
    return result


def fetch_result(row: Dict[str, Any]) -> Optional[QuarterlyResult]:
    """Fetch and parse one index row into a normalised result.

    Returns ``None`` when neither channel yields usable numbers, which happens
    for stale archive links belonging to renamed or delisted issuers.
    """
    result = result_from_row(row)
    if result is None:
        return None

    xbrl_url = str(row.get("xbrl", "") or "").strip()
    detail_url = str(row.get("resultDetailedDataLink", "") or "").strip()
    if detail_url.startswith("/"):
        detail_url = _BASE + detail_url

    # Prefer XBRL: it is tagged, so it needs no label heuristics.
    attempts: List[Tuple[str, str]] = []
    if xbrl_url and _looks_like_xbrl(xbrl_url):
        attempts.append(("xbrl", xbrl_url))
    if detail_url:
        attempts.append(("html", detail_url))

    for source, url in attempts:
        resp = _throttled_get(url)
        if resp is None:
            continue
        if source == "xbrl":
            values = parse_xbrl(
                resp.content,
                period_start=result.period_start,
                period_end=result.period_end,
            )
        else:
            values = parse_html(resp.text)
        if not any(v is not None for v in values.values()):
            continue
        for key, value in values.items():
            setattr(result, key, value)
        result.source = source
        result.url = url
        break
    else:
        return None

    return derive_operating_profit(result)


def _preference(result: QuarterlyResult) -> Tuple[int, int]:
    """Rank duplicate filings: consolidated first, then the richest record."""
    filled = sum(
        1
        for v in (
            result.sales,
            result.net_profit,
            result.eps,
            result.operating_profit,
        )
        if v is not None
    )
    return (1 if result.consolidated else 0, filled)


def select_best(
    results: Iterable[QuarterlyResult],
) -> Dict[Tuple[str, str], QuarterlyResult]:
    """Collapse to one result per (symbol, quarter).

    Companies file both consolidated and standalone, and sometimes refile. We
    keep consolidated where present — matching screener.in's own default — and
    otherwise the most complete record.
    """
    best: Dict[Tuple[str, str], QuarterlyResult] = {}
    for result in results:
        label = result.quarter_label
        if not label:
            continue
        key = (result.symbol, label)
        current = best.get(key)
        if current is None or _preference(result) > _preference(current):
            best[key] = result
    return best


def collect_quarter(
    from_date: date,
    to_date: date,
    *,
    symbols: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> List[QuarterlyResult]:
    """Fetch and parse every filing in a window, optionally limited to symbols."""
    wanted = {s.strip().upper() for s in symbols} if symbols else None
    rows = list_filings(from_date, to_date)
    if wanted:
        rows = [
            r for r in rows
            if str(r.get("symbol", "")).strip().upper() in wanted
        ]
    if limit is not None:
        rows = rows[:limit]

    out: List[QuarterlyResult] = []
    misses = 0
    for i, row in enumerate(rows, start=1):
        parsed = fetch_result(row)
        if parsed is None:
            misses += 1
        else:
            out.append(parsed)
        if i % 100 == 0:
            logger.info("  parsed %d/%d (%d unusable)", i, len(rows), misses)
    logger.info(
        "Window %s..%s: %d parsed, %d unusable of %d filings.",
        from_date, to_date, len(out), misses, len(rows),
    )
    return out
