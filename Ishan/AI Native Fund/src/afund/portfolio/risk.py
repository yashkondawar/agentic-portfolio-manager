"""Portfolio risk metrics computed from nav_history + positions + benchmark.

Everything here is a pure read: no writes, no network, no LLM. Every metric
degrades gracefully to None (rather than raising) when there isn't enough
history to compute it meaningfully — `snapshot()`'s `insufficient_history`
flag tells callers whether that's the case for the return-based metrics as
a whole (< MIN_OBSERVATIONS daily returns).
"""
from __future__ import annotations

import datetime as dt
import math
import sqlite3
import statistics

from afund.config import load_settings

TRADING_DAYS_PER_YEAR = 252
MIN_OBSERVATIONS = 30
VAR_PERCENTILE = 0.05  # 1-day 95% VaR

# Canonical mapping lives in afund.sectors (dependency-free module — keeps
# portfolio/ free of any orchestrator/cycles-layer import).
from afund.sectors import SECTOR_TO_KPI_KEY


def _nav_series(conn: sqlite3.Connection, as_of: str | None = None) -> list[tuple[str, float]]:
    """[(date, total_nav)] ascending, up to and including as_of."""
    if as_of is not None:
        rows = conn.execute(
            "SELECT date, total_nav FROM nav_history WHERE date <= ? AND total_nav IS NOT NULL ORDER BY date ASC",
            (as_of,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT date, total_nav FROM nav_history WHERE total_nav IS NOT NULL ORDER BY date ASC"
        ).fetchall()
    return [(r["date"], r["total_nav"]) for r in rows]


def _returns_from_series(series: list[tuple[str, float]]) -> list[float]:
    out = []
    for i in range(1, len(series)):
        prev = series[i - 1][1]
        cur = series[i][1]
        if prev:
            out.append((cur - prev) / prev)
    return out


def _index_series(conn: sqlite3.Connection, index_name: str, as_of: str | None = None) -> list[tuple[str, float]]:
    if as_of is not None:
        rows = conn.execute(
            "SELECT date, close FROM index_data WHERE index_name = ? AND date <= ? AND close IS NOT NULL ORDER BY date ASC",
            (index_name, as_of),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT date, close FROM index_data WHERE index_name = ? AND close IS NOT NULL ORDER BY date ASC",
            (index_name,),
        ).fetchall()
    return [(r["date"], r["close"]) for r in rows]


def _sd_annualized(daily_returns: list[float]) -> float | None:
    if len(daily_returns) < 2:
        return None
    try:
        sd = statistics.stdev(daily_returns)
    except statistics.StatisticsError:
        return None
    if math.isnan(sd):
        return None
    return sd * math.sqrt(TRADING_DAYS_PER_YEAR)


def _historical_var_95_1d(daily_returns: list[float]) -> float | None:
    """Historical percentile method: the 5th percentile of the daily return
    distribution, expressed as a positive loss fraction (e.g. 0.023 means a
    2.3% 1-day loss at 95% confidence). None if fewer than MIN_OBSERVATIONS
    returns are available."""
    if len(daily_returns) < MIN_OBSERVATIONS:
        return None
    sorted_returns = sorted(daily_returns)
    # Nearest-rank percentile (index method), no interpolation.
    idx = max(0, min(len(sorted_returns) - 1, int(math.floor(VAR_PERCENTILE * len(sorted_returns)))))
    percentile_return = sorted_returns[idx]
    return -percentile_return if percentile_return < 0 else 0.0


def _max_drawdown_pct(nav_values: list[float]) -> float | None:
    if len(nav_values) < 2:
        return None
    peak = nav_values[0]
    max_dd = 0.0
    for v in nav_values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak
            if dd < max_dd:
                max_dd = dd
    return max_dd * 100.0


def _beta_and_alpha(
    portfolio_returns_by_date: dict[str, float],
    benchmark_returns_by_date: dict[str, float],
    risk_free_rate_annual: float,
) -> tuple[float | None, float | None, int]:
    """CAPM beta and annualized Jensen's alpha over OVERLAPPING dates only.

    beta = Cov(Rp, Rm) / Var(Rm)
    alpha (daily) = mean(Rp) - [Rf_daily + beta * (mean(Rm) - Rf_daily)]
    alpha (annualized) = alpha_daily * TRADING_DAYS_PER_YEAR

    Rf_daily conversion: simple daily rate = risk_free_rate_annual / 252
    (not geometric compounding — adequate at these small daily magnitudes
    and keeps the annualization symmetric: alpha_daily * 252 undoes it).
    """
    common_dates = sorted(set(portfolio_returns_by_date) & set(benchmark_returns_by_date))
    n = len(common_dates)
    if n < 2:
        return None, None, n

    rp = [portfolio_returns_by_date[d] for d in common_dates]
    rm = [benchmark_returns_by_date[d] for d in common_dates]

    mean_rp = statistics.mean(rp)
    mean_rm = statistics.mean(rm)

    cov = sum((a - mean_rp) * (b - mean_rm) for a, b in zip(rp, rm)) / n
    var_rm = sum((b - mean_rm) ** 2 for b in rm) / n

    if var_rm == 0:
        return None, None, n

    beta = cov / var_rm

    rf_daily = risk_free_rate_annual / TRADING_DAYS_PER_YEAR
    alpha_daily = mean_rp - (rf_daily + beta * (mean_rm - rf_daily))
    alpha_annualized = alpha_daily * TRADING_DAYS_PER_YEAR

    return beta, alpha_annualized, n


def _concentration(conn: sqlite3.Connection, as_of_prices: dict[int, float]) -> dict:
    positions = conn.execute(
        "SELECT instrument_id, qty, avg_cost FROM positions WHERE qty != 0"
    ).fetchall()

    weights: list[tuple[int, float]] = []
    total_mv = 0.0
    for pos in positions:
        price = as_of_prices.get(pos["instrument_id"])
        if price is None:
            continue
        mv = pos["qty"] * price
        total_mv += mv
        weights.append((pos["instrument_id"], mv))

    if total_mv <= 0 or not weights:
        return {
            "hhi": None,
            "top5_weight_pct": None,
            "position_count": len(positions),
        }

    pct_weights = [(iid, mv / total_mv) for iid, mv in weights]
    hhi = sum(w ** 2 for _, w in pct_weights)
    top5 = sorted((w for _, w in pct_weights), reverse=True)[:5]
    top5_weight_pct = sum(top5) * 100.0

    return {
        "hhi": hhi,
        "top5_weight_pct": top5_weight_pct,
        "position_count": len(positions),
    }


def _positions_detail(conn: sqlite3.Connection, as_of: str) -> list[dict]:
    from afund.portfolio.nav import price_on_or_before

    positions = conn.execute(
        """
        SELECT p.instrument_id, p.qty, p.avg_cost, i.symbol
          FROM positions p
          JOIN instruments i ON i.id = p.instrument_id
         WHERE p.qty != 0
        """
    ).fetchall()

    detail = []
    total_mv = 0.0
    prices: dict[int, float | None] = {}
    for pos in positions:
        price = price_on_or_before(conn, pos["instrument_id"], as_of)
        prices[pos["instrument_id"]] = price
        if price is not None:
            total_mv += pos["qty"] * price

    for pos in positions:
        price = prices[pos["instrument_id"]]
        market_value = pos["qty"] * price if price is not None else None
        weight_pct = (market_value / total_mv * 100.0) if (market_value is not None and total_mv > 0) else None
        unrealized_pnl = (price - pos["avg_cost"]) * pos["qty"] if price is not None else None
        unrealized_pnl_pct = (
            (price - pos["avg_cost"]) / pos["avg_cost"] * 100.0
            if price is not None and pos["avg_cost"]
            else None
        )
        detail.append(
            {
                "symbol": pos["symbol"],
                "qty": pos["qty"],
                "avg_cost": pos["avg_cost"],
                "last_price": price,
                "market_value": market_value,
                "weight_pct": weight_pct,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
            }
        )
    return detail


def snapshot(conn: sqlite3.Connection, as_of: str | None = None) -> dict:
    """Compute the full risk snapshot as of `as_of` (default: latest nav_history date).

    Returns a dict with sd_annualized, var_95_1d_pct, var_95_1d_value,
    max_drawdown_pct, beta, jensens_alpha_annualized, concentration,
    positions_detail, observations, insufficient_history.

    Every numeric metric is None when it can't be computed (missing/short
    history, zero variance, etc.) rather than raising or returning NaN.
    """
    settings = load_settings()
    portfolio_cfg = settings.get("portfolio", {})
    benchmark_name = portfolio_cfg.get("benchmark", "NIFTY 50")
    risk_free_rate_annual = float(portfolio_cfg.get("risk_free_rate_annual", 0.065))

    nav_series = _nav_series(conn, as_of=as_of)
    as_of = as_of or (nav_series[-1][0] if nav_series else dt.date.today().isoformat())

    nav_values = [v for _, v in nav_series]
    daily_returns = _returns_from_series(nav_series)
    observations = len(daily_returns)
    insufficient_history = observations < MIN_OBSERVATIONS

    sd_annualized = _sd_annualized(daily_returns)

    var_95_1d_pct = _historical_var_95_1d(daily_returns)
    latest_nav = nav_values[-1] if nav_values else None
    var_95_1d_value = (
        var_95_1d_pct * latest_nav if (var_95_1d_pct is not None and latest_nav is not None) else None
    )

    max_drawdown_pct = _max_drawdown_pct(nav_values)

    portfolio_returns_by_date = {d: r for d, r in zip((d for d, _ in nav_series[1:]), daily_returns)}
    benchmark_series = _index_series(conn, benchmark_name, as_of=as_of)
    benchmark_returns = _returns_from_series(benchmark_series)
    benchmark_returns_by_date = {d: r for d, r in zip((d for d, _ in benchmark_series[1:]), benchmark_returns)}

    beta, jensens_alpha_annualized, overlap_n = _beta_and_alpha(
        portfolio_returns_by_date, benchmark_returns_by_date, risk_free_rate_annual
    )
    if overlap_n < MIN_OBSERVATIONS:
        # Overlapping-history requirement mirrors the same MIN_OBSERVATIONS
        # bar as the rest of the return-based metrics.
        beta, jensens_alpha_annualized = None, None

    # Prices as-of for concentration/positions_detail.
    from afund.portfolio.nav import price_on_or_before

    position_rows = conn.execute("SELECT instrument_id FROM positions WHERE qty != 0").fetchall()
    as_of_prices = {
        row["instrument_id"]: price_on_or_before(conn, row["instrument_id"], as_of)
        for row in position_rows
    }
    concentration = _concentration(conn, as_of_prices)
    positions_detail = _positions_detail(conn, as_of)

    return {
        "as_of": as_of,
        "sd_annualized": sd_annualized,
        "var_95_1d_pct": var_95_1d_pct,
        "var_95_1d_value": var_95_1d_value,
        "max_drawdown_pct": max_drawdown_pct,
        "beta": beta,
        "jensens_alpha_annualized": jensens_alpha_annualized,
        "concentration": concentration,
        "positions_detail": positions_detail,
        "observations": observations,
        "insufficient_history": insufficient_history,
    }


def _resolve_sector_scope(conn: sqlite3.Connection, *, instrument_id: int | None, sector: str | None) -> str | None:
    """Resolve a registry KPI sector slug (cycle_assessments.scope) from
    either an explicit `sector` (raw NSE instruments.sector string, or
    already a registry slug / scope name) or an instrument_id lookup."""
    if sector:
        # Accept either a raw NSE sector string or an already-resolved
        # registry slug / market scope (e.g. "NIFTY 50") — try the map,
        # fall back to the string as-is.
        return SECTOR_TO_KPI_KEY.get(sector, sector)
    if instrument_id is not None:
        row = conn.execute("SELECT sector FROM instruments WHERE id = ?", (instrument_id,)).fetchone()
        if row and row["sector"]:
            return SECTOR_TO_KPI_KEY.get(row["sector"], row["sector"])
    return None


def cycle_adjusted_limit(
    conn: sqlite3.Connection,
    *,
    instrument_id: int | None = None,
    sector: str | None = None,
    base_limit_pct: float | None = None,
) -> dict:
    """max_single_position_pct adjusted by the latest sector/scope
    valuation_cycle phase's multiplier (registry/rules/risk_limits.yaml ->
    phase_multipliers).

    Pass either instrument_id (its instruments.sector is looked up and
    mapped to a registry KPI slug) or sector directly (a raw NSE sector
    string, a registry slug, or a market scope like "NIFTY 50" — all are
    tried against SECTOR_TO_KPI_KEY, falling back to using the string as
    given). Falls back sector-scope -> NIFTY 500 -> NIFTY 50 when the
    sector-specific scope has no assessment yet, mirroring
    orchestrator.context._build_cycle_context / cycles.funnel.gate1_quant_cycle.

    base_limit_pct defaults to registry/rules/risk_limits.yaml's
    max_single_position_pct.value.

    Returns {"base_limit_pct", "multiplier", "adjusted_limit_pct",
    "phase_id", "scope_used", "unknown_phase", "note"}. unknown_phase=True
    (multiplier forced to 1.0) when no cycle_assessments row exists for any
    fallback scope, or the phase_id isn't a recognized key in
    phase_multipliers — cycle-aware sizing never guesses tighter or looser
    than the base limit when it doesn't actually know the phase.
    """
    import sys
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from registry.registry import Registry

    reg = Registry.load()
    if base_limit_pct is None:
        base_limit_pct = float(reg.rules.max_single_position_pct.value)
    multipliers = reg.rules.phase_multipliers.value

    resolved_scope = _resolve_sector_scope(conn, instrument_id=instrument_id, sector=sector)
    candidate_scopes = [resolved_scope, "NIFTY 500", "NIFTY 50"]
    seen: set[str] = set()
    scopes = [s for s in candidate_scopes if s and not (s in seen or seen.add(s))]

    phase_id = None
    scope_used = None
    for candidate in scopes:
        row = conn.execute(
            """
            SELECT scope, phase_id FROM cycle_assessments
             WHERE cycle_id = 'valuation_cycle' AND scope = ? AND data_pending = 0
             ORDER BY as_of_date DESC
             LIMIT 1
            """,
            (candidate,),
        ).fetchone()
        if row is not None and row["phase_id"]:
            phase_id = row["phase_id"]
            scope_used = row["scope"]
            break

    if phase_id is None or phase_id not in multipliers:
        return {
            "base_limit_pct": base_limit_pct,
            "multiplier": 1.0,
            "adjusted_limit_pct": base_limit_pct,
            "phase_id": phase_id,
            "scope_used": scope_used,
            "unknown_phase": True,
            "note": "no valuation_cycle phase available for any fallback scope, or phase not in "
                    "phase_multipliers map -- using base limit unmodified (multiplier=1.0)",
        }

    multiplier = float(multipliers[phase_id])
    return {
        "base_limit_pct": base_limit_pct,
        "multiplier": multiplier,
        "adjusted_limit_pct": base_limit_pct * multiplier,
        "phase_id": phase_id,
        "scope_used": scope_used,
        "unknown_phase": False,
        "note": None,
    }
