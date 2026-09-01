"""Corporate actions, and the price-adjustment factors derived from them.

:mod:`scraper.bhavcopy` gives raw, as-traded prices. That is the right thing to
store — it is what the tape actually said — but it is the wrong thing to
compute returns from. NSE does not adjust the archive: on HDFCBANK's 1:2 split
the bhavcopy shows ``prev_close = 2187.75`` against ``close = 1101.05``, and
``PREVCLOSE`` is *not* restated either, so a naive return chain books -49.7% on
a day the holder lost nothing. Over thirteen years and a few hundred names,
that is hundreds of fabricated catastrophes.

This module closes that gap from NSE's own corporate-actions feed
(``/api/corporates-corporateActions``), which carries an ex-date and a
free-text
``subject`` per event. The subject is the only place the ratio lives, so it is
parsed here into a numeric factor:

===========================================  ==================  ============
subject                                      meaning             factor
===========================================  ==================  ============
``Face Value Split From Rs 10 To Rs 2``      5-for-1 split       0.2
``Bonus 1:1``                                1 free per 1 held   0.5
``Bonus 1 : 1250``                           1 free per 1250     0.99920...
``Bonus 1:1 / Face Value Split ... To Rs 2`` both, compounded    0.1
===========================================  ==================  ============

The factor is what a *pre*-ex-date price must be multiplied by to be comparable
with post-ex-date prices. :func:`adjustment_series` accumulates it backwards so
any historical close can be restated onto today's share base in one multiply.

Dividends are never folded into the *price* factor: doing so would erase the
real ex-date drop, and because the strategy exits on an ATR trailing stop, a
series without that drop systematically flatters stop-based exits. Measured on
the 2014-2026 run, back-adjusted vendor data left 382 of 402 trades identical
and turned 20 genuine ``trailing_stop`` exits into later ``time_stop`` ones.

The correct treatment is to keep the drop on the tape and pay the cash
separately: :func:`load_dividends` returns per-symbol ex-date payouts that the
backtest engine credits to cash on the ex-date. Measured yield on deployed
capital over 2014-2026 is ~2.3-2.6%/yr (an earlier note in this file claimed
~1.3%/yr; that figure was wrong). Note the engine's NIFTY 50 benchmark is a
price index, so a dividend-credited equity curve is being compared against a
benchmark that excludes them -- the strategy is flattered by roughly the index
yield in that comparison, though not in its own absolute return.

    uv run python -m scraper.corporate_actions --from 2012-01-01   # backfill
    uv run python -m scraper.corporate_actions --status
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import requests

from core.storage import connect
from scraper import conn_cache

logger = logging.getLogger("scraper.corporate_actions")

_BASE = "https://www.nseindia.com"
_ACTIONS_PAGE = f"{_BASE}/companies-listing/corporate-filings-actions"
_ACTIONS_API = f"{_BASE}/api/corporates-corporateActions"

MIN_REQUEST_INTERVAL = 0.4

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": _ACTIONS_PAGE,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS corporate_actions (
    symbol      TEXT NOT NULL,
    ex_date     TEXT NOT NULL,
    subject     TEXT NOT NULL,
    isin        TEXT NOT NULL DEFAULT '',
    face_value  REAL,
    kind        TEXT NOT NULL DEFAULT '',
    factor      REAL,
    dividend    REAL,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (symbol, ex_date, subject)
);

CREATE INDEX IF NOT EXISTS idx_ca_symbol
    ON corporate_actions (symbol, ex_date);
CREATE INDEX IF NOT EXISTS idx_ca_kind   ON corporate_actions (kind);
CREATE INDEX IF NOT EXISTS idx_ca_isin   ON corporate_actions (isin, ex_date);

-- Windows already walked, so a resumed backfill is a no-op.
CREATE TABLE IF NOT EXISTS corporate_action_windows (
    from_date    TEXT NOT NULL,
    to_date      TEXT NOT NULL,
    rows         INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (from_date, to_date)
);

-- Symbols already swept one-by-one, so a resumed sweep is a no-op.
CREATE TABLE IF NOT EXISTS corporate_action_symbols (
    symbol       TEXT PRIMARY KEY,
    rows         INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT NOT NULL
);
"""


