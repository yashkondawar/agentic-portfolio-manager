"""Phase 10 — ETF/MF fund analytics: rolling returns, risk-adjusted metrics,
capture ratios, and ETF premium/discount vs NAV.

Pure functions over mf_navs / daily_prices / index_data, mirroring the
degrade-to-None discipline of derive/returns.py and portfolio/risk.py: every
function returns None (or a dict with None fields) when there isn't enough
history, rather than raising or fabricating a number. Nothing here writes to
the database except refresh_fund_analytics(), which caches results into the
new derived_series table for the mapped-ETF + universe.mf_watchlist scheme
set (so the dashboard/agents can read a cheap cached series instead of
recomputing on every packet build).
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from afund.config import load_settings
from afund.derive.returns import _closest_on_or_before, _price_series

TRADING_DAYS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# Series helpers
# ---------------------------------------------------------------------------

def _nav_series(conn: sqlite3.Connection, scheme_code: str) -> list[tuple[str, float]]:
    """Ascending [(date, nav)] for one AMFI scheme code."""
    rows = conn.execute(
        """
        SELECT date, nav FROM mf_navs
         WHERE scheme_code = ? AND nav IS NOT NULL
         ORDER BY date ASC
        """,
        (scheme_code,),
    ).fetchall()
    return [(r["date"], r["nav"]) for r in rows]


def _returns_from_series(series: list[tuple[str, float]]) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for i in range(1, len(series)):
        prev = series[i - 1][1]
        date, val = series[i]
        if prev and prev != 0:
            out.append((date, (val - prev) / prev))
    return out


def _sd_annualized(returns: list[float]) -> float | None:
    n = len(returns)
    if n < 2:
        return None
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return (var ** 0.5) * (TRADING_DAYS_PER_YEAR ** 0.5)


def _amfi_scheme_code_for_instrument(conn: sqlite3.Connection, instrument_id: int) -> str | None:
    row = conn.execute("SELECT amfi_scheme_code FROM instruments WHERE id = ?", (instrument_id,)).fetchone()
    return row["amfi_scheme_code"] if row else None


# ---------------------------------------------------------------------------
# Rolling returns / SD / risk-adjusted
# ---------------------------------------------------------------------------

def mf_rolling_returns(conn: sqlite3.Connection, scheme_code: str, years: list[float] | None = None,
                        as_of: str | None = None) -> dict[str, float | None]:
    """CAGR over each trailing window in `years` (default [3, 5]), keyed
    'Ny' -> CAGR or None if history doesn't reach back that far."""
    years = years or [3, 5]
    series = _nav_series(conn, scheme_code)
    result: dict[str, float | None] = {f"{y}y": None for y in years}
    if not series:
        return result

    as_of = as_of or dt.date.today().isoformat()
    end_point = _closest_on_or_before(series, as_of)
    if end_point is None:
        return result
    end_date, end_nav = end_point

    for y in years:
        start_target = (dt.date.fromisoformat(end_date) - dt.timedelta(days=round(y * 365.25))).isoformat()
        start_point = _closest_on_or_before(series, start_target)
        if start_point is None or start_point[0] == end_date:
            continue
        start_date, start_nav = start_point
        if not start_nav or start_nav <= 0 or end_nav <= 0:
            continue
        actual_years = (dt.date.fromisoformat(end_date) - dt.date.fromisoformat(start_date)).days / 365.25
        if actual_years <= 0:
            continue
        result[f"{y}y"] = (end_nav / start_nav) ** (1 / actual_years) - 1
    return result


def mf_rolling_sd(conn: sqlite3.Connection, scheme_code: str, years: list[float] | None = None,
                   as_of: str | None = None) -> dict[str, float | None]:
    """Annualized SD of daily NAV returns over each trailing window."""
    years = years or [3, 5]
    series = _nav_series(conn, scheme_code)
    result: dict[str, float | None] = {f"{y}y": None for y in years}
    if len(series) < 2:
        return result

    as_of = as_of or dt.date.today().isoformat()
    end_point = _closest_on_or_before(series, as_of)
    if end_point is None:
        return result
    end_date = end_point[0]

    for y in years:
        start_target = (dt.date.fromisoformat(end_date) - dt.timedelta(days=round(y * 365.25))).isoformat()
        window = [(d, v) for d, v in series if start_target <= d <= end_date]
        if len(window) < 30:  # not enough observations to trust an annualized SD
            continue
        rets = [r for _, r in _returns_from_series(window)]
        result[f"{y}y"] = _sd_annualized(rets)
    return result


