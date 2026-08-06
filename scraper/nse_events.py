"""NSE corporate-events / results feeds.

Authoritative data straight from nseindia.com to complement the LLM web-search
discovery in the quarterly-results strategy:

* :func:`recent_declared_results` — companies that have ACTUALLY filed quarterly
  results recently (from the corporates-financial-results feed). This is the
  "assured, just declared" source the strategy verifies on screener.in.
* :func:`upcoming_result_declarations` — companies with board meetings SCHEDULED
  to declare results (from the corporate-filing events calendar). Forward-looking
  watch list; results aren't out yet.

NSE's JSON APIs require browser-like headers and a cookie bootstrap, so all
access goes through a shared, self-bootstrapping session. Every function
degrades gracefully (returns ``[]``) on any network/parse failure so the caller
can fall back to web search / watchlist.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

logger = logging.getLogger("scraper.nse_events")

_BASE = "https://www.nseindia.com"
_CALENDAR_PAGE = f"{_BASE}/companies-listing/corporate-filing-events-calendar"
_EVENT_CALENDAR_API = f"{_BASE}/api/event-calendar"
_FINANCIAL_RESULTS_API = f"{_BASE}/api/corporates-financial-results"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": _CALENDAR_PAGE,
}

_session: Optional[requests.Session] = None
_bootstrapped_at: float = 0.0
_BOOTSTRAP_TTL = 600.0  # re-bootstrap cookies every 10 minutes


def _get_session() -> requests.Session:
    """Return a cookie-bootstrapped session (NSE rejects cookieless calls)."""
    global _session, _bootstrapped_at
    now = time.time()
    if _session is not None and (now - _bootstrapped_at) < _BOOTSTRAP_TTL:
        return _session

    sess = requests.Session()
    sess.headers.update(_HEADERS)
    try:
        sess.get(f"{_BASE}/", timeout=20)
        sess.get(_CALENDAR_PAGE, timeout=20)
        _bootstrapped_at = now
    except requests.RequestException as e:
        logger.warning("NSE cookie bootstrap failed: %s", e)
    _session = sess
    return sess


def _get_json(url: str, *, params: Optional[Dict[str, str]] = None, retries: int = 2) -> Optional[Any]:
    for attempt in range(retries + 1):
        sess = _get_session()
        try:
            resp = sess.get(url, params=params, timeout=25)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("NSE %s -> HTTP %s (attempt %d)", url, resp.status_code, attempt + 1)
        except (requests.RequestException, ValueError) as e:
            logger.warning("NSE request/parse error for %s: %s", url, e)
        # Force a fresh bootstrap before retrying.
        global _bootstrapped_at
        _bootstrapped_at = 0.0
        time.sleep(1.5 * (attempt + 1))
    return None


# ── date helpers ────────────────────────────────────────────────────────────
def _parse_nse_date(raw: Optional[str]) -> Optional[date]:
    """Parse NSE dates like '06-Jul-2026' or '25-Jun-2026 16:39:17'."""
    if not raw:
        return None
    token = str(raw).strip().split(" ")[0]
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def _is_results_purpose(text: str) -> bool:
    return "result" in (text or "").lower()


# ── public feeds ─────────────────────────────────────────────────────────────
def recent_declared_results(
    *,
    lookback_days: int = 2,
    as_of: Optional[date] = None,
    period: str = "Quarterly",
) -> List[Dict[str, Any]]:
    """Companies that FILED quarterly results within the lookback window.

    Returns a list of ``{symbol, company, result_date, relating_to, source}``,
    de-duplicated per symbol (keeping the latest broadcast).
    """
    as_of = as_of or date.today()
    start = as_of - timedelta(days=max(0, lookback_days - 1))

    data = _get_json(
        _FINANCIAL_RESULTS_API, params={"index": "equities", "period": period}
    )
    if not isinstance(data, list):
        logger.info("NSE financial-results feed unavailable; returning none.")
        return []

    by_symbol: Dict[str, Dict[str, Any]] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        bcast = _parse_nse_date(row.get("broadCastDate") or row.get("filingDate"))
        if bcast is None or not (start <= bcast <= as_of):
            continue
        sym = str(row.get("symbol", "")).strip().upper()
        if not sym:
            continue
        prev = by_symbol.get(sym)
        if prev is None or bcast >= prev["_bcast"]:
            by_symbol[sym] = {
                "symbol": sym,
                "company": str(row.get("companyName", "")).strip(),
                "result_date": bcast.isoformat(),
                "relating_to": row.get("relatingTo", ""),
                "source": "nse_filings",
                "_bcast": bcast,
            }

    out = sorted(by_symbol.values(), key=lambda r: r["_bcast"], reverse=True)
    for r in out:
        r.pop("_bcast", None)
    logger.info("NSE: %d symbols with results filed in last %d day(s).", len(out), lookback_days)
    return out


# ── delta cache (fetch whole table once/day, act only on new filings) ────────
def _filing_key(row: Dict[str, Any]) -> Optional[str]:
    """Stable identity for a single filed result: symbol|relatingTo|resultDate."""
    sym = str(row.get("symbol", "")).strip().upper()
    if not sym:
        return None
    bcast = _parse_nse_date(row.get("broadCastDate") or row.get("filingDate"))
    relating = str(row.get("relatingTo", "")).strip()
    period = str(row.get("period", "")).strip()
    date_part = bcast.isoformat() if bcast else str(row.get("broadCastDate", "")).strip()
    return f"{sym}|{relating or period}|{date_part}"


def _load_seen(cache_path: Path) -> Dict[str, str]:
    try:
        raw = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        keys = raw.get("keys", {}) if isinstance(raw, dict) else {}
        return {str(k): str(v) for k, v in keys.items()} if isinstance(keys, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_seen(cache_path: Path, keys: Dict[str, str]) -> None:
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": datetime.now().isoformat(timespec="seconds"), "keys": keys}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def new_declared_results(
    *,
    cache_path: Union[str, Path],
    as_of: Optional[date] = None,
    period: str = "Quarterly",
    max_age_days: int = 7,
    prune_after_days: int = 400,
) -> List[Dict[str, Any]]:
    """Return only results filed since the last run (the daily *delta*).

    The full corporates-financial-results table (thousands of rows spanning ~a
    year) is fetched in a single request, then diffed against a persistent
    seen-cache keyed by ``symbol|relatingTo|resultDate`` so repeat runs act only
    on brand-new filings. This is far more robust than a fixed date-window: the
    seen-cache guarantees no filing is ever processed twice, correctly surfacing
    results filed after weekends, holidays, or missed runs.

    Returned filings are additionally bounded to the last ``max_age_days`` (new
    declarations are inherently recent). This keeps the delta immune to two NSE
    quirks: intermittent thin/partial API responses, and the feed carrying a
    full year of history — neither can ever flood the strategy with stale names.
    Every key in the current table is still absorbed into the cache regardless of
    age, so nothing is re-flagged later.

    Returns ``{symbol, company, result_date, relating_to, source}`` for each new
    filing (latest first). Degrades to ``[]`` on any NSE failure, leaving the
    cache untouched.
    """
    as_of = as_of or date.today()
    data = _get_json(
        _FINANCIAL_RESULTS_API, params={"index": "equities", "period": period}
    )
    if not isinstance(data, list):
        logger.info("NSE financial-results feed unavailable; delta returning none.")
        return []

    seen = _load_seen(cache_path)
    recent_cutoff = as_of - timedelta(days=max(0, max_age_days - 1))
    today_iso = as_of.isoformat()

    new_rows: Dict[str, Dict[str, Any]] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        key = _filing_key(row)
        if key is None:
            continue
        already = key in seen
        seen.setdefault(key, today_iso)  # always absorb into cache
        if already:
            continue
        bcast = _parse_nse_date(row.get("broadCastDate") or row.get("filingDate"))
        # Only surface genuinely recent, unseen filings; older ones just seed the cache.
        if bcast is None or bcast < recent_cutoff:
            continue
        sym = str(row.get("symbol", "")).strip().upper()
        prev = new_rows.get(sym)
        if prev is None or bcast >= prev["_bcast"]:
            new_rows[sym] = {
                "symbol": sym,
                "company": str(row.get("companyName", "")).strip(),
                "result_date": bcast.isoformat(),
                "relating_to": row.get("relatingTo", ""),
                "source": "nse_filings",
                "_bcast": bcast,
            }

    # Prune stale cache keys (embedded date older than the retention window).
    prune_before = as_of - timedelta(days=max(1, prune_after_days))
    kept: Dict[str, str] = {}
    for key, first_seen in seen.items():
        parsed = _parse_nse_date(key.rsplit("|", 1)[-1])
        if parsed is None or parsed >= prune_before:
            kept[key] = first_seen
    _save_seen(cache_path, kept)

    out = sorted(new_rows.values(), key=lambda r: r["_bcast"], reverse=True)
    for r in out:
        r.pop("_bcast", None)
    logger.info(
        "NSE delta: %d new filing(s) in last %d day(s) (cache now %d keys).",
        len(out), max_age_days, len(kept),
    )
    return out


# ── event-calendar declared source (fresh; financial-results feed lags) ───────
# The corporates-financial-results API is chronically stale/thin — it can sit
# days behind and even freeze a symbol's latest quarter (observed: GESHIP's most
# recent row stuck at Jan-2025 while its Jun-2026 result was already public).
# The event-calendar API, by contrast, carries every board meeting "to consider
# and approve" results, dated the day it happens, for the whole market — so a
# meeting whose date has already passed is an authoritative "just declared"
# signal. We therefore treat past-dated result board meetings as declared
# candidates (screener.in then verifies the actual numbers downstream).
_CAL_PREFIX = "CAL"


def recent_declared_from_calendar(
    *,
    lookback_days: int = 2,
    as_of: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Companies whose result board-meeting already occurred in the window.

    Sources the *fresh* event-calendar API (see note above) rather than the
    lagging financial-results feed. Returns ``{symbol, company, result_date,
    relating_to, source}`` for result-purpose events whose date is in
    ``[as_of - lookback_days + 1, as_of]`` (i.e. already happened), latest first.
    Degrades to ``[]`` on any NSE/parse failure.
    """
    as_of = as_of or date.today()
    start = as_of - timedelta(days=max(0, lookback_days - 1))
    by_symbol: Dict[str, Dict[str, Any]] = {}
    for c_start, c_end in _iter_month_ranges(start, as_of):
        data = _get_json(
            _EVENT_CALENDAR_API,
            params={
                "index": "equities",
                "from_date": c_start.strftime("%d-%m-%Y"),
                "to_date": c_end.strftime("%d-%m-%Y"),
            },
        )
        if not isinstance(data, list):
            continue
        for ev in data:
            if not isinstance(ev, dict):
                continue
            if not (
                _is_results_purpose(ev.get("purpose", ""))
                or _is_results_purpose(ev.get("bm_desc", ""))
            ):
                continue
            edate = _parse_nse_date(ev.get("date"))
            if edate is None or not (start <= edate <= as_of):
                continue
            sym = str(ev.get("symbol", "")).strip().upper()
            if not sym:
                continue
            prev = by_symbol.get(sym)
            if prev is None or edate >= prev["_edate"]:
                by_symbol[sym] = {
                    "symbol": sym,
                    "company": str(ev.get("company", "")).strip(),
                    "result_date": edate.isoformat(),
                    "relating_to": "",
                    "source": "nse_event_calendar",
                    "_edate": edate,
                }
    out = sorted(by_symbol.values(), key=lambda r: r["_edate"], reverse=True)
    for r in out:
        r.pop("_edate", None)
    logger.info(
        "NSE calendar: %d result-declarer(s) in last %d day(s).",
        len(out), lookback_days,
    )
    return out


