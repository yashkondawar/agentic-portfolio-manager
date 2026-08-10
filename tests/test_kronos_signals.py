"""Unit tests for the pure Kronos signal-derivation layer.

These exercise :func:`kronos.signals.derive_signal` with hand-built forecast
frames — no torch, no network, no GPU — so they run anywhere.
"""

from __future__ import annotations

import pandas as pd
import pytest

from kronos.signals import derive_signal, signals_to_frame


def _path(closes, highs=None, lows=None) -> pd.DataFrame:
    n = len(closes)
    highs = highs or [c * 1.01 for c in closes]
    lows = lows or [c * 0.99 for c in closes]
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000] * n,
        }
    )


def test_bullish_paths_produce_buy():
    last_close = 100.0
    # All paths finish clearly higher with a favourable cone.
    paths = [
        _path([101, 103, 106], highs=[102, 104, 108], lows=[100, 101, 104]),
        _path([102, 104, 107], highs=[103, 105, 109], lows=[101, 102, 105]),
        _path([101, 102, 105], highs=[102, 103, 107], lows=[100, 101, 103]),
    ]
    sig = derive_signal("TEST", last_close, paths, horizon=3)

    assert sig.direction == "BUY"
    assert sig.prob_up == 1.0
    assert sig.expected_return > 0
    assert sig.expected_close > last_close
    assert sig.suggested_target > last_close
    assert sig.suggested_stop < last_close
    assert sig.reward_risk >= 1.5
    assert sig.confidence == "HIGH"
    assert sig.n_paths == 3


def test_bearish_paths_produce_avoid():
    last_close = 100.0
    paths = [
        _path([98, 96, 94]),
        _path([99, 97, 95]),
        _path([98, 95, 93]),
    ]
    sig = derive_signal("TEST", last_close, paths, horizon=3)

    assert sig.direction == "AVOID"
    assert sig.prob_up == 0.0
    assert sig.expected_return < 0


def test_mixed_paths_produce_hold():
    last_close = 100.0
    # Roughly balanced up/down, small expected move -> no strong edge.
    paths = [
        _path([101, 100.5, 100.6]),
        _path([99, 99.5, 99.4]),
        _path([100.2, 100.1, 100.3]),
        _path([99.8, 99.9, 99.7]),
    ]
    sig = derive_signal("TEST", last_close, paths, horizon=3)

    assert sig.direction == "HOLD"
    assert 0.0 < sig.prob_up < 1.0
    assert sig.confidence in {"LOW", "MEDIUM"}


def test_prob_up_and_volatility_computed_across_paths():
    last_close = 100.0
    paths = [_path([110, 110, 110]), _path([90, 90, 90])]  # one up, one down
    sig = derive_signal("TEST", last_close, paths, horizon=3)

    assert sig.prob_up == 0.5
    assert sig.expected_close == pytest.approx(100.0, abs=1e-6)
    assert sig.forecast_volatility > 0  # dispersion between +10% and -10%


def test_horizon_inferred_from_path_length():
    sig = derive_signal("TEST", 100.0, [_path([101, 102, 103, 104])])
    assert sig.horizon == 4


def test_high_low_optional_falls_back_to_close():
    last_close = 100.0
    path = pd.DataFrame({"close": [101.0, 102.0, 103.0]})  # no high/low columns
    sig = derive_signal("TEST", last_close, [path], horizon=3)
    assert sig.predicted_high >= last_close
    assert sig.predicted_low <= 103.0


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        derive_signal("TEST", 0.0, [_path([101])])  # non-positive last_close
    with pytest.raises(ValueError):
        derive_signal("TEST", 100.0, [])  # no paths


def test_signals_to_frame_orders_buys_first():
    last_close = 100.0
    buy = derive_signal("BUY1", last_close, [_path([105, 106, 108])] * 3, horizon=3)
    avoid = derive_signal("AVD1", last_close, [_path([95, 94, 92])] * 3, horizon=3)
    frame = signals_to_frame([avoid, buy])

    assert list(frame["symbol"]) == ["BUY1", "AVD1"]
    assert frame.iloc[0]["direction"] == "BUY"


def test_signals_to_frame_empty():
    assert signals_to_frame([]).empty