def mf_risk_adjusted(conn: sqlite3.Connection, scheme_code: str, years: list[float] | None = None,
                      as_of: str | None = None) -> dict[str, float | None]:
    """Sharpe-style ratio (CAGR - risk_free) / annualized SD per window.
    Uses config/settings.yaml -> portfolio.risk_free_rate_annual."""
    years = years or [3, 5]
    settings = load_settings()
    rf = settings.get("portfolio", {}).get("risk_free_rate_annual", 0.065)

    rolling_returns = mf_rolling_returns(conn, scheme_code, years=years, as_of=as_of)
    rolling_sd = mf_rolling_sd(conn, scheme_code, years=years, as_of=as_of)

    result: dict[str, float | None] = {}
    for y in years:
        key = f"{y}y"
        cagr_val = rolling_returns.get(key)
        sd_val = rolling_sd.get(key)
        if cagr_val is None or sd_val is None or sd_val == 0:
            result[key] = None
        else:
            result[key] = (cagr_val - rf) / sd_val
    return result


# ---------------------------------------------------------------------------
# Capture ratios
# ---------------------------------------------------------------------------

def mf_capture_ratios(conn: sqlite3.Connection, scheme_code: str, benchmark: str = "NIFTY 50",
                       as_of: str | None = None) -> dict[str, float | None]:
    """Upside/downside capture ratio of the scheme vs a benchmark index.

    Formula (standard capture-ratio definition):
      1. Build daily return series for scheme (NAV-based) and benchmark
         (index_data close-based), joined on date.
      2. Partition joined days into "up days" (benchmark daily return > 0)
         and "down days" (benchmark daily return < 0).
      3. Upside capture  = mean(scheme_return on up days)   / mean(benchmark_return on up days)
         Downside capture = mean(scheme_return on down days) / mean(benchmark_return on down days)
      Both expressed as ratios (1.0 = matches benchmark; >1.0 on upside is
      good, >1.0 on downside is bad — captures more of the benchmark's falls).

    Returns None for a ratio if there are fewer than 10 up/down days in the
    overlapping window, or no overlapping history at all.
    """
    nav_series = _nav_series(conn, scheme_code)
    index_series = _price_series(conn, index_name=benchmark)
    result: dict[str, float | None] = {"upside_capture": None, "downside_capture": None, "observations": 0}
    if len(nav_series) < 2 or len(index_series) < 2:
        return result

    scheme_returns = dict(_returns_from_series(nav_series))
    index_returns = dict(_returns_from_series(index_series))

    if as_of:
        scheme_returns = {d: r for d, r in scheme_returns.items() if d <= as_of}
        index_returns = {d: r for d, r in index_returns.items() if d <= as_of}

    common_dates = sorted(set(scheme_returns) & set(index_returns))
    if not common_dates:
        return result

    up_scheme, up_bench, down_scheme, down_bench = [], [], [], []
    for d in common_dates:
        bench_r = index_returns[d]
        scheme_r = scheme_returns[d]
        if bench_r > 0:
            up_scheme.append(scheme_r)
            up_bench.append(bench_r)
        elif bench_r < 0:
            down_scheme.append(scheme_r)
            down_bench.append(bench_r)

    result["observations"] = len(common_dates)

    if len(up_bench) >= 10:
        mean_up_bench = sum(up_bench) / len(up_bench)
        if mean_up_bench != 0:
            result["upside_capture"] = (sum(up_scheme) / len(up_scheme)) / mean_up_bench

    if len(down_bench) >= 10:
        mean_down_bench = sum(down_bench) / len(down_bench)
        if mean_down_bench != 0:
            result["downside_capture"] = (sum(down_scheme) / len(down_scheme)) / mean_down_bench

    return result


# ---------------------------------------------------------------------------
# ETF premium/discount vs NAV
# ---------------------------------------------------------------------------

def etf_premium_discount(conn: sqlite3.Connection, symbol: str) -> dict:
    """(daily_prices.close - mf_navs.nav) / nav for an ETF, matched via
    instruments.amfi_scheme_code. Returns {"as_of", "latest_pct", "series":
    [(date, pct), ...]}; latest_pct/series are None/[] if the ETF has no
    scheme-code mapping yet or no overlapping price/NAV dates."""
    row = conn.execute(
        "SELECT id, amfi_scheme_code FROM instruments WHERE symbol = ? AND instrument_type = 'ETF'",
        (symbol,),
    ).fetchone()
    if row is None or not row["amfi_scheme_code"]:
        return {"as_of": None, "latest_pct": None, "series": [], "note": "no amfi_scheme_code mapped"}

    instrument_id = row["id"]
    scheme_code = row["amfi_scheme_code"]

    price_series = dict(_price_series(conn, instrument_id=instrument_id))
    nav_series = dict(_nav_series(conn, scheme_code))

    common_dates = sorted(set(price_series) & set(nav_series))
    if not common_dates:
        return {"as_of": None, "latest_pct": None, "series": [], "note": "no overlapping price/NAV dates"}

    series = []
    for d in common_dates:
        nav = nav_series[d]
        close = price_series[d]
        if nav and nav != 0:
            series.append((d, (close - nav) / nav))

    if not series:
        return {"as_of": None, "latest_pct": None, "series": [], "note": "no valid NAV denominators"}

    as_of, latest_pct = series[-1]
    return {"as_of": as_of, "latest_pct": latest_pct, "series": series, "note": None}


