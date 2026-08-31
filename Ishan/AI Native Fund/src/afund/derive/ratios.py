"""Minimal derived fundamentals: YoY growth + margins from financials_quarterly.

Kept deliberately small for Phase 1 — just what's needed to sanity-check a
financials pipeline run and to feed a future regime/ranking layer. Reads
financials_quarterly (populated by data/financials.py); returns plain dicts,
writes nothing.
"""
from __future__ import annotations

import sqlite3


def _quarters(conn: sqlite3.Connection, instrument_id: int, statement_type: str = "consolidated") -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT period_end, revenue, operating_profit, net_profit, eps
          FROM financials_quarterly
         WHERE instrument_id = ? AND statement_type = ?
         ORDER BY period_end ASC
        """,
        (instrument_id, statement_type),
    ).fetchall()
    if not rows:
        # fall back to whatever statement_type is actually present (e.g. standalone-only coverage)
        rows = conn.execute(
            """
            SELECT period_end, revenue, operating_profit, net_profit, eps
              FROM financials_quarterly
             WHERE instrument_id = ?
             ORDER BY period_end ASC
            """,
            (instrument_id,),
        ).fetchall()
    return rows


def operating_margin(revenue: float | None, operating_profit: float | None) -> float | None:
    if not revenue or revenue == 0 or operating_profit is None:
        return None
    return operating_profit / revenue


def net_margin(revenue: float | None, net_profit: float | None) -> float | None:
    if not revenue or revenue == 0 or net_profit is None:
        return None
    return net_profit / revenue


def yoy_growth(current: float | None, year_ago: float | None) -> float | None:
    if current is None or year_ago is None or year_ago == 0:
        return None
    return (current - year_ago) / abs(year_ago)


def latest_quarter_ratios(conn: sqlite3.Connection, instrument_id: int, statement_type: str = "consolidated") -> dict:
    """Ratios for the most recent quarter, including YoY growth vs. the
    quarter 4 rows back (same quarter, prior year) when available.

    Returns a dict with period_end plus revenue_yoy / net_profit_yoy /
    operating_margin / net_margin — any of which may be None if the
    underlying data (or the year-ago comparison quarter) is missing.
    """
    quarters = _quarters(conn, instrument_id, statement_type)
    if not quarters:
        return {
            "instrument_id": instrument_id,
            "period_end": None,
            "revenue_yoy": None,
            "net_profit_yoy": None,
            "operating_margin": None,
            "net_margin": None,
        }

    latest = quarters[-1]
    year_ago = quarters[-5] if len(quarters) >= 5 else None

    return {
        "instrument_id": instrument_id,
        "period_end": latest["period_end"],
        "revenue_yoy": yoy_growth(latest["revenue"], year_ago["revenue"] if year_ago else None),
        "net_profit_yoy": yoy_growth(latest["net_profit"], year_ago["net_profit"] if year_ago else None),
        "operating_margin": operating_margin(latest["revenue"], latest["operating_profit"]),
        "net_margin": net_margin(latest["revenue"], latest["net_profit"]),
    }
