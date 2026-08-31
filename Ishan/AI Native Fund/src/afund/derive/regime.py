"""The "Marks lens" cycle/regime overlay — encodes registry/strategies/
cycle_contrarian.yaml as pure calculation (no LLM calls, no I/O beyond
reading index_data/daily_prices via the passed connection).

Thresholds mirror the strategy YAML's entry/exit criteria:
  - panic_buy:            1y return <= -40%  OR  5y CAGR <= -10%
  - long_term_neglect:    ~0% absolute return over a 10-12y window (we use
                           10y and treat |return| <= 5% as "approximately zero")
  - euphoria_avoid:       1y return >= +100%

These are DRAFT thresholds per the strategy file's own status (status:
DRAFT, "do not treat entry/exit thresholds below as final until confirmed"
in cycle_contrarian.yaml) — this module just implements them faithfully;
it isn't the place to second-guess the numbers.

Degrades gracefully: any metric that can't be computed (insufficient
history) is returned as None and contributes no signal, and the result
carries an 'insufficient_history' flag when core inputs are missing so
downstream consumers don't misread a None as "checked, clean."
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import statistics

from afund.derive.returns import cagr as _cagr
from afund.derive.returns import history_span_years, trailing_return

EUPHORIA_1Y_THRESHOLD = 1.00       # +100%
PANIC_1Y_THRESHOLD = -0.40         # -40%
PANIC_5Y_CAGR_THRESHOLD = -0.10    # -10% annualized
NEGLECT_YEARS = 10.0
NEGLECT_ABS_RETURN_THRESHOLD = 0.05  # "approximately zero" band, +/-5%

PE_HISTORY_YEARS = 5.0


def _pe_series(conn: sqlite3.Connection, index_name: str) -> list[tuple[str, float]]:
    rows = conn.execute(
        """
        SELECT date, pe FROM index_data
         WHERE index_name = ? AND pe IS NOT NULL
         ORDER BY date ASC
        """,
        (index_name,),
    ).fetchall()
    return [(r["date"], r["pe"]) for r in rows]


def pe_percentile_5y(conn: sqlite3.Connection, index_name: str, as_of: str | None = None) -> float | None:
    """Percentile rank (0-100) of the current PE within its trailing 5y
    history. None if there's no current PE or fewer than ~30 history points
    (too thin to be a meaningful percentile)."""
    series = _pe_series(conn, index_name)
    if not series:
        return None

    as_of = as_of or dt.date.today().isoformat()
    window_start = (dt.date.fromisoformat(as_of) - dt.timedelta(days=round(PE_HISTORY_YEARS * 365.25))).isoformat()
    windowed = [pe for date, pe in series if window_start <= date <= as_of]
    if len(windowed) < 30:
        return None

    current_pe = windowed[-1]
    rank = sum(1 for pe in windowed if pe <= current_pe)
    return 100.0 * rank / len(windowed)


def pe_zscore(conn: sqlite3.Connection, index_name: str, as_of: str | None = None) -> float | None:
    """Z-score of the current PE vs. its trailing 5y mean/stdev."""
    series = _pe_series(conn, index_name)
    if not series:
        return None

    as_of = as_of or dt.date.today().isoformat()
    window_start = (dt.date.fromisoformat(as_of) - dt.timedelta(days=round(PE_HISTORY_YEARS * 365.25))).isoformat()
    windowed = [pe for date, pe in series if window_start <= date <= as_of]
    if len(windowed) < 30:
        return None

    current_pe = windowed[-1]
    mean_pe = statistics.mean(windowed)
    try:
        stdev_pe = statistics.stdev(windowed)
    except statistics.StatisticsError:
        return None
    if stdev_pe == 0:
        return None
    return (current_pe - mean_pe) / stdev_pe


def evaluate_regime(conn: sqlite3.Connection, index_name: str, as_of: str | None = None) -> dict:
    """Evaluate the cycle_contrarian signals for one index as of a date.

    Returns:
        {
          "index": str, "date": str,
          "pe": float | None, "pe_percentile_5y": float | None, "pe_zscore": float | None,
          "ret_1y": float | None, "cagr_5y": float | None, "ret_10y": float | None,
          "signals": [str, ...],
          "insufficient_history": bool,
        }
    """
    as_of = as_of or dt.date.today().isoformat()

    pe_row = conn.execute(
        "SELECT pe FROM index_data WHERE index_name = ? AND date <= ? AND pe IS NOT NULL "
        "ORDER BY date DESC LIMIT 1",
        (index_name, as_of),
    ).fetchone()
    current_pe = pe_row["pe"] if pe_row else None

    ret_1y = trailing_return(conn, index_name=index_name, years=1.0, as_of=as_of)
    cagr_5y = _cagr(conn, index_name=index_name, years=5.0, as_of=as_of)
    ret_10y = trailing_return(conn, index_name=index_name, years=NEGLECT_YEARS, as_of=as_of)
    span_years = history_span_years(conn, index_name=index_name)

    signals: list[str] = []

    if ret_1y is not None and ret_1y >= EUPHORIA_1Y_THRESHOLD:
        signals.append("euphoria_avoid")

    if (ret_1y is not None and ret_1y <= PANIC_1Y_THRESHOLD) or \
       (cagr_5y is not None and cagr_5y <= PANIC_5Y_CAGR_THRESHOLD):
        signals.append("panic_buy")

    if ret_10y is not None and abs(ret_10y) <= NEGLECT_ABS_RETURN_THRESHOLD and span_years >= NEGLECT_YEARS:
        signals.append("long_term_neglect")

    # Core inputs needed for any signal to be meaningful: at least a 1y return
    # and a full year of history. If those aren't there, flag it explicitly
    # rather than silently returning an empty (and misleadingly "clean") signal list.
    insufficient_history = ret_1y is None or span_years < 1.0

    return {
        "index": index_name,
        "date": as_of,
        "pe": current_pe,
        "pe_percentile_5y": pe_percentile_5y(conn, index_name, as_of=as_of),
        "pe_zscore": pe_zscore(conn, index_name, as_of=as_of),
        "ret_1y": ret_1y,
        "cagr_5y": cagr_5y,
        "ret_10y": ret_10y,
        "signals": signals,
        "insufficient_history": insufficient_history,
    }