def new_declared_from_calendar(
    *,
    cache_path: Union[str, Path],
    as_of: Optional[date] = None,
    max_age_days: int = 7,
    prune_after_days: int = 400,
) -> List[Dict[str, Any]]:
    """Event-calendar declared results filed since the last run (the daily delta).

    The calendar counterpart of :func:`new_declared_results`. Pulls recently
    *past* result board meetings from the fresh event-calendar and diffs them
    against the shared persistent seen-cache (keyed ``CAL|SYMBOL|<result_date>``
    so calendar keys never collide with financial-results keys and the existing
    date-suffix pruning still applies). Only brand-new declarers are surfaced;
    every current declarer is absorbed into the cache so nothing is re-flagged.
    Degrades to ``[]`` on any NSE failure, leaving the cache untouched.
    """
    as_of = as_of or date.today()
    declared = recent_declared_from_calendar(lookback_days=max_age_days, as_of=as_of)
    if not declared:
        return []

    seen = _load_seen(cache_path)
    today_iso = as_of.isoformat()
    out: List[Dict[str, Any]] = []
    for r in declared:
        key = f"{_CAL_PREFIX}|{r['symbol']}|{r['result_date']}"
        already = key in seen
        seen.setdefault(key, today_iso)  # always absorb into cache
        if not already:
            out.append(r)

    # Prune stale cache keys (trailing date older than the retention window).
    prune_before = as_of - timedelta(days=max(1, prune_after_days))
    kept: Dict[str, str] = {}
    for key, first_seen in seen.items():
        parsed = _parse_nse_date(key.rsplit("|", 1)[-1])
        if parsed is None or parsed >= prune_before:
            kept[key] = first_seen
    _save_seen(cache_path, kept)

    logger.info(
        "NSE calendar delta: %d new declarer(s) (cache now %d keys).",
        len(out), len(kept),
    )
    return out


