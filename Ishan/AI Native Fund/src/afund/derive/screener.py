"""Bottom-up contrarian screener over the full active STOCK/ETF universe.

Scans every active STOCK/ETF instrument with price history and flags the
cycle_contrarian signals (registry/strategies/cycle_contrarian.yaml) at the
INSTRUMENT level — the sibling to derive/regime.py, which evaluates the same
family of signals at the INDEX level. Nothing here calls an LLM; this module
only computes and ranks.

Thresholds are parsed out of the registry's entry_criteria/exit_criteria
strings rather than hardcoded, so a future edit to the strategy YAML (e.g.
loosening the panic threshold from -40% to -35%) takes effect here without a
code change. The one exception is the "long-term neglect" band: the registry
text ("approximately zero absolute return over a 10-12 year window") has no
parseable number, so NEGLECT_ABS_RETURN_THRESHOLD is a module constant here,
mirroring the same judgment call regime.py already made (its
NEGLECT_ABS_RETURN_THRESHOLD = 0.05 comment says the same thing) — we use a
looser 10% band per this task's spec, since a single-instrument 10y return is
noisier than an index-level one.

Performance: this runs over ~750+ instruments and must complete in seconds,
so it does ONE SQL pass per data source (all daily_prices rows for all active
STOCK/ETF instruments in one query, all derived_ratios rows in another) and
vectorizes the per-instrument math with pandas groupby — never a Python loop
issuing one query per instrument.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from typing import Any

import pandas as pd

# "Long-term neglect": |10y cumulative return| below this band counts as
# "approximately zero" (registry text has no exact number for this one — see
# module docstring). 10-12y window per the registry text; we use 10y exactly,
# same simplification derive/regime.py makes.
NEGLECT_YEARS = 10.0
NEGLECT_ABS_RETURN_THRESHOLD = 0.10  # +/-10% cumulative over the window

# derived_ratios.metric_name values we treat as "PE-like" / "ROCE-like" /
# "debt-to-equity-like" for the tolerant metric attachment. This table is
# sparse and inconsistently populated (see schema.sql derived_ratios comment
# and the live DB: only stock_p_e/roce/roe/etc. exist today) so we match by
# substring rather than an exact fixed list.
_PE_METRIC_HINTS = ("p_e", "pe_ratio", "price_to_earnings")
_ROCE_METRIC_HINTS = ("roce",)
_ROE_METRIC_HINTS = ("roe",)
_DEBT_EQUITY_METRIC_HINTS = ("debt_to_equity", "debt_equity", "de_ratio")


def _load_registry_thresholds() -> dict[str, float]:
    """Parse panic/euphoria numeric thresholds out of
    registry/strategies/cycle_contrarian.yaml's entry/exit criteria text.

    Returns fractions (e.g. -0.40 for "-40%"), not percentages. Falls back to
    the values documented in derive/regime.py (which mirrors the same
    registry file) if a criterion's wording ever changes shape enough that
    the regex can't find it — so a screener run never hard-fails on a
    registry wording tweak.
    """
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from registry.registry import Registry

    reg = Registry.load()
    strategy = reg.strategies.get("cycle_contrarian")

    # Defaults mirror derive/regime.py's documented thresholds.
    thresholds = {
        "panic_1y": -0.40,
        "panic_5y_cagr": -0.10,
        "euphoria_1y": 1.00,
    }
    if strategy is None:
        return thresholds

    text_blob = " ".join(strategy.entry_criteria) + " " + " ".join(strategy.exit_criteria)

    m = re.search(r"1-year absolute return\s*<=\s*(-?\d+(?:\.\d+)?)\s*%", text_blob, re.IGNORECASE)
    if m:
        thresholds["panic_1y"] = float(m.group(1)) / 100.0

    m = re.search(r"5-year CAGR\s*<=\s*(-?\d+(?:\.\d+)?)\s*%", text_blob, re.IGNORECASE)
    if m:
        thresholds["panic_5y_cagr"] = float(m.group(1)) / 100.0

    m = re.search(r"1-year absolute return\s*>=\s*(-?\d+(?:\.\d+)?)\s*%", text_blob, re.IGNORECASE)
    if m:
        thresholds["euphoria_1y"] = float(m.group(1)) / 100.0

    return thresholds


DEEP_DRAWDOWN_THRESHOLD = -0.30  # pct_from_52w_high <= -30% (not a registry criterion; screener-specific)


def _active_universe(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT id AS instrument_id, symbol, sector
          FROM instruments
         WHERE active = 1 AND instrument_type IN ('STOCK', 'ETF')
        """
    ).fetchall()
    return pd.DataFrame([dict(r) for r in rows], columns=["instrument_id", "symbol", "sector"])


