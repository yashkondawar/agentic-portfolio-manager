"""Tests for the chart-ready Kronos backend (kronos.viz).

These use a fake forecaster + monkeypatched history fetch so they run without
torch, network, or GPU. They validate the payload *shape* the UI depends on.
"""

from __future__ import annotations

import pandas as pd
import pytest

from kronos import viz
from kronos.config import KronosConfig


def _history(n: int = 120) -> pd.DataFrame:
    idx = pd.bdate_range(end="2024-06-28", periods=n)
    base = [100 + i * 0.1 for i in range(n)]
    return pd.DataFrame(
        {
            "open": base,
            "high": [c * 1.01 for c in base],
            "low": [c * 0.99 for c in base],
            "close": base,
            "volume": [1000] * n,
        },
        index=idx,
    )


class _FakeForecaster:
    """Returns deterministic upward-drifting paths, no torch involved."""

    def __init__(self, config=None):
        self.config = config

    def predict_paths(self, df, x_ts, y_ts, *, pred_len, sample_paths):
        paths = []
        last = float(df["close"].iloc[-1])
        for k in range(sample_paths):
            closes = [last * (1 + 0.01 * (step + 1) + 0.001 * k) for step in range(pred_len)]
            paths.append(
                pd.DataFrame(
                    {
                        "open": closes,
                        "high": [c * 1.01 for c in closes],
                        "low": [c * 0.99 for c in closes],
                        "close": closes,
                        "volume": [1000] * pred_len,
                    }
                )
            )
        return paths


@pytest.fixture(autouse=True)
def _patch_history(monkeypatch):
    monkeypatch.setattr(viz, "_fetch_history", lambda symbol, history_bars: _history())


def test_base_config_pins_bigger_model():
    cfg = viz.base_config()
    assert cfg.model == viz.BASE_MODEL
    assert cfg.tokenizer == viz.BASE_TOKENIZER


def test_forecast_for_chart_payload_shape():
    cfg = KronosConfig(model=viz.BASE_MODEL, tokenizer=viz.BASE_TOKENIZER, pred_len=10, sample_paths=15)
    fc = viz.forecast_for_chart("RELIANCE", config=cfg, forecaster=_FakeForecaster(cfg))

    assert fc.ok
    assert fc.symbol == "RELIANCE"
    assert fc.history is not None and len(fc.history) >= 30
    assert len(fc.forecast_dates) == 10
    assert list(fc.bands.columns) == ["p10", "p25", "p50", "p75", "p90"]
    assert len(fc.bands) == 10
    # Cone is ordered p10 <= p50 <= p90 at every step.
    assert (fc.bands["p10"] <= fc.bands["p50"]).all()
    assert (fc.bands["p50"] <= fc.bands["p90"]).all()
    assert fc.signal is not None
    assert fc.n_paths == 15
    assert fc.model == viz.BASE_MODEL


def test_forecast_for_chart_insufficient_history(monkeypatch):
    monkeypatch.setattr(viz, "_fetch_history", lambda symbol, history_bars: _history(10))
    fc = viz.forecast_for_chart("TINY", forecaster=_FakeForecaster())
    assert not fc.ok
    assert "insufficient" in (fc.error or "")


def test_forecast_many_isolates_bad_symbol(monkeypatch):
    def _fetch(symbol, history_bars):
        if symbol == "BAD":
            raise RuntimeError("network boom")
        return _history()

    monkeypatch.setattr(viz, "_fetch_history", _fetch)
    monkeypatch.setattr(viz, "KronosForecaster", _FakeForecaster)
    results = viz.forecast_many_for_chart(["RELIANCE", "BAD"])
    assert len(results) == 2
    assert results[0].ok
    assert not results[1].ok and "boom" in (results[1].error or "")
