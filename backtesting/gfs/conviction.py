"""
conviction.py
=============

Which GFS signals are worth taking?

The portfolio backtest closes ~240 trades over eight years. That is far too few
to mine twenty candidate features against without finding something by accident,
so this module does the search **portfolio-free**: every GFS signal in the
universe is simulated as an isolated trade under the same fill and exit rules the
engine uses, which yields several thousand labelled outcomes instead of a few
hundred. Filters discovered here are then re-tested inside the real portfolio,
where capacity limits and sector caps apply.

Two disciplines make the difference between research and self-deception:

1. **Time-split, not random split.** Features are ranked on the earlier part of
   the sample and reported on the later part. A random split would leak, because
   signals on the same day in the same sector are the same bet.
2. **The trial count is reported.** Scanning `F` features by quintile is `5F`
   implicit hypotheses. With twenty features that is a hundred looks, and the
   best of a hundred random looks is impressive on its own. `train_test_report`
   therefore always prints how many comparisons were made, and a rule that
   survives only in-sample is labelled as failed rather than quietly dropped.

On win rate specifically
------------------------
Win rate is largely an artefact of exit geometry, not signal quality. Widening
the stop and shortening the target raises win rate mechanically while lowering
expectancy - the classic way a strategy reaches "80% winners" and still loses
money. Every report here therefore shows win rate **and** expectancy in R
together, and `stop_target_grid` exists to make the trade-off between them
explicit rather than accidental.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import GFSConfig, EXIT_RESISTANCE, EXIT_RSI

logger = logging.getLogger("gfs.conviction")

#: Hard bound on how long a portfolio-free trade is tracked. This is NOT a time
#: stop - the trade is marked `open_at_horizon` and excluded from win-rate
#: statistics rather than closed at market. Without a bound, a position that
#: never reaches its target would need infinite data.
MAX_TRACK_SESSIONS = 504  # ~2 years

FEATURE_COLUMNS = [
    "rsi_m",
    "rsi_w",
    "rsi_d",
    "rsi_m_slope",
    "rsi_w_slope",
    "dip_depth",
    "headroom_pct",
    "reward_risk",
    "dist_52w_high_pct",
    "pct_above_sma200",
    "pct_above_sma50",
    "sma_stack",
    "atr_pct",
    "turnover_cr",
    "vol_ratio",
    "down_streak",
    "drawdown_63d_pct",
    "days_above_sma200",
    "ret_63d",
    "ret_126d",
    "ret_252d",
    "sector_rs",
    "sector_rank",
    "breadth_pct",
    "bench_above_sma",
]


# ── Feature engineering ──────────────────────────────────────────────────────


def add_feature_columns(frame: pd.DataFrame, cfg: GFSConfig) -> pd.DataFrame:
    """Per-symbol features, all computed from data at or before each row.

    Every operation is a backward-looking rolling window or a shift, so a row
    dated D never contains information from D+1. `test_conviction_features_are_leak_free`
    verifies this by truncation rather than by inspection.
    """
    out = frame.copy()
    close = out["Close"].astype("float64")
    high = out["High"].astype("float64")
    low = out["Low"].astype("float64")
    volume = out["Volume"].astype("float64")

    sma50 = close.rolling(50, min_periods=50).mean()
    sma20 = close.rolling(20, min_periods=20).mean()
    sma200 = out["sma200"]

    # How far the recovery can run before it meets the prior swing high. The
    # exit is defined in terms of this level, so a signal with no headroom is
    # structurally incapable of paying out.
    resistance = out["resistance"]
    out["headroom_pct"] = (resistance - close) / close * 100.0

    stop_distance = cfg.atr_stop_mult * out["atr"]
    out["reward_risk"] = (resistance - close) / stop_distance.where(stop_distance > 0)

    high_252 = high.rolling(252, min_periods=100).max()
    out["dist_52w_high_pct"] = (close - high_252) / high_252 * 100.0

    out["pct_above_sma200"] = (close - sma200) / sma200 * 100.0
    out["pct_above_sma50"] = (close - sma50) / sma50 * 100.0
    out["sma_stack"] = ((sma20 > sma50) & (sma50 > sma200)).astype(float)

    # Monthly / weekly RSI momentum: is the higher timeframe still improving, or
    # already rolling over while still above the threshold?
    out["rsi_m_slope"] = out["rsi_m"] - out["rsi_m"].shift(63)
    out["rsi_w_slope"] = out["rsi_w"] - out["rsi_w"].shift(21)

    out["dip_depth"] = cfg.s_rsi_entry - out["rsi_d"]

    avg_vol = volume.rolling(20, min_periods=20).mean()
    out["vol_ratio"] = volume / avg_vol.where(avg_vol > 0)

    down = (close < close.shift(1)).astype(int)
    # Length of the current consecutive-down-day run.
    grp = (down == 0).cumsum()
    out["down_streak"] = down.groupby(grp).cumsum()

    high_63 = close.rolling(63, min_periods=63).max()
    out["drawdown_63d_pct"] = (close - high_63) / high_63 * 100.0

    above = out["above_sma200"].astype(int)
    below_grp = (above == 0).cumsum()
    out["days_above_sma200"] = above.groupby(below_grp).cumsum()

    out["ret_63d"] = (close / close.shift(63) - 1.0) * 100.0
    out["ret_126d"] = (close / close.shift(126) - 1.0) * 100.0
    out["ret_252d"] = (close / close.shift(252) - 1.0) * 100.0
    return out


# ── Portfolio-free trade simulation ──────────────────────────────────────────


@dataclass
class TradeOutcome:
    entry_date: pd.Timestamp
    exit_date: Optional[pd.Timestamp]
    entry_price: float
    exit_price: float
    stop_price: float
    reason: str
    r_multiple: float
    pct_return: float
    days_held: int
    mae_r: float
    mfe_r: float
    open_at_horizon: bool


def simulate_signal(
    frame: pd.DataFrame,
    i: int,
    cfg: GFSConfig,
    *,
    stop_mult: Optional[float] = None,
    exit_rsi: Optional[float] = None,
    use_resistance_target: bool = True,
) -> Optional[TradeOutcome]:
    """Simulate one signal as a standalone trade, mirroring the engine's rules.

    Signal at the close of bar `i` -> fill at the open of `i+1`. Thereafter, for
    each bar: the stop is checked first (an unfavourable but defensible reading
    of a daily bar), then the resistance target intrabar, then the RSI exit which
    is only knowable at the close and therefore fills at the following open.

    There is deliberately no time stop. A trade still open after
    `MAX_TRACK_SESSIONS` is returned with `open_at_horizon=True` so the caller can
    exclude it rather than book a fictitious result.
    """
    n = len(frame)
    if i + 1 >= n:
        return None

    stop_mult = cfg.atr_stop_mult if stop_mult is None else stop_mult
    exit_rsi = cfg.exit_rsi if exit_rsi is None else exit_rsi

    opens = frame["Open"].to_numpy(dtype="float64")
    highs = frame["High"].to_numpy(dtype="float64")
    lows = frame["Low"].to_numpy(dtype="float64")
    closes = frame["Close"].to_numpy(dtype="float64")
    rsis = frame["rsi_d"].to_numpy(dtype="float64")
    resist = frame["resistance"].to_numpy(dtype="float64")
    index = frame.index

    atr = float(frame["atr"].iloc[i])
    if not np.isfinite(atr) or atr <= 0:
        return None

    entry_price = float(opens[i + 1])
    if not np.isfinite(entry_price) or entry_price <= 0:
        return None

    cost = cfg.commission_pct / 100.0 + cfg.slippage_bps / 10_000.0
    fill = entry_price * (1.0 + cost)
    stop_price = fill - stop_mult * atr
    risk = fill - stop_price
    if risk <= 0:
        return None

    # The target is frozen at signal time; letting it drift with a rolling
    # resistance would let a later bar's high define the exit level.
    target = float(resist[i]) if use_resistance_target else np.nan
    if not np.isfinite(target) or target <= fill:
        target = np.nan

    last = min(n - 1, i + 1 + MAX_TRACK_SESSIONS)
    pending_rsi_exit = False
    mae = 0.0
    mfe = 0.0

    for j in range(i + 1, last + 1):
        if pending_rsi_exit:
            return _close_trade(
                index, i, j, fill, float(opens[j]) * (1.0 - cost), stop_price,
                "rsi_target", risk, mae, mfe,
            )

        low_j, high_j = float(lows[j]), float(highs[j])
        mae = min(mae, (low_j - fill) / risk)
        mfe = max(mfe, (high_j - fill) / risk)

        if low_j <= stop_price:
            exit_px = min(stop_price, float(opens[j])) * (1.0 - cost)
            return _close_trade(
                index, i, j, fill, exit_px, stop_price, "stop", risk, mae, mfe
            )

        if np.isfinite(target) and high_j >= target:
            exit_px = max(target, float(opens[j])) * (1.0 - cost)
            return _close_trade(
                index, i, j, fill, exit_px, stop_price, "resistance", risk, mae, mfe
            )

        rsi_j = rsis[j]
        if np.isfinite(rsi_j) and rsi_j >= exit_rsi:
            pending_rsi_exit = True

    exit_px = float(closes[last]) * (1.0 - cost)
    out = _close_trade(
        index, i, last, fill, exit_px, stop_price, "open_at_horizon", risk, mae, mfe
    )
    out.open_at_horizon = True
    return out


def _close_trade(index, i, j, fill, exit_px, stop, reason, risk, mae, mfe) -> TradeOutcome:
    return TradeOutcome(
        entry_date=index[i + 1],
        exit_date=index[j],
        entry_price=fill,
        exit_price=exit_px,
        stop_price=stop,
        reason=reason,
        r_multiple=(exit_px - fill) / risk,
        pct_return=(exit_px / fill - 1.0) * 100.0,
        days_held=int(j - i - 1),
        mae_r=mae,
        mfe_r=mfe,
        open_at_horizon=False,
    )


# ── Building the labelled signal table ───────────────────────────────────────


def build_signal_table(
    panels: Dict[str, Any],
    qualify: pd.DataFrame,
    sector_panel,
    regime_panel,
    cfg: GFSConfig,
    *,
    stop_mult: Optional[float] = None,
    exit_rsi: Optional[float] = None,
    use_resistance_target: bool = True,
    respect_gates: bool = True,
) -> pd.DataFrame:
    """One row per GFS signal: features known at signal time + realised outcome.

    `respect_gates=True` keeps only signals that pass the regime and sector
    gates, i.e. the population the live strategy would actually consider.
    """
    rows: List[Dict[str, Any]] = []
    regime_frame = regime_panel.frame if regime_panel is not None else None
    # The bar store often holds far more history than the configured window.
    # Silently studying signals outside it would mean reporting results for a
    # sample the caller never asked for.
    window_start = pd.Timestamp(cfg.start_date)
    window_end = pd.Timestamp(cfg.end_date)

    for sym, panel in panels.items():
        if sym not in qualify.columns:
            continue
        frame = add_feature_columns(panel.frame, cfg)
        mask = qualify[sym].reindex(frame.index, fill_value=False).astype(bool)
        mask &= (frame.index >= window_start) & (frame.index <= window_end)
        positions = np.flatnonzero(mask.to_numpy())
        if positions.size == 0:
            continue

        sector = panel.sector or "Unknown"
        for i in positions:
            ts = frame.index[i]
            if respect_gates and regime_frame is not None:
                try:
                    if not bool(regime_frame.at[ts, "regime_ok"]):
                        continue
                except KeyError:
                    continue

            sector_rs, sector_rank = _sector_stats(sector_panel, sector, ts)
            if respect_gates and cfg.use_sector_filter:
                if sector_rank is None or sector_rank > cfg.sector_top_n:
                    continue

            outcome = simulate_signal(
                frame, int(i), cfg,
                stop_mult=stop_mult,
                exit_rsi=exit_rsi,
                use_resistance_target=use_resistance_target,
            )
            if outcome is None:
                continue

            row = {
                "symbol": sym,
                "sector": sector,
                "signal_date": ts,
                "entry_date": outcome.entry_date,
                "exit_date": outcome.exit_date,
                "reason": outcome.reason,
                "r_multiple": outcome.r_multiple,
                "pct_return": outcome.pct_return,
                "days_held": outcome.days_held,
                "mae_r": outcome.mae_r,
                "mfe_r": outcome.mfe_r,
                "open_at_horizon": outcome.open_at_horizon,
                "win": outcome.r_multiple > 0,
                "sector_rs": sector_rs,
                "sector_rank": sector_rank,
            }
            src = frame.iloc[i]
            for col in FEATURE_COLUMNS:
                if col in ("sector_rs", "sector_rank", "breadth_pct", "bench_above_sma"):
                    continue
                row[col] = float(src[col]) if col in src and pd.notna(src[col]) else np.nan
            if regime_frame is not None and ts in regime_frame.index:
                row["breadth_pct"] = float(regime_frame.at[ts, "breadth_pct"])
                row["bench_above_sma"] = float(bool(regime_frame.at[ts, "bench_ok"]))
            else:
                row["breadth_pct"] = np.nan
                row["bench_above_sma"] = np.nan
            rows.append(row)

    if not rows:
        return pd.DataFrame()
    table = pd.DataFrame(rows).sort_values("signal_date").reset_index(drop=True)
    logger.info(
        "Signal table: %d signals, %d closed, %d still open at horizon.",
        len(table), int((~table["open_at_horizon"]).sum()),
        int(table["open_at_horizon"].sum()),
    )
    return table


def _sector_stats(sector_panel, sector: str, ts) -> Tuple[Optional[float], Optional[float]]:
    if sector_panel is None or sector not in getattr(sector_panel, "rs", pd.DataFrame()).columns:
        return None, None
    try:
        rs = sector_panel.rs.at[ts, sector]
        rank = sector_panel.rank.at[ts, sector]
    except KeyError:
        return None, None
    rs = float(rs) if pd.notna(rs) else None
    rank = float(rank) if pd.notna(rank) else None
    return rs, rank


# ── Evaluation primitives ────────────────────────────────────────────────────


def evaluate(subset: pd.DataFrame) -> Dict[str, Any]:
    """Win rate AND expectancy together - neither means much alone."""
    closed = subset[~subset["open_at_horizon"]]
    n = len(closed)
    if n == 0:
        return {"n": 0, "win_rate": np.nan, "exp_r": np.nan, "median_r": np.nan,
                "avg_win_r": np.nan, "avg_loss_r": np.nan, "profit_factor": np.nan,
                "avg_days": np.nan}
    r = closed["r_multiple"]
    wins, losses = r[r > 0], r[r <= 0]
    gross_win, gross_loss = wins.sum(), -losses.sum()
    return {
        "n": n,
        "win_rate": len(wins) / n * 100.0,
        "exp_r": float(r.mean()),
        "median_r": float(r.median()),
        "avg_win_r": float(wins.mean()) if len(wins) else np.nan,
        "avg_loss_r": float(losses.mean()) if len(losses) else np.nan,
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else np.inf,
        "avg_days": float(closed["days_held"].mean()),
    }


def quintile_report(
    table: pd.DataFrame, feature: str, bins: int = 5
) -> Optional[pd.DataFrame]:
    """Win rate and expectancy across `bins` equal-count buckets of `feature`."""
    col = table[feature].replace([np.inf, -np.inf], np.nan)
    valid = table[col.notna()].copy()
    if len(valid) < bins * 20:
        return None
    try:
        valid["_bucket"] = pd.qcut(
            valid[feature].replace([np.inf, -np.inf], np.nan), bins,
            labels=False, duplicates="drop",
        )
    except ValueError:
        return None
    rows = []
    for bucket, group in valid.groupby("_bucket"):
        stats = evaluate(group)
        stats["bucket"] = int(bucket)
        stats["lo"] = float(group[feature].min())
        stats["hi"] = float(group[feature].max())
        rows.append(stats)
    if not rows:
        return None
    return pd.DataFrame(rows).set_index("bucket")


def split_by_date(table: pd.DataFrame, frac: float = 0.6) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Chronological split. A random split would leak: same-day signals in the
    same sector are effectively one bet, so they must not straddle the boundary."""
    if table.empty:
        return table, table
    dates = table["signal_date"].sort_values().unique()
    cut = dates[int(len(dates) * frac)]
    return table[table["signal_date"] < cut], table[table["signal_date"] >= cut]