def _all_prices(conn: sqlite3.Connection, instrument_ids: list[int]) -> pd.DataFrame:
    if not instrument_ids:
        return pd.DataFrame(columns=["instrument_id", "date", "close"])
    placeholders = ",".join("?" for _ in instrument_ids)
    # pandas.read_sql_query rather than fetchall()+dict-per-row: this table
    # is 1M+ rows across the full universe, and read_sql_query's bulk C-level
    # fetch is roughly 3x faster here than iterating sqlite3.Row objects —
    # the difference between the screener taking ~11s vs. ~4s end to end.
    df = pd.read_sql_query(
        f"""
        SELECT instrument_id, date, close
          FROM daily_prices
         WHERE instrument_id IN ({placeholders}) AND close IS NOT NULL
         ORDER BY instrument_id ASC, date ASC
        """,
        conn,
        params=instrument_ids,
    )
    if not df.empty:
        # Plain datetime.date objects (not pandas Timestamp/Timedelta) for date
        # arithmetic below — sidesteps a pandas 2.x NumPy-timedelta-unit
        # deprecation warning that fires on `pd.Timedelta(days=<int>)` and
        # keeps the arithmetic identical in spirit to derive/returns.py's
        # stdlib-datetime approach.
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _all_derived_ratios(conn: sqlite3.Connection, instrument_ids: list[int]) -> pd.DataFrame:
    if not instrument_ids:
        return pd.DataFrame(columns=["instrument_id", "as_of_date", "metric_name", "metric_value"])
    placeholders = ",".join("?" for _ in instrument_ids)
    return pd.read_sql_query(
        f"""
        SELECT instrument_id, as_of_date, metric_name, metric_value
          FROM derived_ratios
         WHERE instrument_id IN ({placeholders})
        """,
        conn,
        params=instrument_ids,
    )


def _closest_on_or_before(dates: pd.Series, closes: pd.Series, target: dt.date) -> float | None:
    """Latest close with date <= target. dates/closes are aligned, ascending."""
    mask = dates <= target
    if not mask.any():
        return None
    idx = mask.to_numpy().nonzero()[0][-1]
    return float(closes.iloc[idx])


