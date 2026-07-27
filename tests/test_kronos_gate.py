"""Tests for the Kronos confirmation gate and the A/B comparison layer.

A fake forecaster returns scripted paths so we exercise the gate's decision +
point-in-time plumbing without torch, network, or GPU.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backtesting.swing_trading.kronos_gate import KronosGate
from backtesting.swing_trading.kronos_ab import _compare, _gate_stats, render_ab_report
from backtesting.swing_trading.config import BacktestConfig


class _FakePredictor:
    """Stand-in for KronosPredictor.predict — returns a fixed drift per call."""

    def __init__(self, drift: float):
        self.drift = drift
        self.calls = 0

    def predict(self, df, x_timestamp, y_timestamp, pred_len, **kwargs):
        self.calls += 1
        last = float(df["close"].iloc[-1])
        closes = [last * (1 + self.drift * (i + 1)) for i in range(pred_len)]
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
    def __init__(self, drift: float):
        self._predictor = _FakePredictor(drift)

    def load(self):
        return self._predictor

    def predict_paths(self, x_df, x_ts, y_ts, *, pred_len, sample_paths):
        p = self.load()
        return [
            p.predict(x_df, x_ts, y_ts, pred_len) for _ in range(sample_paths)
        ]


def _asof_frame(n: int = 120, start_price: float = 100.0) -> pd.DataFrame:
    idx = pd.bdate_range("2025-01-01", periods=n)
    prices = np.linspace(start_price, start_price * 1.1, n)
    return pd.DataFrame(
        {
            "Open": prices,
            "High": prices * 1.01,
            "Low": prices * 0.99,
            "Close": prices,
            "Volume": [10000] * n,
        },
        index=idx,
    )


def _gate(forecaster, **overrides) -> KronosGate:
    kwargs = dict(
        pred_len=5,
        sample_paths=4,
        lookback=64,
        min_prob_up=0.55,
        block_avoid=True,
    )
    kwargs.update(overrides)
    return KronosGate(forecaster, **kwargs)


def test_gate_keeps_bullish_candidate():
    gate = _gate(_FakeForecaster(drift=0.01))  # +1%/step → strongly up
    sig = gate.evaluate("TEST", _asof_frame(), date(2025, 6, 2))
    assert sig is not None
    assert sig.direction == "BUY"
    assert sig.prob_up == 1.0
    assert gate.allows(sig) is True


def test_gate_vetoes_bearish_candidate():
    gate = _gate(_FakeForecaster(drift=-0.01))  # -1%/step → down
    sig = gate.evaluate("TEST", _asof_frame(), date(2025, 6, 2))
    assert sig.direction == "AVOID"
    assert gate.allows(sig) is False


def test_gate_min_prob_up_threshold_blocks():
    # Flat drift → prob_up == 0; even with block_avoid off, low P(up) vetoes.
    gate = _gate(_FakeForecaster(drift=-0.001), block_avoid=False, min_prob_up=0.55)
    sig = gate.evaluate("TEST", _asof_frame(), date(2025, 6, 2))
    assert gate.allows(sig) is False


def test_gate_fails_open_on_insufficient_history():
    gate = _gate(_FakeForecaster(drift=0.01), min_rows=30)
    short = _asof_frame(n=10)
    sig = gate.evaluate("TEST", short, date(2025, 6, 2))
    assert sig is None
    assert gate.allows(None) is True  # no forecast -> not vetoed


def test_gate_caches_by_symbol_and_day():
    forecaster = _FakeForecaster(drift=0.01)
    gate = _gate(forecaster, sample_paths=4)
    df = _asof_frame()
    day = date(2025, 6, 2)
    gate.evaluate("TEST", df, day)
    calls_after_first = forecaster._predictor.calls
    gate.evaluate("TEST", df, day)  # same key → cached, no new predict calls
    assert forecaster._predictor.calls == calls_after_first


def test_gate_decision_record_shape():
    gate = _gate(_FakeForecaster(drift=0.01))
    sig = gate.evaluate("TEST", _asof_frame(), date(2025, 6, 2))
    rec = gate.decision_record("TEST", date(2025, 6, 2), sig, True)
    assert rec["symbol"] == "TEST"
    assert rec["allowed"] is True
    assert rec["direction"] == "BUY"
    assert 0.0 <= rec["prob_up"] <= 1.0


def test_compare_and_verdict_pass():
    base = {
        "win_rate_pct": 50.0,
        "cagr_pct": 10.0,
        "max_drawdown_pct": -20.0,
        "num_trades": 40,
    }
    gated = {
        "win_rate_pct": 60.0,
        "cagr_pct": 12.0,
        "max_drawdown_pct": -15.0,
        "num_trades": 25,
    }
    cmp = _compare(base, gated)
    assert cmp["win_rate_pct"] == 10.0
    assert cmp["return_per_dd_gated"] > cmp["return_per_dd_base"]
    assert cmp["verdict"].startswith("PASS")


def test_verdict_inconclusive_when_all_vetoed():
    base = {"win_rate_pct": 50.0, "cagr_pct": 10.0, "max_drawdown_pct": -20.0, "num_trades": 30}
    gated = {"win_rate_pct": 0.0, "cagr_pct": 0.0, "max_drawdown_pct": 0.0, "num_trades": 0}
    cmp = _compare(base, gated)
    assert "INCONCLUSIVE" in cmp["verdict"]


def test_gate_stats_counts():
    log = [
        {"allowed": True, "reason": "kept", "direction": "BUY"},
        {"allowed": False, "reason": "vetoed", "direction": "AVOID"},
        {"allowed": True, "reason": "no_forecast", "direction": None},
    ]
    stats = _gate_stats(log)
    assert stats["evaluated"] == 3
    assert stats["vetoed"] == 1
    assert stats["kept"] == 2
    assert stats["avoid_calls"] == 1
    assert stats["no_forecast"] == 1


def test_render_ab_report_smoke():
    base = {
        "total_return_pct": 8.0, "cagr_pct": 8.0, "max_drawdown_pct": -18.0,
        "sharpe": 0.7, "win_rate_pct": 48.0, "profit_factor": 1.4,
        "num_trades": 40, "avg_holding_days": 12.0, "avg_exposure_pct": 60.0,
    }
    gated = {
        "total_return_pct": 11.0, "cagr_pct": 11.0, "max_drawdown_pct": -13.0,
        "sharpe": 1.0, "win_rate_pct": 58.0, "profit_factor": 1.9,
        "num_trades": 26, "avg_holding_days": 11.0, "avg_exposure_pct": 45.0,
    }
    cmp = _compare(base, gated)
    stats = _gate_stats([{"allowed": True, "reason": "kept", "direction": "BUY"}])
    report = render_ab_report(base, gated, cmp, stats, BacktestConfig())
    assert "Kronos Gate A/B" in report
    assert "Verdict:" in report
    assert "Win rate" in report
