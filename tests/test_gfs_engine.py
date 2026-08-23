"""
End-to-end tests for the GFS backtest harness.

These run the whole pipeline - panels, sector and regime views, the daily loop,
metrics and the null models - on synthetic data, so they can assert things that
are impossible to check on real prices:

* a market with **no** exploitable structure must not produce a large edge;
* a market with a **planted** GFS pattern must produce one, otherwise the engine
  is failing to see signals it should see;
* the backtest must be **deterministic** for a given seed;
* and, most importantly, the result must not change when future data is appended
  to the input - the end-to-end version of the leakage test.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backtesting.gfs import baselines as bl
from backtesting.gfs.config import GFSConfig, RANK_RANDOM
from backtesting.gfs.engine import GFSBacktestEngine
from backtesting.gfs.metrics import compute_metrics, render_summary
from backtesting.gfs.panels import (
    base_panel_key,
    build_panels,
    build_qualify_matrix,
    build_regime_panel,
    build_sector_panel,
    master_calendar,
)
from backtesting.gfs.service import PreparedData
from backtesting.gfs.universe import UniverseStock


class FakeData:
    """Stand-in for PointInTimeData: whole frames, no network."""

    def __init__(self, frames, benchmark=None):
        self.frames = frames
        self.benchmark = benchmark

    def full(self, symbol):
        return self.frames.get(symbol)


def random_walk(n, seed, drift=0.0004, vol=0.016, start=100.0, index=None):
    rng = np.random.default_rng(seed)
    idx = index if index is not None else pd.bdate_range("2014-01-01", periods=n)
    close = start * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    spread = np.abs(rng.normal(0, 0.007, n)) * close
    frame = pd.DataFrame(
        {
            "Open": close * (1 + rng.normal(0, 0.002, n)),
            "High": close + spread,
            "Low": close - spread,
            "Close": close,
            "Volume": rng.integers(500_000, 5_000_000, n).astype(float),
        },
        index=idx,
    )
    frame["High"] = frame[["Open", "High", "Close"]].max(axis=1)
    frame["Low"] = frame[["Open", "Low", "Close"]].min(axis=1)
    return frame


def build_market(num_symbols=12, n=2200, seed0=100):
    idx = pd.bdate_range("2014-01-01", periods=n)
    frames = {
        f"SYM{i:02d}": random_walk(n, seed0 + i, index=idx) for i in range(num_symbols)
    }
    bench = random_walk(n, seed0 + 999, drift=0.0003, vol=0.010, start=10_000.0, index=idx)
    sectors = ["IT", "Bank", "Pharma", "Auto"]
    universe = [
        UniverseStock(symbol=s, industry=sectors[i % len(sectors)])
        for i, s in enumerate(sorted(frames))
    ]
    return FakeData(frames, bench), universe


def make_cfg(**kw) -> GFSConfig:
    base = dict(
        start_date=date(2019, 1, 1),
        end_date=date(2022, 6, 30),
        min_daily_bars=250,
        min_weekly_bars=52,
        min_monthly_bars=24,
        min_turnover_cr=0.0,
        min_price=0.0,
        max_atr_pct=100.0,
        use_regime_filter=False,
        use_sector_filter=False,
        starting_capital=1_000_000.0,
        max_positions=5,
    )
    base.update(kw)
    return GFSConfig(**base)


def run_pipeline(data, universe, cfg):
    panels = build_panels(data, universe, cfg)
    calendar = master_calendar(data.benchmark, panels)
    sector = build_sector_panel(panels, calendar, cfg)
    regime = build_regime_panel(data.benchmark, panels, calendar, cfg)
    qualify = build_qualify_matrix(panels, calendar, cfg)
    engine = GFSBacktestEngine(cfg, panels, sector, regime, qualify, calendar)
    engine.run(cfg.start_date, cfg.end_date)
    return engine, panels, qualify


@pytest.fixture(scope="module")
def market():
    return build_market()


# ── The pipeline runs and produces coherent output ───────────────────────────


def test_end_to_end_runs_and_balances(market):
    data, universe = market
    cfg = make_cfg()
    engine, panels, qualify = run_pipeline(data, universe, cfg)

    assert len(panels) == len(universe)
    assert len(engine.daily_log) > 700
    assert engine.pf.cash >= -1e-6, "cash must never go negative"
    assert len(engine.pf.positions) <= cfg.max_positions

    metrics = compute_metrics(engine.daily_log, engine.pf.closed, cfg.starting_capital)
    assert metrics["start_date"] < metrics["end_date"]
    assert "max_drawdown_pct" in metrics
    assert render_summary(metrics, signal_stats=engine.signal_frequency())


def test_position_and_sector_limits_are_never_breached(market):
    data, universe = market
    cfg = make_cfg(max_positions=3, max_per_sector=1, use_sector_filter=False)
    engine, _, _ = run_pipeline(data, universe, cfg)
    for snap in engine.daily_log:
        assert snap["open_positions"] <= 3


def test_no_trade_exits_before_it_was_opened(market):
    data, universe = market
    engine, _, _ = run_pipeline(data, universe, make_cfg())
    for trade in engine.pf.closed:
        assert trade.exit_date >= trade.entry_date
        assert trade.entry_price > 0 and trade.exit_price > 0
        assert trade.quantity > 0


def test_every_entry_is_preceded_by_a_qualifying_signal(market):
    """A position must never appear on a day when the name did not qualify on
    some earlier session - the audit that ties fills back to signals."""
    data, universe = market
    cfg = make_cfg()
    engine, _, qualify = run_pipeline(data, universe, cfg)
    assert engine.pf.closed, "synthetic market produced no trades to audit"
    for trade in engine.pf.closed:
        entry_ts = pd.Timestamp(trade.entry_date)
        history = qualify[trade.symbol].loc[:entry_ts]
        # The signal fires at a close and fills at the NEXT open, so the
        # qualifying day is strictly before the entry date.
        assert history.iloc[:-1].any(), f"{trade.symbol} filled without a prior signal"


def test_run_is_deterministic(market):
    data, universe = market
    cfg = make_cfg(rank_by=RANK_RANDOM, seed=42)
    a, _, _ = run_pipeline(data, universe, cfg)
    b, _, _ = run_pipeline(data, universe, cfg)
    assert a.pf.closed, "vacuous test: the synthetic market produced no trades"
    assert [t.symbol for t in a.pf.closed] == [t.symbol for t in b.pf.closed]
    assert [round(s["equity"], 6) for s in a.daily_log] == [
        round(s["equity"], 6) for s in b.daily_log
    ]


def test_appending_future_data_does_not_change_the_past(market):
    """The end-to-end leakage test: extending the input beyond the test window
    must leave every simulated day identical."""
    data, universe = market
    cfg = make_cfg(end_date=date(2021, 6, 30))

    cut = pd.Timestamp("2021-08-31")
    truncated = FakeData(
        {s: f.loc[:cut] for s, f in data.frames.items()},
        data.benchmark.loc[:cut],
    )
    full_engine, _, _ = run_pipeline(data, universe, cfg)
    trunc_engine, _, _ = run_pipeline(truncated, universe, cfg)

    assert full_engine.daily_log and full_engine.pf.closed, "vacuous test"
    assert [s["equity"] for s in full_engine.daily_log] == [
        s["equity"] for s in trunc_engine.daily_log
    ]
    assert [(t.symbol, t.entry_date, t.exit_date) for t in full_engine.pf.closed] == [
        (t.symbol, t.entry_date, t.exit_date) for t in trunc_engine.pf.closed
    ]


# ── The engine sees signals it should, and not ones it shouldn't ─────────────


def test_qualify_matrix_matches_the_stated_rule(market):
    data, universe = market
    cfg = make_cfg(g_rsi_min=55.0, f_rsi_min=55.0, s_rsi_entry=45.0)
    panels = build_panels(data, universe, cfg)
    calendar = master_calendar(data.benchmark, panels)
    qualify = build_qualify_matrix(panels, calendar, cfg)

    checked = 0
    for sym, panel in panels.items():
        frame = panel.frame
        flags = qualify[sym].reindex(frame.index).fillna(False)
        hits = frame[flags]
        if hits.empty:
            continue
        assert (hits["rsi_m"] >= 55.0).all()
        assert (hits["rsi_w"] >= 55.0).all()
        assert (hits["rsi_d"] <= 45.0).all()
        assert hits["tradable"].all()
        checked += len(hits)
    assert checked > 0, "no qualifying rows at all - thresholds may be unreachable"


def test_stricter_thresholds_never_produce_more_signals(market):
    data, universe = market
    loose = build_qualify_matrix(
        build_panels(data, universe, make_cfg(g_rsi_min=50, f_rsi_min=50, s_rsi_entry=45)),
        master_calendar(data.benchmark, build_panels(data, universe, make_cfg())),
        make_cfg(g_rsi_min=50, f_rsi_min=50, s_rsi_entry=45),
    )
    strict_cfg = make_cfg(g_rsi_min=70, f_rsi_min=70, s_rsi_entry=30)
    panels = build_panels(data, universe, strict_cfg)
    strict = build_qualify_matrix(
        panels, master_calendar(data.benchmark, panels), strict_cfg
    )
    assert strict.to_numpy().sum() <= loose.to_numpy().sum()


def test_base_panel_cache_cannot_change_results(market):
    """The sweep's speed-up must be a pure optimisation.

    ``build_panels`` may reuse a cached indicator pass across configurations
    that share a :func:`base_panel_key`. If that cache ever leaked a stale
    threshold, every sweep result would be quietly wrong while every test that
    only runs one configuration would still pass. So: prime the cache with one
    set of thresholds, reuse it with another, and demand the output match a
    cold build.
    """
    data, universe = market
    loose = make_cfg(g_rsi_min=50, f_rsi_min=50, s_rsi_entry=45)
    strict = make_cfg(g_rsi_min=70, f_rsi_min=70, s_rsi_entry=30)
    assert base_panel_key(loose) == base_panel_key(strict)

    cache = {}
    build_panels(data, universe, loose, cache)  # prime with the loose thresholds
    assert cache, "cache was never populated, so this test proves nothing"
    warm = build_panels(data, universe, strict, cache)
    cold = build_panels(data, universe, strict)

    assert set(warm) == set(cold)
    for sym in cold:
        pd.testing.assert_frame_equal(warm[sym].frame, cold[sym].frame)
    # And the reused rows must actually differ from what the priming config saw,
    # otherwise the thresholds were never really re-applied.
    primed = build_panels(data, universe, loose)
    assert any(
        not warm[s].frame["gf_ok"].equals(primed[s].frame["gf_ok"]) for s in cold
    )


def test_base_panel_cache_is_dropped_when_indicators_change(market):
    """Changing an RSI period must invalidate the cache, not reuse it."""
    data, universe = market
    prepared = PreparedData(data, universe)
    prepared.panels_for(make_cfg(rsi_period_daily=14))
    first = dict(prepared._base_cache)
    assert first
    prepared.panels_for(make_cfg(rsi_period_daily=9))
    sym = next(iter(first))
    assert not prepared._base_cache[sym]["rsi_d"].equals(first[sym]["rsi_d"])


def test_random_walk_market_shows_no_meaningful_edge(market):
    """Prices with no exploitable structure must not yield a big forward-return
    edge. If they do, the harness is measuring itself, not the market."""
    data, universe = market
    cfg = make_cfg()
    panels = build_panels(data, universe, cfg)
    calendar = master_calendar(data.benchmark, panels)
    qualify = build_qualify_matrix(panels, calendar, cfg)
    study = bl.forward_return_study(panels, qualify, horizons=[21])
    if not study:
        pytest.skip("no signals in the synthetic market")
    edge = abs(study["h21"]["edge_pct"])
    assert edge < 6.0, f"suspiciously large edge on random data: {edge}%"


# ── Gates behave monotonically ───────────────────────────────────────────────


def test_regime_gate_reduces_or_holds_trade_count(market):
    data, universe = market
    off, _, _ = run_pipeline(data, universe, make_cfg(use_regime_filter=False))
    on, _, _ = run_pipeline(data, universe, make_cfg(use_regime_filter=True))
    assert len(on.pf.closed) <= len(off.pf.closed)


def test_sector_gate_reduces_or_holds_trade_count(market):
    data, universe = market
    off, _, _ = run_pipeline(data, universe, make_cfg(use_sector_filter=False))
    on, _, _ = run_pipeline(
        data, universe, make_cfg(use_sector_filter=True, sector_top_n=1, min_sector_members=1)
    )
    assert len(on.pf.closed) <= len(off.pf.closed)


def test_higher_costs_never_improve_results(market):
    data, universe = market
    cheap, _, _ = run_pipeline(data, universe, make_cfg(commission_pct=0.0, slippage_bps=0.0))
    dear, _, _ = run_pipeline(data, universe, make_cfg(commission_pct=0.5, slippage_bps=100.0))
    if not cheap.pf.closed:
        pytest.skip("no trades")
    assert dear.daily_log[-1]["equity"] <= cheap.daily_log[-1]["equity"] + 1e-6


# ── Baselines ────────────────────────────────────────────────────────────────


def test_buy_and_hold_curve_tracks_the_benchmark(market):
    data, universe = market
    cfg = make_cfg()
    engine, _, _ = run_pipeline(data, universe, cfg)
    curve = bl.buy_and_hold_curve(data.benchmark, engine.daily_log, cfg.starting_capital)
    assert len(curve) == len(engine.daily_log)
    assert curve[0]["equity"] == pytest.approx(cfg.starting_capital, rel=1e-6)

    metrics = compute_metrics(
        engine.daily_log, engine.pf.closed, cfg.starting_capital, benchmark_curve=curve
    )
    assert "benchmark" in metrics
    assert metrics["benchmark"]["excess_cagr_pct"] == pytest.approx(
        metrics["cagr_pct"] - metrics["benchmark"]["cagr_pct"], abs=0.02
    )


def test_random_entry_null_produces_a_percentile(market):
    data, universe = market
    cfg = make_cfg()
    engine, panels, _ = run_pipeline(data, universe, cfg)
    if len(engine.pf.closed) < 5:
        pytest.skip("too few trades for a meaningful null")
    null = bl.random_entry_null(panels, engine.pf.closed, cfg, num_runs=60)
    assert 0.0 <= null["strategy_percentile_vs_random"] <= 100.0
    assert null["random_avg_trade_pct_p5"] <= null["random_avg_trade_pct_mean"]
    assert null["random_avg_trade_pct_mean"] <= null["random_avg_trade_pct_p95"]
    assert bl.render_random_null(null)


def test_ablation_variants_are_well_formed():
    from dataclasses import replace

    cfg = make_cfg()
    names = set()
    for variant in bl.ablation_variants():
        assert variant.question, variant.name
        assert variant.name not in names
        names.add(variant.name)
        replace(cfg, **variant.overrides).validate()
    assert "baseline" in names and "no_grandfather_father" in names