def _per_instrument_metrics(group: pd.DataFrame, as_of_date: dt.date) -> dict[str, Any]:
    """Compute ret_1y, cagr_5y, ret_10y, pct_from_52w_high/low, above_200dma
    for one instrument's price history (a groupby group), vectorized within
    the group via pandas/numpy rather than calling derive.returns' per-call
    SQL-querying functions (which would each re-hit the DB per instrument)."""
    dates = group["date"]
    closes = group["close"]

    end_close = _closest_on_or_before(dates, closes, as_of_date)
    if end_close is None:
        return {
            "ret_1y": None, "cagr_5y": None, "ret_10y": None,
            "pct_from_52w_high": None, "pct_from_52w_low": None, "above_200dma": None,
            "last_close": None,
        }

    def _trailing_return(years: float) -> float | None:
        start_target = as_of_date - dt.timedelta(days=round(years * 365.25))
        start_close = _closest_on_or_before(dates, closes, start_target)
        if start_close is None or not start_close:
            return None
        return (end_close - start_close) / start_close

    def _cagr(years: float) -> float | None:
        start_target = as_of_date - dt.timedelta(days=round(years * 365.25))
        mask = dates <= start_target
        if not mask.any():
            return None
        idx = mask.to_numpy().nonzero()[0][-1]
        start_close = float(closes.iloc[idx])
        start_date = dates.iloc[idx]
        if not start_close or start_close <= 0 or end_close <= 0:
            return None
        actual_years = (as_of_date - start_date).days / 365.25
        if actual_years <= 0:
            return None
        return (end_close / start_close) ** (1 / actual_years) - 1

    ret_1y = _trailing_return(1.0)
    cagr_5y = _cagr(5.0)

    # ret_10y only meaningful when we actually have ~10-12y of history.
    span_years = (dates.iloc[-1] - dates.iloc[0]).days / 365.25
    ret_10y = _trailing_return(NEGLECT_YEARS) if span_years >= NEGLECT_YEARS else None

    window = group[dates > as_of_date - dt.timedelta(days=365)]
    if window.empty:
        window = group
    high_52w = float(window["close"].max())
    low_52w = float(window["close"].min())
    pct_from_52w_high = (end_close - high_52w) / high_52w if high_52w else None
    pct_from_52w_low = (end_close - low_52w) / low_52w if low_52w else None

    above_200dma = None
    if len(group) >= 200:
        dma_200 = float(closes.tail(200).mean())
        above_200dma = end_close >= dma_200

    return {
        "ret_1y": ret_1y, "cagr_5y": cagr_5y, "ret_10y": ret_10y,
        "pct_from_52w_high": pct_from_52w_high, "pct_from_52w_low": pct_from_52w_low,
        "above_200dma": above_200dma, "last_close": end_close,
    }


def _tolerant_metric_lookup(ratios_for_instrument: pd.DataFrame, hints: tuple[str, ...]) -> float | None:
    """Latest (by as_of_date) metric_value whose metric_name contains any of
    `hints` (case-insensitive substring match) — tolerant because
    derived_ratios.metric_name isn't a controlled vocabulary in practice
    (schema.sql just calls it TEXT) and today's data has names like
    'stock_p_e' rather than a canonical 'pe'."""
    if ratios_for_instrument.empty:
        return None
    lower_names = ratios_for_instrument["metric_name"].str.lower()
    mask = pd.Series(False, index=ratios_for_instrument.index)
    for hint in hints:
        mask |= lower_names.str.contains(hint, na=False)
    matches = ratios_for_instrument[mask]
    if matches.empty:
        return None
    matches = matches.sort_values("as_of_date")
    return matches["metric_value"].iloc[-1]