# ---------------------------------------------------------------------------
# Cache refresh: writes into derived_series
# ---------------------------------------------------------------------------

def _mapped_etfs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, symbol, amfi_scheme_code FROM instruments
         WHERE instrument_type = 'ETF' AND amfi_scheme_code IS NOT NULL AND active = 1
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _upsert_series(conn: sqlite3.Connection, *, instrument_id: int | None, scheme_code: str | None,
                    metric_name: str, date: str, value: float | None) -> None:
    if value is None:
        return
    conn.execute(
        """
        INSERT INTO derived_series (instrument_id, scheme_code, metric_name, date, value)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(COALESCE(instrument_id, -1), COALESCE(scheme_code, ''), metric_name, date)
        DO UPDATE SET value = excluded.value
        """,
        (instrument_id, scheme_code, metric_name, date, value),
    )


def refresh_fund_analytics(conn: sqlite3.Connection, as_of: str | None = None) -> dict:
    """Recompute + cache rolling returns / SD / risk-adjusted / capture /
    premium-discount for every mapped ETF, plus rolling returns/SD/risk-adj
    for every universe.mf_watchlist scheme. Idempotent (upserts). Returns a
    small summary dict for logging."""
    as_of = as_of or dt.date.today().isoformat()
    settings = load_settings()
    benchmark = settings.get("portfolio", {}).get("benchmark", "NIFTY 50")
    watchlist = settings.get("universe", {}).get("mf_watchlist", []) or []

    etfs_processed = 0
    mf_processed = 0

    for etf in _mapped_etfs(conn):
        instrument_id = etf["id"]
        scheme_code = etf["amfi_scheme_code"]
        symbol = etf["symbol"]

        rolling = mf_rolling_returns(conn, scheme_code, as_of=as_of)
        sd = mf_rolling_sd(conn, scheme_code, as_of=as_of)
        risk_adj = mf_risk_adjusted(conn, scheme_code, as_of=as_of)
        capture = mf_capture_ratios(conn, scheme_code, benchmark=benchmark, as_of=as_of)
        prem_disc = etf_premium_discount(conn, symbol)

        for label, val in rolling.items():
            _upsert_series(conn, instrument_id=instrument_id, scheme_code=None,
                            metric_name=f"rolling_return_{label}", date=as_of, value=val)
        for label, val in sd.items():
            _upsert_series(conn, instrument_id=instrument_id, scheme_code=None,
                            metric_name=f"rolling_sd_{label}", date=as_of, value=val)
        for label, val in risk_adj.items():
            _upsert_series(conn, instrument_id=instrument_id, scheme_code=None,
                            metric_name=f"risk_adjusted_{label}", date=as_of, value=val)
        _upsert_series(conn, instrument_id=instrument_id, scheme_code=None,
                        metric_name="capture_upside", date=as_of, value=capture.get("upside_capture"))
        _upsert_series(conn, instrument_id=instrument_id, scheme_code=None,
                        metric_name="capture_downside", date=as_of, value=capture.get("downside_capture"))
        if prem_disc.get("latest_pct") is not None:
            _upsert_series(conn, instrument_id=instrument_id, scheme_code=None,
                            metric_name="premium_discount_pct", date=prem_disc["as_of"],
                            value=prem_disc["latest_pct"])
        etfs_processed += 1

    for scheme_code in watchlist:
        rolling = mf_rolling_returns(conn, scheme_code, as_of=as_of)
        sd = mf_rolling_sd(conn, scheme_code, as_of=as_of)
        risk_adj = mf_risk_adjusted(conn, scheme_code, as_of=as_of)

        for label, val in rolling.items():
            _upsert_series(conn, instrument_id=None, scheme_code=scheme_code,
                            metric_name=f"rolling_return_{label}", date=as_of, value=val)
        for label, val in sd.items():
            _upsert_series(conn, instrument_id=None, scheme_code=scheme_code,
                            metric_name=f"rolling_sd_{label}", date=as_of, value=val)
        for label, val in risk_adj.items():
            _upsert_series(conn, instrument_id=None, scheme_code=scheme_code,
                            metric_name=f"risk_adjusted_{label}", date=as_of, value=val)
        mf_processed += 1

    conn.commit()
    return {"as_of": as_of, "etfs_processed": etfs_processed, "mf_watchlist_processed": mf_processed}