def historical_result_dates(
    symbol: str,
    *,
    period: str = "Quarterly",
) -> Dict[date, date]:
    """Real quarterly-result *declaration* dates for a single symbol.

    Backfills the actual announcement calendar for backtesting: hits the
    per-symbol corporates-financial-results feed (full history, back to the
    company's listing) and returns a mapping of

        ``quarter_end (month-end date)  ->  earliest broadcast date``.

    NSE returns two rows per quarter (Consolidated + Standalone) — we keep the
    *earliest* ``broadCastDate`` for each quarter because that is the moment the
    market first learned the result. Quarter-ends are normalised to the last day
    of the ``toDate`` month so they line up with screener's quarter-column labels
    (which are always calendar quarter-ends).

    Degrades to ``{}`` on any NSE/parse failure so the caller can fall back to an
    estimated reporting lag.
    """
    sym = (symbol or "").strip().upper().replace(".NS", "").replace(".BO", "")
    if not sym:
        return {}

    data = _get_json(
        _FINANCIAL_RESULTS_API,
        params={"index": "equities", "symbol": sym, "period": period},
    )
    if not isinstance(data, list):
        logger.info("NSE per-symbol results feed unavailable for %s.", sym)
        return {}

    out: Dict[date, date] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        qend = _month_end(_parse_nse_date(row.get("toDate")))
        bcast = _parse_nse_date(row.get("broadCastDate") or row.get("filingDate"))
        if qend is None or bcast is None:
            continue
        prev = out.get(qend)
        if prev is None or bcast < prev:
            out[qend] = bcast

    logger.info("NSE: %d historical result date(s) for %s.", len(out), sym)
    return out