def run_screen(conn: sqlite3.Connection, as_of: str | None = None, top_n: int = 15) -> dict:
    """Run the bottom-up contrarian screen over the active STOCK/ETF universe.

    Returns:
        {
          "as_of": str,
          "candidates": [dict, ...]  (up to top_n, contrarian-scored, euphoria excluded),
          "euphoria_list": [dict, ...]  (up to 5, euphoria_avoid names),
          "universe_scanned": int,
        }
    """
    as_of = as_of or dt.date.today().isoformat()
    as_of_date = dt.date.fromisoformat(as_of)

    thresholds = _load_registry_thresholds()

    universe = _active_universe(conn)
    universe_scanned = len(universe)
    if universe.empty:
        return {"as_of": as_of, "candidates": [], "euphoria_list": [], "universe_scanned": 0}

    instrument_ids = universe["instrument_id"].tolist()
    prices = _all_prices(conn, instrument_ids)
    ratios_df = _all_derived_ratios(conn, instrument_ids)

    results: list[dict] = []
    if not prices.empty:
        for instrument_id, group in prices.groupby("instrument_id", sort=False):
            metrics = _per_instrument_metrics(group.reset_index(drop=True), as_of_date)
            if metrics["last_close"] is None:
                continue

            ret_1y = metrics["ret_1y"]
            cagr_5y = metrics["cagr_5y"]
            ret_10y = metrics["ret_10y"]
            pct_from_52w_high = metrics["pct_from_52w_high"]

            flags: list[str] = []
            if (ret_1y is not None and ret_1y <= thresholds["panic_1y"]) or \
               (cagr_5y is not None and cagr_5y <= thresholds["panic_5y_cagr"]):
                flags.append("panic_buy")

            if ret_10y is not None and abs(ret_10y) < NEGLECT_ABS_RETURN_THRESHOLD:
                flags.append("long_term_neglect")

            if ret_1y is not None and ret_1y >= thresholds["euphoria_1y"]:
                flags.append("euphoria_avoid")

            if pct_from_52w_high is not None and pct_from_52w_high <= DEEP_DRAWDOWN_THRESHOLD:
                flags.append("deep_drawdown")

            if not flags:
                continue

            row = universe.loc[universe["instrument_id"] == instrument_id].iloc[0]
            ratios_for_instrument = (
                ratios_df[ratios_df["instrument_id"] == instrument_id] if not ratios_df.empty else ratios_df
            )

            contrarian_positive = sum(
                1 for f in ("panic_buy", "long_term_neglect", "deep_drawdown") if f in flags
            )

            results.append(
                {
                    "instrument_id": int(instrument_id),
                    "symbol": row["symbol"],
                    "sector": row["sector"],
                    "ret_1y": ret_1y,
                    "cagr_5y": cagr_5y,
                    "ret_10y": ret_10y,
                    "pct_from_52w_high": pct_from_52w_high,
                    "pct_from_52w_low": metrics["pct_from_52w_low"],
                    "above_200dma": metrics["above_200dma"],
                    "flags": flags,
                    "score": contrarian_positive,
                    "pe": _tolerant_metric_lookup(ratios_for_instrument, _PE_METRIC_HINTS),
                    "roce": _tolerant_metric_lookup(ratios_for_instrument, _ROCE_METRIC_HINTS),
                    "roe": _tolerant_metric_lookup(ratios_for_instrument, _ROE_METRIC_HINTS),
                    "debt_to_equity": _tolerant_metric_lookup(ratios_for_instrument, _DEBT_EQUITY_METRIC_HINTS),
                }
            )

    euphoria_list = sorted(
        (r for r in results if "euphoria_avoid" in r["flags"]),
        key=lambda r: (r["ret_1y"] if r["ret_1y"] is not None else 0.0),
        reverse=True,
    )[:5]

    candidates_pool = [r for r in results if "euphoria_avoid" not in r["flags"] and r["score"] > 0]
    candidates_pool.sort(
        key=lambda r: (-r["score"], r["ret_1y"] if r["ret_1y"] is not None else 0.0)
    )
    candidates = candidates_pool[:top_n]

    return {
        "as_of": as_of,
        "candidates": candidates,
        "euphoria_list": euphoria_list,
        "universe_scanned": universe_scanned,
    }


def _print_table(screen: dict) -> None:
    candidates = screen["candidates"]
    print(f"Bottom-up contrarian screen — as_of={screen['as_of']}  universe_scanned={screen['universe_scanned']}")
    print(f"{len(candidates)} candidates, {len(screen['euphoria_list'])} euphoria_avoid names\n")

    header = f"{'symbol':<12}{'score':>5}  {'ret_1y':>8}  {'cagr_5y':>8}  {'ret_10y':>8}  {'%from52wHi':>11}  flags"
    print(header)
    print("-" * len(header))
    for c in candidates:
        def _pct(v):
            return f"{v * 100:.1f}%" if v is not None else "n/a"

        print(
            f"{c['symbol']:<12}{c['score']:>5}  {_pct(c['ret_1y']):>8}  {_pct(c['cagr_5y']):>8}  "
            f"{_pct(c['ret_10y']):>8}  {_pct(c['pct_from_52w_high']):>11}  {','.join(c['flags'])}"
        )

    if screen["euphoria_list"]:
        print("\nEuphoria / AVOID candidates:")
        for c in screen["euphoria_list"]:
            print(f"  {c['symbol']:<12} ret_1y={c['ret_1y'] * 100:.1f}%" if c["ret_1y"] is not None else f"  {c['symbol']}")


def main() -> None:
    from afund.db.connection import get_conn

    conn = get_conn()
    try:
        screen = run_screen(conn)
        _print_table(screen)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
