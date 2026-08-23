"""Tests for the Market Temperature research module.

These pin down the specific bugs that made the original framework unusable, so
that a future refactor cannot quietly reintroduce them. Everything runs on
synthetic series constructed in-test — no network access.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.market_temperature.config import (
    RULE_SPECS,
    TEMPERATURE_BANDS,
    classify_score,
)
from research.market_temperature.data import (
    MarketDataUnavailable,
    to_month_end_total_return,
)
from research.market_temperature.service import _rank_within_sign
from research.market_temperature.signals import (
    TOTAL_WEIGHT,
    composite_score,
    current_drawdown_pct,
    evaluate_rules,
    rule_3y_flat,
    rule_drawdown,
    trailing_cagr_pct,
    trailing_return_pct,
)


def _series(values: list[float], *, end: str = "2026-01-31") -> pd.Series:
    index = pd.date_range(end=end, periods=len(values), freq="ME")
    return pd.Series(values, index=index, dtype=float)


def _compounding(months: int, annual_rate: float, start: float = 100.0) -> pd.Series:
    """A series growing at a constant annual rate, so CAGR is stable at any point."""
    monthly = (1.0 + annual_rate) ** (1 / 12) - 1.0
    return _series([start * (1 + monthly) ** i for i in range(months)])


def _flat_then(months: int, start: float, end: float) -> pd.Series:
    return _series(list(np.linspace(start, end, months)))


# --------------------------------------------------------------------------- #
# Window primitives
# --------------------------------------------------------------------------- #


def test_trailing_return_handles_fractional_years():
    """The original raised ValueError on any non-integer year window."""
    series = _flat_then(120, 100.0, 200.0)
    asof = series.index[-1]
    assert trailing_return_pct(series, asof, 0.5) is not None
    assert trailing_return_pct(series, asof, 1.5) is not None
    assert trailing_return_pct(series, asof, 2.25) is not None


def test_trailing_return_is_none_without_enough_history():
    series = _flat_then(24, 100.0, 110.0)
    assert trailing_return_pct(series, series.index[-1], 12) is None


def test_trailing_cagr_matches_known_doubling():
    series = _series([100.0] * 64 + [200.0])
    cagr = trailing_cagr_pct(series, series.index[-1], 5)
    assert cagr == pytest.approx(14.87, abs=0.3)


# --------------------------------------------------------------------------- #
# Bug B4: the falling-knife rule
# --------------------------------------------------------------------------- #


def test_three_year_rule_rejects_a_crash():
    """A 65% collapse must never be scored as a quiet sideways market.

    The original band was `ret <= +10%` with no lower bound, so a crash was
    labelled 'aggressive contrarian accumulation'.
    """
    series = _series([100.0] * 40 + [35.0])
    reading = rule_3y_flat(series, series.index[-1])
    assert reading.score == 0.0
    assert "decline" in reading.detail.lower()


def test_three_year_rule_accepts_genuine_drift():
    series = _series([100.0] * 40 + [104.0])
    reading = rule_3y_flat(series, series.index[-1])
    assert reading.score == 1.0
    assert "sideways" in reading.detail.lower()


def test_three_year_rule_rejects_a_strong_rally():
    series = _series([100.0] * 40 + [180.0])
    reading = rule_3y_flat(series, series.index[-1])
    assert reading.score == 0.0


# --------------------------------------------------------------------------- #
# Bug B5: correction rule firing after recovery
# --------------------------------------------------------------------------- #


def test_drawdown_uses_current_level_not_window_maximum():
    """Crash then full recovery must NOT read as a live correction."""
    series = _series([100.0] * 6 + [60.0] + [100.0] * 5)
    asof = series.index[-1]
    assert current_drawdown_pct(series, asof, months=12) == pytest.approx(0.0, abs=1e-6)
    assert rule_drawdown(series, asof).score == 0.0


def test_drawdown_fires_while_still_depressed():
    series = _series([100.0] * 6 + [100.0] * 5 + [58.0])
    reading = rule_drawdown(series, series.index[-1])
    assert reading.score == 2.0
    assert 30.0 <= (reading.observed or 0) <= 55.0


def test_drawdown_beyond_band_is_not_treated_as_opportunity():
    series = _series([100.0] * 11 + [25.0])
    reading = rule_drawdown(series, series.index[-1])
    assert reading.score == 0.0
    assert "structural" in reading.detail.lower()


# --------------------------------------------------------------------------- #
# Composite comparability
# --------------------------------------------------------------------------- #


def test_composite_denominator_is_constant_regardless_of_history():
    """Unevaluable rules must stay in the denominator.

    The original dropped them, so the same market conditions produced different
    scores depending only on how much history happened to be loaded.
    """
    short = _compounding(72, 0.12)
    long = _compounding(400, 0.12)

    short_readings = evaluate_rules(short, short.index[-1])
    long_readings = evaluate_rules(long, long.index[-1])

    assert any(r.score is None for r in short_readings)
    assert all(r.score is not None for r in long_readings)

    # Denominator is fixed, so an unevaluable rule can only pull toward zero.
    assert abs(composite_score(short_readings)) <= 2.0
    assert TOTAL_WEIGHT == sum(spec.weight for spec in RULE_SPECS.values())


def test_composite_is_zero_when_nothing_fires():
    """A market compounding at a healthy but unremarkable rate trips no rule."""
    series = _compounding(400, 0.12)
    readings = evaluate_rules(series, series.index[-1])
    assert all(r.score == 0.0 for r in readings)
    assert composite_score(readings) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# Banding: the "silent signal must not look confident" rule
# --------------------------------------------------------------------------- #


def test_zero_score_is_always_neutral():
    """Regression: a silent signal previously ranked in the 82nd percentile and
    was labelled 'Cool - deploy faster'."""
    for rank in (0.0, 0.5, 0.95, 1.0):
        assert classify_score(0.0, rank) is TEMPERATURE_BANDS["neutral"]


def test_positive_scores_map_to_cheap_bands():
    assert classify_score(0.2, 0.1) is TEMPERATURE_BANDS["cool"]
    assert classify_score(0.2, 0.9) is TEMPERATURE_BANDS["cold"]


def test_negative_scores_map_to_expensive_bands():
    assert classify_score(-0.2, 0.1) is TEMPERATURE_BANDS["warm"]
    assert classify_score(-0.2, 0.9) is TEMPERATURE_BANDS["hot"]


def test_rank_within_sign_ignores_opposite_sign_history():
    scores = pd.Series([0.0] * 50 + [-0.5, -0.4, 0.1, 0.3])
    # 0.1 is the weakest of the two positive readings.
    assert _rank_within_sign(0.1, scores) == pytest.approx(0.5)
    assert _rank_within_sign(0.3, scores) == pytest.approx(1.0)


def test_rank_within_sign_is_zero_for_neutral():
    scores = pd.Series([0.0, 0.2, -0.2])
    assert _rank_within_sign(0.0, scores) == 0.0


# --------------------------------------------------------------------------- #
# Total-return conversion
# --------------------------------------------------------------------------- #


def test_total_return_index_exceeds_price_index():
    dates = pd.date_range("2010-01-01", periods=365 * 6, freq="D")
    flat = pd.Series(100.0, index=dates)
    total_return = to_month_end_total_return(flat, 0.013)
    years = (total_return.index[-1] - total_return.index[0]).days / 365.25
    implied = total_return.iloc[-1] ** (1 / years) - 1
    assert implied == pytest.approx(0.013, abs=0.001)


def test_total_return_rejects_a_series_that_is_too_short():
    dates = pd.date_range("2010-01-01", periods=5, freq="D")
    with pytest.raises(MarketDataUnavailable):
        to_month_end_total_return(pd.Series(100.0, index=dates), 0.013)


# --------------------------------------------------------------------------- #
# No silent fabrication
# --------------------------------------------------------------------------- #


def test_download_failure_raises_rather_than_substituting_data(monkeypatch):
    """The original fell back to a seeded random walk and logged a warning."""
    from research.market_temperature import data as data_module

    class _Dead:
        def __init__(self, *_args, **_kwargs):
            pass

        def history(self, **_kwargs):
            return pd.DataFrame()

    monkeypatch.setattr(data_module, "get_cache", lambda *a, **k: None)
    monkeypatch.setitem(
        __import__("sys").modules, "yfinance", type("m", (), {"Ticker": _Dead})
    )
    with pytest.raises(MarketDataUnavailable):
        data_module._download("^DELISTED")
