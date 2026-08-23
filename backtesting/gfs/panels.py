"""
panels.py
=========

Pre-computation layer.

The daily loop must never do heavy work, otherwise an 8-year Nifty-500 run is
unusable. So every indicator a decision could possibly need is computed **once
per symbol** as a vectorized, causal series, and the engine then only reads a
row.

This is not merely an optimisation - it is a correctness device. Because each
column is produced by a backward-looking operation over the *whole* series, the
value at row ``t`` cannot depend on anything after ``t``, and that invariant is
checked mechanically by the truncation test in ``tests/test_gfs_leakage.py``:
building panels from a history cut short at ``T`` must reproduce, bit for bit,
the rows up to ``T`` of panels built from the full history.

Three kinds of panel are produced, mirroring the top-down funnel in the
strategy's own diagram:

* :class:`SymbolPanel`      - microscopic view (one stock).
* :func:`build_sector_panel` - aerial view (sector relative strength).
* :func:`build_regime_panel` - helicopter view (index trend + market breadth).
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import indicators as ind
from .config import GFSConfig, TRIGGER_DIP

logger = logging.getLogger("gfs.panels")

# Columns the engine is allowed to read. Declared explicitly so a typo becomes a
# KeyError at build time rather than a silently-NaN filter at run time.
PANEL_COLUMNS = [
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "rsi_d",
    "rsi_w",
    "rsi_m",
    "rsi_d_prev",
    "n_weekly",
    "n_monthly",
    "atr",
    "atr_pct",
    "sma200",
    "above_sma200",
    "turnover_cr",
    "swing_low",
    "resistance",
    "headroom_pct",
    "tradable",
    "gf_ok",
    "s_dip",
    "s_recross",
]


@dataclass
class SymbolPanel:
    symbol: str
    sector: str
    frame: pd.DataFrame

    def row(self, ts: pd.Timestamp) -> Optional[pd.Series]:
        """The panel row for an exact session, or ``None`` if the name did not
        trade that day (suspension, listing gap, holiday on one exchange)."""
        try:
            return self.frame.loc[ts]
        except KeyError:
            return None


def base_panel_key(cfg: GFSConfig) -> tuple:
    """The config fields the expensive indicator columns actually depend on.

    Thresholds like ``g_rsi_min`` are deliberately absent: changing them only
    re-evaluates a boolean, it does not change a single RSI value. Splitting the
    build this way turns a 324-configuration sweep from 324 full indicator
    passes over the universe into one, which is the difference between a sweep
    that runs and a sweep that nobody ever runs.
    """
    return (
        cfg.htf_mode,
        cfg.rsi_period_daily,
        cfg.rsi_period_weekly,
        cfg.rsi_period_monthly,
        cfg.atr_period,
        cfg.swing_low_lookback,
        cfg.resistance_lookback,
        cfg.min_daily_bars,
    )


def build_base_panel(
    symbol: str,
    daily: pd.DataFrame,
    cfg: GFSConfig,
) -> Optional[pd.DataFrame]:
    """The expensive half: every indicator column, no thresholds applied."""
    if daily is None or daily.empty:
        return None
    df = daily.copy()
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    # A monthly RSI needs years of daily history behind it; anything shorter is
    # rejected up front rather than producing a warm-looking NaN-free tail.
    if len(df) < max(cfg.min_daily_bars, cfg.atr_period + 1):
        return None

    close = df["Close"].astype("float64")
    high = df["High"].astype("float64")
    low = df["Low"].astype("float64")
    volume = df["Volume"].astype("float64") if "Volume" in df else pd.Series(
        0.0, index=df.index
    )

    out = pd.DataFrame(index=df.index)
    out["Open"] = df["Open"].astype("float64")
    out["High"] = high
    out["Low"] = low
    out["Close"] = close
    out["Volume"] = volume

    # ── Son: daily RSI ───────────────────────────────────────────────────────
    out["rsi_d"] = ind.rsi_series(close, cfg.rsi_period_daily)
    out["rsi_d_prev"] = out["rsi_d"].shift(1)

    # ── Father / Grandfather: weekly + monthly RSI projected onto daily ──────
    rsi_w, n_w = ind.htf_rsi_daily(
        df, ind.WEEKLY_RULE, cfg.rsi_period_weekly, cfg.htf_mode
    )
    rsi_m, n_m = ind.htf_rsi_daily(
        df, ind.MONTHLY_RULE, cfg.rsi_period_monthly, cfg.htf_mode
    )
    out["rsi_w"] = rsi_w
    out["rsi_m"] = rsi_m
    out["n_weekly"] = n_w
    out["n_monthly"] = n_m

    # ── Risk / tradability inputs ────────────────────────────────────────────
    out["atr"] = ind.atr_series(high, low, close, cfg.atr_period)
    out["atr_pct"] = out["atr"] / close * 100.0
    out["sma200"] = close.rolling(200, min_periods=200).mean()
    out["above_sma200"] = (close > out["sma200"]).fillna(False)
    out["turnover_cr"] = ind.rolling_median_turnover_cr(close, volume, 20)
    out["swing_low"] = ind.rolling_swing_low(low, cfg.swing_low_lookback)
    out["resistance"] = ind.prior_swing_high(high, cfg.resistance_lookback)
    return out


def apply_conditions(base: pd.DataFrame, cfg: GFSConfig) -> pd.DataFrame:
    """The cheap half: turn indicator columns into the GFS booleans."""
    out = base.copy()

    enough_history = (
        (out["n_weekly"] >= cfg.min_weekly_bars)
        & (out["n_monthly"] >= cfg.min_monthly_bars)
        & out["atr"].notna()
        & out["rsi_d"].notna()
        & out["rsi_w"].notna()
        & out["rsi_m"].notna()
    )
    # `turnover_cr` is NaN for the first 20 sessions and for names yfinance
    # reports without volume. Treat unknown liquidity as NOT tradable here (as
    # opposed to the live scanner, which is permissive) - a backtest that
    # silently trades unknown-liquidity names overstates its own capacity.
    out["tradable"] = (
        enough_history
        & (out["Close"] >= cfg.min_price)
        & (out["turnover_cr"] >= cfg.min_turnover_cr)
        & (out["atr_pct"] <= cfg.max_atr_pct)
    )

    # Headroom: the distance to the resistance level the exit is defined
    # against. A dip with the prior swing high 3% overhead cannot pay for its
    # own stop, however strong the higher timeframes look. See
    # `conviction.py` - this is the one entry filter that survived out-of-sample.
    out["headroom_pct"] = (out["resistance"] - out["Close"]) / out["Close"] * 100.0
    if cfg.min_headroom_pct > 0:
        out["tradable"] &= out["headroom_pct"] >= cfg.min_headroom_pct

    # ── The GFS conditions themselves ────────────────────────────────────────
    out["gf_ok"] = (out["rsi_m"] >= cfg.g_rsi_min) & (out["rsi_w"] >= cfg.f_rsi_min)
    out["s_dip"] = out["rsi_d"] <= cfg.s_rsi_entry
    out["s_recross"] = (out["rsi_d"] > cfg.s_rsi_entry) & (
        out["rsi_d_prev"] <= cfg.s_rsi_entry
    )

    for col in ("above_sma200", "tradable", "gf_ok", "s_dip", "s_recross"):
        out[col] = out[col].fillna(False).astype(bool)
    return out[PANEL_COLUMNS]


def build_symbol_panel(
    symbol: str,
    sector: str,
    daily: pd.DataFrame,
    cfg: GFSConfig,
) -> Optional[SymbolPanel]:
    """Compute every causal column this strategy can consult for one symbol."""
    base = build_base_panel(symbol, daily, cfg)
    if base is None:
        return None
    return SymbolPanel(
        symbol=symbol, sector=sector or "Unknown", frame=apply_conditions(base, cfg)
    )


def build_panels(
    data,
    universe,
    cfg: GFSConfig,
    base_cache: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, SymbolPanel]:
    """Build one :class:`SymbolPanel` per symbol that has usable history.

    ``base_cache`` (keyed by symbol, valid for one :func:`base_panel_key`) lets a
    sweep skip the expensive indicator pass entirely between trials.
    """
    panels: Dict[str, SymbolPanel] = {}
    skipped = 0
    for item in universe:
        base = base_cache.get(item.symbol) if base_cache is not None else None
        if base is None:
            base = build_base_panel(item.symbol, data.full(item.symbol), cfg)
            if base is None:
                skipped += 1
                continue
            if base_cache is not None:
                base_cache[item.symbol] = base
        panels[item.symbol] = SymbolPanel(
            symbol=item.symbol,
            sector=item.industry or "Unknown",
            frame=apply_conditions(base, cfg),
        )
    if skipped:
        logger.info(
            "Built %d symbol panels (%d skipped for insufficient history/data).",
            len(panels),
            skipped,
        )
    return panels


# ── Aerial view: sector relative strength ────────────────────────────────────


@dataclass
class SectorPanel:
    """Daily sector relative-strength ranks (1 = strongest sector)."""

    rs: pd.DataFrame  # index: master calendar, columns: sector -> % return
    rank: pd.DataFrame  # index: master calendar, columns: sector -> dense rank
    members: Dict[str, List[str]]

    def rank_of(self, sector: str, ts: pd.Timestamp) -> Optional[float]:
        if sector not in self.rank.columns:
            return None
        try:
            val = self.rank.at[ts, sector]
        except KeyError:
            return None
        return None if pd.isna(val) else float(val)

    def sector_count(self, ts: pd.Timestamp) -> int:
        try:
            return int(self.rank.loc[ts].notna().sum())
        except KeyError:
            return 0


def build_sector_panel(
    panels: Dict[str, SymbolPanel],
    master_index: pd.DatetimeIndex,
    cfg: GFSConfig,
) -> SectorPanel:
    """Equal-weighted sector indices, their trailing return, and a daily rank.

    Each sector index is the cumulative product of the *equal-weighted mean of
    its members' daily returns*, which keeps a sector comparable even as members
    enter the sample at different times (a newly-listed member contributes only
    from its first return onward instead of dragging the whole index).
    """
    by_sector: Dict[str, List[str]] = {}
    for sym, panel in panels.items():
        by_sector.setdefault(panel.sector or "Unknown", []).append(sym)

    rs_cols: Dict[str, pd.Series] = {}
    kept: Dict[str, List[str]] = {}
    for sector, members in by_sector.items():
        if len(members) < cfg.min_sector_members:
            continue
        rets = []
        for sym in members:
            close = panels[sym].frame["Close"].reindex(master_index).ffill(limit=5)
            rets.append(close.pct_change(fill_method=None))
        if not rets:
            continue
        member_rets = pd.concat(rets, axis=1)
        # Require at least `min_sector_members` live members on a given day,
        # otherwise the "sector" is one stock wearing a hat.
        live = member_rets.notna().sum(axis=1)
        mean_ret = member_rets.mean(axis=1, skipna=True)
        mean_ret = mean_ret.where(live >= cfg.min_sector_members)
        index_level = (1.0 + mean_ret.fillna(0.0)).cumprod()
        index_level = index_level.where(mean_ret.notna().cummax())
        rs_cols[sector] = (
            index_level / index_level.shift(cfg.sector_rs_lookback) - 1.0
        ) * 100.0
        kept[sector] = members

    if not rs_cols:
        empty = pd.DataFrame(index=master_index)
        return SectorPanel(rs=empty, rank=empty.copy(), members={})

    rs = pd.DataFrame(rs_cols, index=master_index)
    rank = rs.rank(axis=1, ascending=False, method="min")
    logger.info(
        "Sector panel: %d sectors with >= %d members.", len(rs.columns), cfg.min_sector_members
    )
    return SectorPanel(rs=rs, rank=rank, members=kept)


# ── Helicopter view: index trend + market breadth ────────────────────────────


@dataclass
class RegimePanel:
    frame: pd.DataFrame  # cols: bench_close, bench_sma, bench_ok, breadth_pct, regime_ok

    def ok_on(self, ts: pd.Timestamp) -> bool:
        try:
            return bool(self.frame.at[ts, "regime_ok"])
        except KeyError:
            return False

    def row(self, ts: pd.Timestamp) -> Optional[pd.Series]:
        try:
            return self.frame.loc[ts]
        except KeyError:
            return None


def build_regime_panel(
    benchmark: Optional[pd.DataFrame],
    panels: Dict[str, SymbolPanel],
    master_index: pd.DatetimeIndex,
    cfg: GFSConfig,
) -> RegimePanel:
    """Quantified stand-in for the 'is the market bullish?' step of the funnel.

    Two measurable proxies replace reading the news:

    * the benchmark trading above its own SMA(n) - a trend switch, and
    * breadth, the share of the universe above its 200-day SMA - a
      participation check that catches the case where the index is held up by a
      handful of heavyweights.
    """
    frame = pd.DataFrame(index=master_index)

    if benchmark is not None and not benchmark.empty:
        bench_close = benchmark["Close"].reindex(master_index).ffill(limit=5)
    else:
        bench_close = pd.Series(np.nan, index=master_index, dtype="float64")
    frame["bench_close"] = bench_close
    frame["bench_sma"] = bench_close.rolling(cfg.regime_sma, min_periods=cfg.regime_sma).mean()
    frame["bench_ok"] = (bench_close > frame["bench_sma"]).fillna(False)

    if panels:
        above = pd.concat(
            [
                panels[s].frame["above_sma200"]
                .reindex(master_index, fill_value=False)
                .astype(bool)
                for s in panels
            ],
            axis=1,
        )
        has_data = pd.concat(
            [
                panels[s].frame["sma200"].reindex(master_index).notna()
                for s in panels
            ],
            axis=1,
        )
        denom = has_data.sum(axis=1).replace(0, np.nan)
        frame["breadth_pct"] = (above.sum(axis=1) / denom * 100.0).fillna(0.0)
    else:
        frame["breadth_pct"] = 0.0

    if cfg.use_regime_filter:
        frame["regime_ok"] = frame["bench_ok"] & (
            frame["breadth_pct"] >= cfg.min_breadth_pct
        )
    else:
        frame["regime_ok"] = True
    frame["regime_ok"] = frame["regime_ok"].fillna(False).astype(bool)
    return RegimePanel(frame=frame)


def master_calendar(
    benchmark: Optional[pd.DataFrame],
    panels: Dict[str, SymbolPanel],
) -> pd.DatetimeIndex:
    """Trading calendar for the run: the benchmark's sessions when available,
    otherwise the union of every symbol's sessions."""
    if benchmark is not None and not benchmark.empty:
        return pd.DatetimeIndex(benchmark.index).sort_values()
    idx = pd.DatetimeIndex([])
    for panel in panels.values():
        idx = idx.union(panel.frame.index)
    return idx.sort_values()


def trigger_column(cfg: GFSConfig) -> str:
    """Panel column implementing the configured Son-timeframe entry trigger."""
    return "s_dip" if cfg.entry_trigger == TRIGGER_DIP else "s_recross"


def build_qualify_matrix(
    panels: Dict[str, SymbolPanel],
    master_index: pd.DatetimeIndex,
    cfg: GFSConfig,
) -> pd.DataFrame:
    """Boolean matrix (days x symbols) of "this name meets the GFS condition".

    Collapsing the daily scan into one row lookup instead of one lookup per
    symbol is what keeps a Nifty-500 x 10-year run to seconds rather than tens
    of minutes - which matters because a parameter sweep runs it hundreds of
    times. The column is a pure AND of already-causal panel columns, so the
    matrix inherits their leak-free property.
    """
    trigger = trigger_column(cfg)
    if not panels:
        return pd.DataFrame(index=master_index)
    cols = {}
    for sym, panel in panels.items():
        frame = panel.frame
        qualify = frame["tradable"] & frame["gf_ok"] & frame[trigger]
        cols[sym] = qualify.reindex(master_index, fill_value=False).astype(bool)
    return pd.DataFrame(cols, index=master_index).astype(bool)
