"""Return calculations over daily_prices (instruments) / index_data (indices).

Pure functions: given a sqlite3.Connection and an identifier, return floats
(or None when there isn't enough history). Nothing is written back to the
database from this module — callers (e.g. derive/regime.py, a future
reporting layer) decide what to do with the numbers.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

TRADING_DAYS_PER_YEAR = 252


def _price_series(conn: sqlite3.Connection, *, instrument_id: int | None = None,
                   index_name: str | None = None) -> list[tuple[str, float]]:
    """Return [(date, close)] ascending, from daily_prices or index_data."""
    if instrument_id is not None:
        rows = conn.execute(
            """
            SELECT date, close FROM daily_prices
             WHERE instrument_id = ? AND close IS NOT NULL
             ORDER BY date ASC
            """,
            (instrument_id,),
        ).fetchall()
    elif index_name is not None:
        rows = conn.execute(
            """
            SELECT date, close FROM index_data
             WHERE index_name = ? AND close IS NOT NULL
             ORDER BY date ASC
            """,
            (index_name,),
        ).fetchall()
    else:
        raise ValueError("must pass either instrument_id or index_name")
    return [(r["date"], r["close"]) for r in rows]


def _closest_on_or_before(series: list[tuple[str, float]], target_date: str) -> tuple[str, float] | None:
    """Latest (date, close) with date <= target_date. series must be ascending."""
    result = None
    for date, close in series:
        if date <= target_date:
            result = (date, close)
        else:
            break
    return result


def daily_returns(conn: sqlite3.Connection, *, instrument_id: int | None = None,
                   index_name: str | None = None) -> list[tuple[str, float]]:
    """Day-over-day simple returns: [(date, return)], one shorter than the
    price series (first day has no prior close to compare against)."""
    series = _price_series(conn, instrument_id=instrument_id, index_name=index_name)
    out: list[tuple[str, float]] = []
    for i in range(1, len(series)):
        prev_date, prev_close = series[i - 1]
        date, close = series[i]
        if prev_close and prev_close != 0:
            out.append((date, (close - prev_close) / prev_close))
    return out


def trailing_return(conn: sqlite3.Connection, *, instrument_id: int | None = None,
                     index_name: str | None = None, years: float,
                     as_of: str | None = None) -> float | None:
    """Absolute (non-annualized) return over the trailing `years` window
    ending at `as_of` (defaults to today). Returns None if there isn't a
    price point at or before the window start."""
    series = _price_series(conn, instrument_id=instrument_id, index_name=index_name)
    if not series:
        return None

    as_of = as_of or dt.date.today().isoformat()
    end_point = _closest_on_or_before(series, as_of)
    if end_point is None:
        return None
    end_date, end_close = end_point

    start_target = (dt.date.fromisoformat(end_date) - dt.timedelta(days=round(years * 365.25))).isoformat()
    start_point = _closest_on_or_before(series, start_target)
    if start_point is None or start_point[0] == end_date:
        return None
    _, start_close = start_point

    if not start_close:
        return None
    return (end_close - start_close) / start_close


def cagr(conn: sqlite3.Connection, *, instrument_id: int | None = None,
          index_name: str | None = None, years: float,
          as_of: str | None = None) -> float | None:
    """Compound annual growth rate over the trailing `years` window."""
    series = _price_series(conn, instrument_id=instrument_id, index_name=index_name)
    if not series:
        return None

    as_of = as_of or dt.date.today().isoformat()
    end_point = _closest_on_or_before(series, as_of)
    if end_point is None:
        return None
    end_date, end_close = end_point

    start_target = (dt.date.fromisoformat(end_date) - dt.timedelta(days=round(years * 365.25))).isoformat()
    start_point = _closest_on_or_before(series, start_target)
    if start_point is None or start_point[0] == end_date:
        return None
    start_date, start_close = start_point

    if not start_close or start_close <= 0 or end_close <= 0:
        return None

    actual_years = (dt.date.fromisoformat(end_date) - dt.date.fromisoformat(start_date)).days / 365.25
    if actual_years <= 0:
        return None

    return (end_close / start_close) ** (1 / actual_years) - 1


def history_span_years(conn: sqlite3.Connection, *, instrument_id: int | None = None,
                        index_name: str | None = None) -> float:
    """How many years of price history are actually available — used by
    regime.py to decide whether a signal has enough history to be trusted."""
    series = _price_series(conn, instrument_id=instrument_id, index_name=index_name)
    if len(series) < 2:
        return 0.0
    first_date = dt.date.fromisoformat(series[0][0])
    last_date = dt.date.fromisoformat(series[-1][0])
    return (last_date - first_date).days / 365.25