def _month_end(d: Optional[date]) -> Optional[date]:
    """Normalise a date to the last day of its month (align to quarter-ends)."""
    if d is None:
        return None
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _quarter_end_from_desc(desc: str) -> Optional[date]:
    """Parse the quarter-end from a board-meeting description.

    NSE ``bm_desc`` reads e.g. "...financial results for the period ended
    Jun 30, 2026" — we pull the "Mon DD, YYYY" and normalise to its month-end so
    it lines up with screener's calendar quarter-end labels.
    """
    m = re.search(r"ended\s+([A-Za-z]{3})[a-z]*\.?\s+\d{1,2},?\s+(\d{4})", desc or "", re.I)
    if not m:
        return None
    mon = _MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    return _month_end(date(int(m.group(2)), mon, 1))


def _infer_quarter_end(edate: date) -> Optional[date]:
    """Fallback: infer the reported quarter-end from the announcement month.

    Indian quarterly results are declared ~1-2 months after quarter-end:
    Jul-Sep → Jun, Oct-Dec → Sep, Jan-Mar → Dec, Apr-Jun → Mar (prev cal-year for
    the Dec quarter announced Jan-Mar).
    """
    m, y = edate.month, edate.year
    if 7 <= m <= 9:
        return _month_end(date(y, 6, 1))
    if 10 <= m <= 12:
        return _month_end(date(y, 9, 1))
    if 1 <= m <= 3:
        return _month_end(date(y - 1, 12, 1))
    return _month_end(date(y, 3, 1))  # Apr-Jun → Mar of the same year