def open_store(db_path: Optional[Path] = None) -> sqlite3.Connection:
    connection = connect(db_path)
    connection.executescript(_SCHEMA)
    connection.commit()
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── parsing ──────────────────────────────────────────────────────────────────
# Face-value splits are written a dozen different ways in the live feed:
#   "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per"
#   "Face Value Split (Sub-Division) - From Rs 10 To Rs 2"
#   "Fv Splt Frm Rs 10 To Re 1"          (abbreviated)
#   "Face Value Split Rs.10/- To Re.1/-" (no "From" at all)
#   "Face Valus Split (Sub-Division) - From Rs 10/- Per To Rs 2/- Per Share"
# Rather than try to spell every variant, detect that the subject is about a
# face-value split and then take the first two rupee amounts in order. The
# unit is "Rs" or the singular "Re", optionally with a full stop, and the
# trailing "/-" is optional.
_SPLIT_CONTEXT_RE = re.compile(
    r"(?:face\s*val\w*\s*spl\w*|f\.?\s?v\.?\s*spl\w*|sub-?division)",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"r[se]\.?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_BARE_PAIR_RE = re.compile(
    r"fr?o?m\s+(\d+(?:\.\d+)?)\D{1,12}?to\s+(\d+(?:\.\d+)?)", re.IGNORECASE
)
# "Bonus 1:1", "Bonus- 1:2", "Bonus 1 : 1250", "Bonus Issue 3:5"
_BONUS_RE = re.compile(
    r"bonus\W*(?:issue\W*)?(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
# A "bonus" of debentures or preference shares hands the holder a *different*
# instrument. The equity share count is unchanged, so adjusting the equity
# price for it would invent a crash rather than remove one.
_NON_EQUITY_BONUS_RE = re.compile(
    r"debenture|ncrps|ncd|preference|warrant", re.IGNORECASE
)
# A demerger genuinely moves value out of the share into a separate listing.
# The ratio alone cannot restate it — that needs the child company's opening
# price — so these are recorded and flagged, never silently adjusted.
_DEMERGER_RE = re.compile(
    r"demerger|de-merger|scheme\s+of\s+arr?angement|spin-?off", re.IGNORECASE
)
# "Dividend - Rs 0.10 Per Share", "Dividend Re 0.50", "Dividend Rs.3/-"
_DIVIDEND_RE = re.compile(
    r"dividend[^0-9]{0,40}?(?:r[se])?\.?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def parse_split(subject: str) -> Optional[float]:
    """Factor for a face-value split, or None. 10 -> 2 gives 0.2."""
    text = subject or ""
    context = _SPLIT_CONTEXT_RE.search(text)
    if not context:
        return None
    # Only look at the text from the split phrase onwards. Subjects routinely
    # bundle a dividend first ("Dividend - Rs 10 Per Share/Face Value Split
    # From Rs 10 To Rs 2"), and reading the payout as the old face value would
    # invent an adjustment instead of removing one.
    tail = text[context.start():]
    amounts = [float(m) for m in _MONEY_RE.findall(tail)]
    if len(amounts) >= 2:
        old, new = amounts[0], amounts[1]
    else:
        match = _BARE_PAIR_RE.search(tail)
        if not match:
            return None
        old, new = float(match.group(1)), float(match.group(2))
    if old <= 0 or new <= 0 or old == new:
        return None
    return new / old


def parse_bonus(subject: str) -> Optional[float]:
    """Factor for a bonus issue of *equity*, or None.

    Indian notation ``a:b`` means *a* free shares for every *b* held, so the
    share count scales by ``(a + b) / b`` and the price by its reciprocal.
    Bonus debentures and bonus preference shares are deliberately ignored:
    they leave the equity share count untouched.
    """
    text = subject or ""
    if _NON_EQUITY_BONUS_RE.search(text):
        return None
    match = _BONUS_RE.search(text)
    if not match:
        return None
    new, held = float(match.group(1)), float(match.group(2))
    if new <= 0 or held <= 0:
        return None
    return held / (held + new)


def parse_dividend(subject: str) -> Optional[float]:
    """Rupees per share, or None. Not applied unless explicitly requested."""
    text = subject or ""
    if "dividend" not in text.lower():
        return None
    match = _DIVIDEND_RE.search(text)
    if not match:
        return None
    value = float(match.group(1))
    return value if value > 0 else None


def is_demerger(subject: str) -> bool:
    """Whether the subject describes value leaving into a separate listing."""
    return bool(_DEMERGER_RE.search(subject or ""))


def classify(subject: str) -> Tuple[str, Optional[float], Optional[float]]:
    """Return ``(kind, factor, dividend)`` for one corporate-action subject.

    A subject can carry a bonus *and* a split at once ("Bonus 1:1 / Face Value
    Split From Rs 10 To Rs 2"), in which case both apply and the factors
    compound.
    """
    split = parse_split(subject)
    bonus = parse_bonus(subject)
    dividend = parse_dividend(subject)
    kinds = []
    factor = None
    if split is not None:
        kinds.append("split")
        factor = split
    if bonus is not None:
        kinds.append("bonus")
        factor = bonus if factor is None else factor * bonus
    if dividend is not None:
        kinds.append("dividend")
    if is_demerger(subject) and factor is None:
        # Recorded so the backtest can refuse to chain a return across the
        # event, rather than booking the value that left as a loss.
        kinds.append("demerger")
    return ("+".join(kinds), factor, dividend)


def _parse_date(raw) -> Optional[date]:
    token = (str(raw) if raw is not None else "").strip()
    if not token:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def _num(raw) -> Optional[float]:
    token = (str(raw) if raw is not None else "").strip().replace(",", "")
    if not token or token in {"-", "NA"}:
        return None
    try:
        return float(token)
    except ValueError:
        return None


# ── fetching ─────────────────────────────────────────────────────────────────
_session: Optional[requests.Session] = None
_bootstrapped_at = 0.0
_last_request = 0.0


def get_session() -> requests.Session:
    global _session, _bootstrapped_at
    now = time.time()
    if _session is not None and (now - _bootstrapped_at) < 600.0:
        return _session
    sess = _session or requests.Session()
    sess.headers.update(_HEADERS)
    try:
        sess.get(f"{_BASE}/", timeout=20)
        sess.get(_ACTIONS_PAGE, timeout=20)
        _bootstrapped_at = now
    except requests.RequestException as exc:
        logger.warning("NSE cookie bootstrap failed: %s", exc)
    _session = sess
    return sess


def fetch_window(start: date, end: date, *, retries: int = 2) -> List[dict]:
    """Corporate actions announced with an ex-date inside the window."""
    global _last_request, _bootstrapped_at
    params = {
        "index": "equities",
        "from_date": start.strftime("%d-%m-%Y"),
        "to_date": end.strftime("%d-%m-%Y"),
    }
    for attempt in range(retries + 1):
        wait = MIN_REQUEST_INTERVAL - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()
        try:
            resp = get_session().get(_ACTIONS_API, params=params, timeout=40)
            if resp.status_code == 200:
                payload = resp.json()
                return payload if isinstance(payload, list) else []
        except (requests.RequestException, ValueError) as exc:
            logger.warning("corporate actions %s..%s: %s", start, end, exc)
        _bootstrapped_at = 0.0
        time.sleep(1.5 * (attempt + 1))
    return []


def fetch_symbol(
    symbol: str,
    start: date,
    end: date,
    *,
    retries: int = 2,
) -> List[dict]:
    """Every corporate action NSE holds for one ticker.

    The date-window sweep misses a great deal: NSE files an event under the
    company's *current* ticker, so a split that happened while the company
    traded as ITDCEM is only returned when you ask for CEMPRO. Sweeping ticker
    by ticker and matching on ISIN recovers those.
    """
    global _last_request, _bootstrapped_at
    params = {
        "index": "equities",
        "symbol": symbol,
        "from_date": start.strftime("%d-%m-%Y"),
        "to_date": end.strftime("%d-%m-%Y"),
    }
    for attempt in range(retries + 1):
        wait = MIN_REQUEST_INTERVAL - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()
        try:
            resp = get_session().get(_ACTIONS_API, params=params, timeout=40)
            if resp.status_code == 200:
                payload = resp.json()
                return payload if isinstance(payload, list) else []
        except (requests.RequestException, ValueError) as exc:
            logger.warning("corporate actions %s: %s", symbol, exc)
        _bootstrapped_at = 0.0
        time.sleep(1.5 * (attempt + 1))
    return []


def store_actions(connection: sqlite3.Connection, rows: Sequence[dict]) -> int:
    payload = []
    now = _now()
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        ex_date = _parse_date(row.get("exDate"))
        subject = (row.get("subject") or "").strip()
        if not symbol or ex_date is None or not subject:
            continue
        kind, factor, dividend = classify(subject)
        payload.append((
            symbol, ex_date.isoformat(), subject,
            (row.get("isin") or "").strip().upper(),
            _num(row.get("faceVal")), kind, factor, dividend, now,
        ))
    if not payload:
        return 0
    connection.executemany(
        "INSERT INTO corporate_actions (symbol, ex_date, subject, isin, "
        "face_value, kind, factor, dividend, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(symbol, ex_date, subject) DO UPDATE SET "
        "isin = excluded.isin, face_value = excluded.face_value, "
        "kind = excluded.kind, factor = excluded.factor, "
        "dividend = excluded.dividend, fetched_at = excluded.fetched_at",
        payload,
    )
    return len(payload)


def completed_windows(connection: sqlite3.Connection) -> set:
    return {
        (row[0], row[1])
        for row in connection.execute(
            "SELECT from_date, to_date FROM corporate_action_windows"
        )
    }


def monthly_windows(start: date, end: date) -> List[Tuple[date, date]]:
    """Month-sized windows.

    The API caps result counts, so small windows are safer.
    """
    out = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        if cursor.month == 12:
            nxt = date(cursor.year + 1, 1, 1)
        else:
            nxt = date(cursor.year, cursor.month + 1, 1)
        out.append((max(cursor, start), min(nxt - timedelta(days=1), end)))
        cursor = nxt
    return out


def run(
    start: date,
    end: date,
    *,
    connection: Optional[sqlite3.Connection] = None,
    resume: bool = True,
) -> dict:
    own = connection is None
    connection = connection or open_store()
    try:
        done = completed_windows(connection) if resume else set()
        windows = monthly_windows(start, end)
        pending = [
            w for w in windows
            if (w[0].isoformat(), w[1].isoformat()) not in done
        ]
        logger.info(
            "corporate actions: %d windows, %d done, %d to fetch.",
            len(windows), len(windows) - len(pending), len(pending),
        )
        total = 0
        for index, (win_start, win_end) in enumerate(pending, 1):
            rows = fetch_window(win_start, win_end)
            stored = store_actions(connection, rows)
            connection.execute(
                "INSERT INTO corporate_action_windows (from_date, to_date, "
                "rows, completed_at) VALUES (?,?,?,?) "
                "ON CONFLICT(from_date, to_date) DO UPDATE SET "
                "rows = excluded.rows, completed_at = excluded.completed_at",
                (win_start.isoformat(), win_end.isoformat(), stored, _now()),
            )
            connection.commit()
            total += stored
            if index % 12 == 0 or index == len(pending):
                logger.info(
                    "  %d/%d windows — %s (%d rows). %d stored.",
                    index, len(pending), win_start, stored, total,
                )
        return {"windows": len(pending), "rows": total}
    finally:
        if own:
            connection.close()


def sweep_symbols(
    symbols: Sequence[str],
    start: date,
    end: date,
    *,
    connection: Optional[sqlite3.Connection] = None,
    resume: bool = True,
) -> dict:
    """Walk tickers one at a time, recovering events the window sweep missed.

    NSE files a corporate action under whatever ticker the company trades
    under *today*, not the one it traded under on the ex-date. A ticker-by-
    ticker sweep, matched back to history through ISIN, is the only way to see
    the split that CROMPGREAV took in 2016 — NSE will only show it for
    CGPOWER.
    """
    own = connection is None
    connection = connection or open_store()
    try:
        done = set()
        if resume:
            done = {
                row[0]
                for row in connection.execute(
                    "SELECT symbol FROM corporate_action_symbols"
                )
            }
        pending = [s for s in symbols if s not in done]
        logger.info(
            "corporate actions sweep: %d symbols, %d done, %d to fetch.",
            len(symbols), len(symbols) - len(pending), len(pending),
        )
        total = 0
        for index, symbol in enumerate(pending, 1):
            rows = fetch_symbol(symbol, start, end)
            stored = store_actions(connection, rows)
            connection.execute(
                "INSERT INTO corporate_action_symbols (symbol, rows, "
                "completed_at) VALUES (?,?,?) "
                "ON CONFLICT(symbol) DO UPDATE SET rows = excluded.rows, "
                "completed_at = excluded.completed_at",
                (symbol, stored, _now()),
            )
            connection.commit()
            total += stored
            if index % 100 == 0 or index == len(pending):
                logger.info(
                    "  %d/%d symbols — %s (%d rows). %d stored.",
                    index, len(pending), symbol, stored, total,
                )
        return {"symbols": len(pending), "rows": total}
    finally:
        if own:
            connection.close()


# ── adjustment factors ───────────────────────────────────────────────────────
def _isin_aliases(connection: sqlite3.Connection) -> Dict[str, set]:
    """``symbol -> every ticker sharing its ISIN``, itself included."""
    return conn_cache.cached(
        connection, "ca_isin_aliases", lambda: _build_isin_aliases(connection)
    )


def _build_isin_aliases(connection: sqlite3.Connection) -> Dict[str, set]:
    by_isin: Dict[str, set] = {}
    symbol_isin: Dict[str, str] = {}
    for symbol, isin in connection.execute(
        "SELECT DISTINCT symbol, isin FROM market_bars WHERE isin <> ''"
    ):
        by_isin.setdefault(isin, set()).add(symbol)
        symbol_isin.setdefault(symbol, isin)
    return {
        symbol: by_isin.get(isin, {symbol})
        for symbol, isin in symbol_isin.items()
    }


def load_factors(
    connection: sqlite3.Connection,
    symbols: Optional[Sequence[str]] = None,
    *,
    include_dividends: bool = False,
    resolve_renames: bool = True,
) -> Dict[str, List[Tuple[date, float]]]:
    """Per-symbol ``(ex_date, factor)`` events, ascending.

    Only events that actually change the share base are returned unless
    ``include_dividends`` is set, in which case cash dividends are folded in as
    a price adjustment too (see the module docstring for why that is off by
    default).

    With ``resolve_renames`` an event is applied to every ticker that shares
    its ISIN, so a split filed under the company's present-day name still
    adjusts the prices it printed under its former name. Duplicates filed
    under both names are collapsed on ``(ex_date, subject)``.
    """
    clauses = ["factor IS NOT NULL"]
    if include_dividends:
        clauses = ["(factor IS NOT NULL OR dividend IS NOT NULL)"]
    where = f"WHERE {' AND '.join(clauses)}"
    rows = connection.execute(
        f"SELECT symbol, ex_date, subject, factor FROM corporate_actions "
        f"{where} ORDER BY ex_date"
    ).fetchall()

    aliases = _isin_aliases(connection) if resolve_renames else {}
    wanted = (
        {s.strip().upper() for s in symbols if s} if symbols else None
    )
    # (ex_date, subject) dedupes the same event filed under two tickers.
    seen: Dict[str, set] = {}
    out: Dict[str, List[Tuple[date, float]]] = {}
    for row in rows:
        factor = row["factor"]
        factor = 1.0 if factor is None else float(factor)
        ex_date = date.fromisoformat(row["ex_date"])
        targets = aliases.get(row["symbol"], {row["symbol"]})
        for target in targets:
            if wanted is not None and target not in wanted:
                continue
            key = (row["ex_date"], row["subject"])
            if key in seen.setdefault(target, set()):
                continue
            seen[target].add(key)
            out.setdefault(target, []).append((ex_date, factor))
    for events in out.values():
        events.sort()
    return out


def load_demergers(
    connection: sqlite3.Connection,
    symbols: Optional[Sequence[str]] = None,
    *,
    resolve_renames: bool = True,
) -> Dict[str, Set[date]]:
    """Per-symbol ex-dates on which the company handed out a spun-off entity.

    A demerger cannot be restated from the filing alone: the parent's price
    drops by whatever the child is worth, and that is only knowable from the
    child's own opening print. So these dates carry no factor and are instead
    reported here for the caller to skip, which keeps a structural payout from
    being scored as a market loss.

    ISIN aliases are resolved for the same reason they are in
    :func:`load_factors` -- NSE files an action under the company's present-day
    ticker, so Crompton Greaves' 2016 demerger sits under ``CGPOWER`` and would
    otherwise never be matched against the prices printed as ``CROMPGREAV``.
    """
    rows = connection.execute(
        "SELECT symbol, ex_date FROM corporate_actions WHERE kind = 'demerger'"
    ).fetchall()
    aliases = _isin_aliases(connection) if resolve_renames else {}
    wanted = (
        {s.strip().upper() for s in symbols if s} if symbols else None
    )
    out: Dict[str, Set[date]] = {}
    for row in rows:
        ex_date = date.fromisoformat(row["ex_date"])
        for target in aliases.get(row["symbol"], {row["symbol"]}):
            if wanted is not None and target not in wanted:
                continue
            out.setdefault(target, set()).add(ex_date)
    return out


def load_dividends(
    connection: sqlite3.Connection,
    symbols: Optional[Sequence[str]] = None,
    *,
    resolve_renames: bool = True,
) -> Dict[str, Dict[date, float]]:
    """Per-symbol cash dividends, keyed by ex-date, in rupees per share.

    These are deliberately NOT folded into the price series. On the ex-date
    the quote really does drop by roughly the payout, and that drop is not an
    artefact -- a live trailing stop sees it and can fire on it. Vendor
    "adjusted" series erase the gap, which quietly flatters every stop-based
    exit by hiding a move that would have happened to a real holder.

    Keeping the price drop and paying the cash separately reproduces what
    actually happens to the holder: a lower quote and a credit in the bank.

    Several payouts can share one ex-date (an interim and a special, say), so
    amounts are summed rather than overwritten.
    """
    rows = connection.execute(
        "SELECT symbol, ex_date, dividend FROM corporate_actions"
        " WHERE kind = 'dividend' AND dividend IS NOT NULL AND dividend > 0"
    ).fetchall()
    aliases = _isin_aliases(connection) if resolve_renames else {}
    wanted = (
        {s.strip().upper() for s in symbols if s} if symbols else None
    )
    out: Dict[str, Dict[date, float]] = {}
    for row in rows:
        ex_date = date.fromisoformat(row["ex_date"])
        amount = float(row["dividend"])
        for target in aliases.get(row["symbol"], {row["symbol"]}):
            if wanted is not None and target not in wanted:
                continue
            per_day = out.setdefault(target, {})
            per_day[ex_date] = per_day.get(ex_date, 0.0) + amount
    return out


def adjustment_series(
    events: Sequence[Tuple[date, float]], sessions: Sequence[date]
) -> List[float]:
    """Cumulative back-adjustment multiplier for each session.

    Walking backwards from the present, every session strictly *before* an
    ex-date carries that event's factor. The result is 1.0 for dates after the
    last event and shrinks going back in time, so
    ``close * adjustment`` is a continuous series on today's share base.
    """
    if not sessions:
        return []
    factors = [1.0] * len(sessions)
    if not events:
        return factors
    running = 1.0
    ordered = sorted(events, reverse=True)
    event_index = 0
    for position in range(len(sessions) - 1, -1, -1):
        day = sessions[position]
        while event_index < len(ordered) and ordered[event_index][0] > day:
            running *= ordered[event_index][1]
            event_index += 1
        factors[position] = running
    return factors


def coverage(connection: sqlite3.Connection) -> dict:
    row = connection.execute(
        "SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(ex_date), MAX(ex_date) "
        "FROM corporate_actions"
    ).fetchone()
    splits = connection.execute(
        "SELECT COUNT(*) FROM corporate_actions WHERE factor IS NOT NULL"
    ).fetchone()[0]
    return {
        "rows": row[0] or 0,
        "symbols": row[1] or 0,
        "first": row[2],
        "last": row[3],
        "adjusting": splits or 0,
    }


def print_status(connection: sqlite3.Connection) -> None:
    stats = coverage(connection)
    print(
        f"\nCorporate actions: {stats['rows']:,} events for "
        f"{stats['symbols']:,} symbols.\n"
        f"  range     : {stats['first']} -> {stats['last']}\n"
        f"  adjusting : {stats['adjusting']:,} (splits and bonuses)"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    global MIN_REQUEST_INTERVAL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", default="2012-01-01")
    parser.add_argument("--to", dest="end", default=None)
    parser.add_argument("--status", action="store_true")
    parser.add_argument(
        "--sweep", action="store_true",
        help=(
            "Walk every ticker in market_bars individually. Recovers events "
            "NSE only files under a company's present-day ticker."
        ),
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--rate", type=float, default=MIN_REQUEST_INTERVAL)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    MIN_REQUEST_INTERVAL = args.rate

    connection = open_store()
    try:
        if args.status:
            print_status(connection)
            return 0
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else date.today()
        if args.sweep:
            symbols = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT symbol FROM market_bars ORDER BY symbol"
                )
            ]
            result = sweep_symbols(
                symbols, start, end,
                connection=connection, resume=not args.no_resume,
            )
            logger.info(
                "Done: %d symbols, %d events.",
                result["symbols"], result["rows"],
            )
        else:
            result = run(
                start, end, connection=connection, resume=not args.no_resume
            )
            logger.info(
                "Done: %d windows, %d events.",
                result["windows"], result["rows"],
            )
        print_status(connection)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