def rank_features(train: pd.DataFrame, features: Sequence[str], bins: int = 5) -> pd.DataFrame:
    """Rank features by the win-rate spread between their best and worst bucket."""
    rows = []
    for feat in features:
        report = quintile_report(train, feat, bins)
        if report is None or report["n"].min() < 20:
            continue
        best = report["win_rate"].idxmax()
        worst = report["win_rate"].idxmin()
        rows.append({
            "feature": feat,
            "best_bucket": int(best),
            "best_win": report.at[best, "win_rate"],
            "best_exp_r": report.at[best, "exp_r"],
            "worst_win": report.at[worst, "win_rate"],
            "spread": report.at[best, "win_rate"] - report.at[worst, "win_rate"],
            "monotonic": _is_monotonic(report["win_rate"]),
            "best_lo": report.at[best, "lo"],
            "best_hi": report.at[best, "hi"],
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("spread", ascending=False).reset_index(drop=True)


def _is_monotonic(series: pd.Series) -> bool:
    """A monotonic response is far more believable than a single lucky bucket."""
    vals = series.sort_index().to_numpy()
    return bool(np.all(np.diff(vals) >= -1e-9) or np.all(np.diff(vals) <= 1e-9))


def rule_mask(table: pd.DataFrame, rule: Dict[str, Tuple[float, float]]) -> pd.Series:
    """Boolean mask for a conjunction of ``feature -> (lo, hi)`` bounds."""
    mask = pd.Series(True, index=table.index)
    for feat, (lo, hi) in rule.items():
        col = table[feat].replace([np.inf, -np.inf], np.nan)
        mask &= col.between(lo, hi)
    return mask.fillna(False)


def yearly_breakdown(subset: pd.DataFrame) -> pd.DataFrame:
    """Per-year win rate and expectancy - an edge concentrated in one year is
    not an edge, and this is the cheapest way to see that."""
    closed = subset[~subset["open_at_horizon"]].copy()
    if closed.empty:
        return pd.DataFrame()
    closed["year"] = closed["signal_date"].dt.year
    rows = []
    for year, group in closed.groupby("year"):
        stats = evaluate(group)
        stats["year"] = int(year)
        rows.append(stats)
    return pd.DataFrame(rows).set_index("year")


def bootstrap_win_rate(
    subset: pd.DataFrame, draws: int = 2000, seed: int = 7
) -> Tuple[float, float]:
    """95% confidence interval for the win rate, resampled **by signal date**.

    Resampling individual trades would badly understate the interval: signals
    cluster on the same days and in the same sectors, so they are not
    independent draws. Blocking on date keeps those clusters intact.
    """
    closed = subset[~subset["open_at_horizon"]]
    if len(closed) < 20:
        return (np.nan, np.nan)
    groups = [g for _, g in closed.groupby("signal_date")]
    rng = np.random.default_rng(seed)
    rates = np.empty(draws)
    for k in range(draws):
        picks = rng.integers(0, len(groups), len(groups))
        sample = pd.concat([groups[p] for p in picks])
        rates[k] = (sample["r_multiple"] > 0).mean() * 100.0
    return (float(np.percentile(rates, 2.5)), float(np.percentile(rates, 97.5)))


def search_pairs(
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: Sequence[str],
    *,
    min_train_n: int = 60,
    min_test_n: int = 40,
    top_k: int = 10,
) -> pd.DataFrame:
    """Every two-feature conjunction of top-quintile bounds, scored on train
    and then reported on test.

    The trial count grows as `C(F,2) x 25`, which is why the returned frame
    carries `n_trials`: the caller must show it. A conjunction that looks good
    on train and evaporates on test has been fitted, not discovered.
    """
    bounds: Dict[str, List[Tuple[float, float]]] = {}
    for feat in features:
        report = quintile_report(train, feat)
        if report is None:
            continue
        bounds[feat] = [(report.at[b, "lo"], report.at[b, "hi"]) for b in report.index]

    names = sorted(bounds)
    rows: List[Dict[str, Any]] = []
    trials = 0
    for a_i, a in enumerate(names):
        for b in names[a_i + 1:]:
            for lo_a, hi_a in bounds[a]:
                for lo_b, hi_b in bounds[b]:
                    trials += 1
                    rule = {a: (lo_a, hi_a), b: (lo_b, hi_b)}
                    tr = evaluate(train[rule_mask(train, rule)])
                    if tr["n"] < min_train_n:
                        continue
                    te = evaluate(test[rule_mask(test, rule)])
                    if te["n"] < min_test_n:
                        continue
                    rows.append({
                        "feat_a": a, "lo_a": lo_a, "hi_a": hi_a,
                        "feat_b": b, "lo_b": lo_b, "hi_b": hi_b,
                        "train_n": tr["n"], "train_win": tr["win_rate"],
                        "train_exp_r": tr["exp_r"],
                        "test_n": te["n"], "test_win": te["win_rate"],
                        "test_exp_r": te["exp_r"], "test_pf": te["profit_factor"],
                    })
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).sort_values("train_win", ascending=False)
    frame = frame.head(top_k).reset_index(drop=True)
    frame.attrs["n_trials"] = trials
    return frame


# ── Stop / target geometry ───────────────────────────────────────────────────


def threshold_scan(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature: str,
    thresholds: Sequence[float],
    *,
    direction: str = "ge",
) -> pd.DataFrame:
    """One interpretable cutoff, evaluated on both halves at once.

    Quintile bounds are sample-specific and therefore mildly overfit by
    construction. A round-number threshold that works on both halves is a much
    stronger claim, and it is the only kind of rule that can actually be written
    into the config.
    """
    rows = []
    for thr in thresholds:
        def pick(frame: pd.DataFrame) -> pd.DataFrame:
            col = frame[feature].replace([np.inf, -np.inf], np.nan)
            keep = col >= thr if direction == "ge" else col <= thr
            return frame[keep.fillna(False)]

        tr, te = evaluate(pick(train)), evaluate(pick(test))
        rows.append({
            "threshold": thr,
            "train_n": tr["n"], "train_win": tr["win_rate"], "train_exp_r": tr["exp_r"],
            "test_n": te["n"], "test_win": te["win_rate"], "test_exp_r": te["exp_r"],
            "test_pf": te["profit_factor"],
        })
    return pd.DataFrame(rows)


def stop_target_grid(
    panels: Dict[str, Any],
    qualify: pd.DataFrame,
    sector_panel,
    regime_panel,
    cfg: GFSConfig,
    stop_mults: Sequence[float] = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0),
    exit_rsis: Sequence[float] = (55.0, 60.0, 65.0, 70.0),
    *,
    min_headroom_pct: Optional[float] = None,
) -> pd.DataFrame:
    """Win rate and expectancy across stop width x exit threshold.

    This is the table that makes the win-rate/expectancy trade-off impossible to
    ignore: a wide stop with an early exit buys a high win rate by making the
    average loss enormous.
    """
    rows = []
    for mult in stop_mults:
        for rsi in exit_rsis:
            table = build_signal_table(
                panels, qualify, sector_panel, regime_panel, cfg,
                stop_mult=mult, exit_rsi=rsi,
            )
            if min_headroom_pct is not None and not table.empty:
                table = table[table["headroom_pct"] >= min_headroom_pct]
            stats = evaluate(table)
            stats["atr_stop_mult"] = mult
            stats["exit_rsi"] = rsi
            rows.append(stats)
            logger.info(
                "stop %.1fxATR / exit RSI %.0f -> win %.1f%%, ExpR %.3f (n=%d)",
                mult, rsi, stats["win_rate"], stats["exp_r"], stats["n"],
            )
    return pd.DataFrame(rows)