def _iter_month_ranges(start: date, end: date):
    cur = start
    while cur <= end:
        nxt = date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
        yield cur, min(nxt - timedelta(days=1), end)
        cur = nxt


def results_event_calendar(
    start: date,
    end: date,
    *,
    only_results: bool = True,
) -> Dict[str, Dict[date, date]]:
    """Bulk REAL result-declaration dates from NSE's corporate event calendar.

    Hits ``/api/event-calendar`` over ``[start, end]`` (chunked by month to dodge
    range caps) and returns ``{symbol -> {quarter_end (month-end) -> earliest
    board-meeting date}}`` — the same shape as :func:`historical_result_dates`,
    so it is a drop-in real-date source for the backtest. This is one call per
    month for the WHOLE market, vs one call per symbol, so it is far cheaper and
    also serves fresher quarters than the per-symbol financial-results archive.

    The quarter-end is parsed from the board-meeting description ("period ended
    <Mon DD, YYYY>"); if that is missing it is inferred from the announcement
    month. Degrades to ``{}`` on any NSE/parse failure.
    """
    out: Dict[str, Dict[date, date]] = {}
    for c_start, c_end in _iter_month_ranges(start, end):
        params = {
            "index": "equities",
            "from_date": c_start.strftime("%d-%m-%Y"),
            "to_date": c_end.strftime("%d-%m-%Y"),
        }
        data = _get_json(_EVENT_CALENDAR_API, params=params)
        if not isinstance(data, list):
            logger.warning("Event calendar unavailable for %s..%s.", params["from_date"], params["to_date"])
            continue
        for ev in data:
            if not isinstance(ev, dict):
                continue
            purpose = ev.get("purpose", "")
            bm = ev.get("bm_desc", "")
            if only_results and not (_is_results_purpose(purpose) or _is_results_purpose(bm)):
                continue
            edate = _parse_nse_date(ev.get("date"))
            if edate is None:
                continue
            sym = str(ev.get("symbol", "")).strip().upper()
            if not sym:
                continue
            qend = _quarter_end_from_desc(bm) or _infer_quarter_end(edate)
            if qend is None:
                continue
            bucket = out.setdefault(sym, {})
            prev = bucket.get(qend)
            if prev is None or edate < prev:
                bucket[qend] = edate  # earliest announcement for the quarter
    logger.info(
        "NSE event calendar: %d symbols with result dates over %s..%s.",
        len(out), start.isoformat(), end.isoformat(),
    )
    return out


def upcoming_result_declarations(
    *,
    days_ahead: int = 14,
    as_of: Optional[date] = None,
    include_past_days: int = 1,
) -> List[Dict[str, Any]]:
    """Companies with board meetings SCHEDULED to declare results.

    Returns ``{symbol, company, event_date, purpose, source}`` for events whose
    purpose mentions results and whose date falls in
    ``[as_of - include_past_days, as_of + days_ahead]``.
    """
    as_of = as_of or date.today()
    start = as_of - timedelta(days=max(0, include_past_days))
    end = as_of + timedelta(days=max(0, days_ahead))

    data = _get_json(_EVENT_CALENDAR_API)
    if not isinstance(data, list):
        logger.info("NSE event calendar unavailable; returning none.")
        return []

    out: List[Dict[str, Any]] = []
    for ev in data:
        if not isinstance(ev, dict):
            continue
        purpose = ev.get("purpose", "")
        if not (_is_results_purpose(purpose) or _is_results_purpose(ev.get("bm_desc", ""))):
            continue
        edate = _parse_nse_date(ev.get("date"))
        if edate is None or not (start <= edate <= end):
            continue
        sym = str(ev.get("symbol", "")).strip().upper()
        if not sym:
            continue
        out.append({
            "symbol": sym,
            "company": str(ev.get("company", "")).strip(),
            "event_date": edate.isoformat(),
            "purpose": purpose,
            "source": "nse_event_calendar",
        })

    out.sort(key=lambda r: r["event_date"])
    logger.info("NSE: %d upcoming result declarations in next %d day(s).", len(out), days_ahead)
    return out
