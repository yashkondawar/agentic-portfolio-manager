"""Tests for the Kronos gate separation-test math (kronos/gate_eval.py).

No torch / network: a fake forecaster returns per-symbol scripted forecast paths
and a fake raw-price cache serves hand-built history, so we exercise the bucketing,
quintile, rank-IC and verdict logic deterministically.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from kronos.gate_eval import (
    RawPriceCache,
    TradeEval,
    TradeRecord,
    evaluate_gate,
    records_from_dicts,
    separation_report,
    render_separation_report,
)


# ── fakes ────────────────────────────────────────────────────────────────────
class _FakePredictor:
    """Per-symbol drift keyed off the last-close level so different symbols get
    different forecasts. Drift is chosen by the caller via a price->drift map."""

    def __init__(self, drift_by_last):
        self.drift_by_last = drift_by_last

    def predict(self, df, x_timestamp, y_timestamp, pred_len, **kwargs):
        last = round(float(df["close"].iloc[-1]), 2)
        drift = self.drift_by_last.get(last, 0.0)
        closes = [last * (1 + drift * (i + 1)) for i in range(pred_len)]
        return pd.DataFrame(
            {
                "open": closes,
                "high": [c * 1.01 for c in closes],
                "low": [c * 0.99 for c in closes],
                "close": closes,
                "volume": [1000] * pred_len,
            }
        )


class _FakeForecaster:
    def __init__(self, drift_by_last):
        self._p = _FakePredictor(drift_by_last)

    def load(self):
        return self._p

    def predict_paths(self, x_df, x_ts, y_ts, *, pred_len, sample_paths):
        return [self._p.predict(x_df, x_ts, y_ts, pred_len) for _ in range(sample_paths)]


class _FakeRawCache(RawPriceCache):
    """Serves a flat history at a per-symbol price level, plus a scripted forward
    return, without hitting the network."""

    def __init__(self, price_by_symbol, fwd_by_symbol=None, rows: int = 120):
        self.price_by_symbol = price_by_symbol
        self.fwd_by_symbol = fwd_by_symbol or {}
        self.rows = rows

    def _plain(self, symbol):
        return symbol.strip().upper().replace(".NS", "").replace(".BO", "")

    def as_of(self, symbol, day, lookback_rows=None):
        price = self.price_by_symbol.get(self._plain(symbol))
        if price is None:
            return None
        n = lookback_rows or self.rows
        idx = pd.bdate_range(end=pd.Timestamp(day), periods=n)
        prices = np.full(n, float(price))
        return pd.DataFrame(
            {
                "Open": prices,
                "High": prices * 1.01,
                "Low": prices * 0.99,
                "Close": prices,
                "Volume": np.full(n, 1000),
            },
            index=idx,
        )

    def forward_return_pct(self, symbol, entry_day, horizon):
        return self.fwd_by_symbol.get(self._plain(symbol))


# ── ingestion ────────────────────────────────────────────────────────────────
def test_records_from_dicts_tolerates_casing_and_aliases():
    rows = [
        {"Symbol": "reliance", "Entry_Date": "2024-03-01", "PnL_Pct": 5.0},
        {"symbol": "TCS", "entry_date": "2024-03-04", "return_pct": -2.0},
        {"symbol": "BROKEN"},  # missing fields -> skipped
    ]
    recs = records_from_dicts(rows)
    assert [r.symbol for r in recs] == ["RELIANCE", "TCS"]
    assert recs[0].entry_date == date(2024, 3, 1)
    assert recs[0].strat_win is True
    assert recs[1].strat_win is False


# ── bucketing / separation ───────────────────────────────────────────────────
def _mk(symbol, pnl, prob=None, allowed=None, fwd=None, has_signal=True, expret=None):
    return TradeEval(
        symbol=symbol,
        entry_date=date(2024, 3, 1),
        strat_pnl_pct=pnl,
        strat_win=pnl > 0,
        has_signal=has_signal,
        allowed=allowed,
        prob_up=prob,
        expected_return=expret,
        direction="BUY" if (prob or 0) >= 0.5 else "AVOID",
        fwd_pnl_pct=fwd,
    )


def test_separation_report_kept_beats_vetoed():
    evals = [
        _mk("A", 10.0, prob=0.7, allowed=True),
        _mk("B", 8.0, prob=0.65, allowed=True),
        _mk("C", 5.0, prob=0.6, allowed=True),
        _mk("D", -6.0, prob=0.3, allowed=False),
        _mk("E", -4.0, prob=0.35, allowed=False),
        _mk("F", 2.0, prob=0.4, allowed=False),
    ]
    rep = separation_report(evals)
    assert rep["kept"]["n"] == 3
    assert rep["kept"]["win_rate"] == 100.0
    assert rep["vetoed"]["n"] == 3
    assert rep["vetoed"]["win_rate"] < rep["kept"]["win_rate"]
    assert rep["win_rate_lift_vs_baseline"] > 0
    assert rep["verdict"].startswith("PASS")


def test_separation_report_inverted_signal():
    evals = [
        _mk("A", -10.0, prob=0.7, allowed=True),
        _mk("B", -8.0, prob=0.65, allowed=True),
        _mk("C", 9.0, prob=0.3, allowed=False),
        _mk("D", 7.0, prob=0.35, allowed=False),
    ]
    rep = separation_report(evals)
    assert rep["kept"]["win_rate"] == 0.0
    assert rep["vetoed"]["win_rate"] == 100.0
    assert rep["verdict"].startswith("INVERTED")


def test_separation_report_inconclusive_when_bucket_empty():
    evals = [_mk("A", 3.0, prob=0.7, allowed=True), _mk("B", 4.0, prob=0.6, allowed=True)]
    rep = separation_report(evals)
    assert rep["vetoed"]["n"] == 0
    assert rep["verdict"].startswith("INCONCLUSIVE")


def test_rank_ic_positive_when_score_tracks_outcome():
    # prob_up strictly increasing with realised pnl -> IC == +1
    evals = [_mk(f"S{i}", pnl=float(i), prob=0.4 + i * 0.03, fwd=float(i)) for i in range(8)]
    rep = separation_report(evals)
    assert rep["ic_probup_vs_strat"] == 1.0
    assert rep["ic_probup_vs_fwd"] == 1.0


def test_quintiles_present_and_monotonic():
    evals = [_mk(f"S{i}", pnl=float(i - 5), prob=0.3 + i * 0.02) for i in range(20)]
    rep = separation_report(evals)
    quints = rep["quintiles"]
    assert len(quints) == 5
    # higher prob quintiles should have >= win rate than lower ones (monotone build)
    assert quints[-1]["win_rate"] >= quints[0]["win_rate"]


def test_no_signal_trades_counted_in_baseline_only():
    evals = [
        _mk("A", 5.0, prob=0.7, allowed=True),
        _mk("Z", -3.0, has_signal=False),
    ]
    rep = separation_report(evals)
    assert rep["n_trades"] == 2
    assert rep["n_signalled"] == 1
    assert rep["n_no_signal"] == 1
    # baseline win rate over ALL trades (1 win / 2) = 50
    assert rep["baseline_win_rate"] == 50.0


def test_render_report_smoke():
    evals = [_mk("A", 5.0, prob=0.7, allowed=True), _mk("B", -3.0, prob=0.3, allowed=False)]
    rep = separation_report(evals)
    md = render_separation_report(rep, title="unit", meta="meta-line")
    assert "Separation Test" in md
    assert "Verdict" in md
    assert "meta-line" in md


# ── end-to-end evaluate_gate with fakes ──────────────────────────────────────
def test_evaluate_gate_end_to_end_with_fakes():
    trades = [
        TradeRecord("WINR", date(2024, 3, 1), strat_pnl_pct=12.0),
        TradeRecord("LOSR", date(2024, 3, 1), strat_pnl_pct=-9.0),
        TradeRecord("GONE", date(2024, 3, 1), strat_pnl_pct=1.0),  # no history
    ]
    raw = _FakeRawCache(
        price_by_symbol={"WINR": 100.0, "LOSR": 200.0},  # GONE absent -> no signal
        fwd_by_symbol={"WINR": 6.0, "LOSR": -5.0},
    )
    # Forecaster: WINR drifts up, LOSR drifts down.
    forecaster = _FakeForecaster(drift_by_last={100.0: 0.02, 200.0: -0.02})

    evals = evaluate_gate(
        trades, forecaster, raw,
        pred_len=5, sample_paths=4, lookback=64, min_prob_up=0.5, block_avoid=True,
    )
    by_sym = {e.symbol: e for e in evals}
    assert by_sym["WINR"].has_signal and by_sym["WINR"].allowed is True
    assert by_sym["LOSR"].has_signal and by_sym["LOSR"].allowed is False
    assert by_sym["GONE"].has_signal is False
    assert by_sym["GONE"].fwd_pnl_pct is None

    rep = separation_report(evals)
    assert rep["kept"]["win_rate"] == 100.0
    assert rep["vetoed"]["win_rate"] == 0.0


# ── RawPriceCache.forward_return_pct math (real method, hand-built frame) ─────
def test_evaluate_gate_rank_mode_keeps_top_fraction():
    trades = [
        TradeRecord("HI", date(2024, 3, 1), strat_pnl_pct=12.0),
        TradeRecord("MID", date(2024, 3, 1), strat_pnl_pct=1.0),
        TradeRecord("LO", date(2024, 3, 1), strat_pnl_pct=-9.0),
        TradeRecord("LO2", date(2024, 3, 1), strat_pnl_pct=-4.0),
    ]
    raw = _FakeRawCache(price_by_symbol={"HI": 100.0, "MID": 150.0, "LO": 200.0, "LO2": 250.0})
    # Drift: HI most bullish, then MID, then LO/LO2 bearish.
    forecaster = _FakeForecaster(
        drift_by_last={100.0: 0.03, 150.0: 0.01, 200.0: -0.02, 250.0: -0.03}
    )
    evals = evaluate_gate(
        trades, forecaster, raw,
        pred_len=5, sample_paths=3, lookback=64, gate_mode="rank", keep_fraction=0.5,
    )
    kept = {e.symbol for e in evals if e.allowed}
    vetoed = {e.symbol for e in evals if not e.allowed}
    assert kept == {"HI", "MID"}      # top 50% by expected return
    assert vetoed == {"LO", "LO2"}


def test_forward_return_pct_math():
    cache = RawPriceCache.__new__(RawPriceCache)  # bypass __init__/mkdir
    idx = pd.bdate_range("2024-01-01", periods=30)
    closes = np.arange(100.0, 130.0)  # +1 per session
    cache.frames = {
        "X": pd.DataFrame(
            {"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": 1},
            index=idx,
        )
    }
    entry = idx[10].date()
    # entry close = 110, +5 sessions -> 115 -> (115/110 - 1)*100
    got = cache.forward_return_pct("X", entry, 5)
    assert got == pytest.approx((115.0 / 110.0 - 1.0) * 100.0)
    # not enough forward rows near the end -> None
    assert cache.forward_return_pct("X", idx[28].date(), 5) is None
