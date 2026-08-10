"""Chart-ready Kronos forecasting for the visualization UI.

This is a *standalone* module (no strategy/backtest coupling): given a ticker it
fetches full daily price history, runs the Kronos-base model to sample forecast
paths, and returns a payload ready to plot — historical candles, a forecast
percentile cone (p10/p25/p50/p75/p90 of close per future step), the last close,
and a :class:`kronos.signals.KronosSignal` summary.

Design notes
------------
* Defaults to the larger **Kronos-base** model (``NeoQuasar/Kronos-base``) for
  the best zero-shot quality on CPU. Callers can override via ``config``.
* The model only consumes the most recent ``clamped_lookback`` bars (<= the 512
  context window); the chart, however, shows a longer ``history_bars`` window so
  the forecast has visual context.
* Forecasts are honest but **indicative** — zero-shot Kronos on daily NSE bars is
  out-of-distribution, so we surface a distribution cone rather than a single
  confident price line, and the UI shows a caveat.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from .config import KronosConfig
from .predictor import KronosForecaster, KronosUnavailable
from .service import (
    _normalise,
    _plain_symbol,
    _yf_symbol,
    fetch_ohlcv,
    prepare_inputs,
)
from .signals import KronosSignal, derive_signal

logger = logging.getLogger("kronos.viz")

# The bigger/better model, used by default for the visualization page.
BASE_MODEL = "NeoQuasar/Kronos-base"
BASE_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"

# Percentiles used for the forecast cone.
_QUANTILES = [0.1, 0.25, 0.5, 0.75, 0.9]
_QUANTILE_COLS = ["p10", "p25", "p50", "p75", "p90"]


def base_config(**overrides) -> KronosConfig:
    """A :class:`KronosConfig` pinned to Kronos-base with optional overrides."""
    params = dict(model=BASE_MODEL, tokenizer=BASE_TOKENIZER)
    params.update(overrides)
    return KronosConfig(**params)


@dataclass
class ChartForecast:
    """Everything the UI needs to render one stock's Kronos forecast."""

    symbol: str
    history: Optional[pd.DataFrame] = None  # index=date, cols open/high/low/close/volume
    forecast_dates: List[pd.Timestamp] = field(default_factory=list)
    bands: Optional[pd.DataFrame] = None  # index=forecast_date, cols p10..p90 (close)
    last_close: Optional[float] = None
    last_date: Optional[pd.Timestamp] = None
    signal: Optional[KronosSignal] = None
    model: str = BASE_MODEL
    n_paths: int = 0
    pred_len: int = 0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.bands is not None


def _fetch_history(symbol: str, history_bars: int) -> Optional[pd.DataFrame]:
    """Fetch up to ``history_bars`` recent daily bars for chart context."""
    import yfinance as yf

    period_days = history_bars * 2 + 60
    raw = yf.download(
        _yf_symbol(symbol),
        period=f"{period_days}d",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    df = _normalise(raw)
    if df is None or df.empty:
        return None
    return df.tail(history_bars)


def _bands_from_paths(
    paths: List[pd.DataFrame], forecast_dates: List[pd.Timestamp]
) -> pd.DataFrame:
    """Per-step close percentiles across the sampled paths → the forecast cone."""
    # Stack each path's close column: rows = step, cols = path.
    closes = pd.DataFrame({i: p["close"].reset_index(drop=True) for i, p in enumerate(paths)})
    q = closes.quantile(_QUANTILES, axis=1).T  # rows = step, cols = quantiles
    q.columns = _QUANTILE_COLS
    q.index = pd.DatetimeIndex(forecast_dates[: len(q)])
    return q


def forecast_for_chart(
    symbol: str,
    *,
    config: Optional[KronosConfig] = None,
    forecaster: Optional[KronosForecaster] = None,
    history_bars: int = 250,
) -> ChartForecast:
    """Fetch history → run Kronos-base → return a chart-ready :class:`ChartForecast`.

    Never raises for per-symbol data problems (captured in ``error``); a missing
    Kronos/torch install (:class:`KronosUnavailable`) *is* re-raised so callers can
    show install guidance once for the whole batch.
    """
    cfg = config or base_config()
    plain = _plain_symbol(symbol)

    history = _fetch_history(symbol, history_bars)
    if history is None or len(history) < 30:
        return ChartForecast(plain, error="insufficient price history", model=cfg.model)

    # Feed only the most recent clamped_lookback bars to the model.
    model_df = history.tail(cfg.clamped_lookback())
    x_df, x_ts, y_ts = prepare_inputs(model_df, cfg.pred_len)
    last_close = float(model_df["close"].iloc[-1])
    last_date = pd.Timestamp(model_df.index[-1])
    forecast_dates = list(pd.to_datetime(y_ts))

    fc = forecaster or KronosForecaster(cfg)
    paths = fc.predict_paths(
        x_df, x_ts, y_ts, pred_len=cfg.pred_len, sample_paths=cfg.sample_paths
    )
    if not paths:
        return ChartForecast(
            plain, history=history, last_close=last_close, last_date=last_date,
            error="model returned no forecast paths", model=cfg.model,
        )

    bands = _bands_from_paths(paths, forecast_dates)
    signal = derive_signal(plain, last_close, paths, horizon=cfg.pred_len)

    return ChartForecast(
        symbol=plain,
        history=history,
        forecast_dates=forecast_dates,
        bands=bands,
        last_close=last_close,
        last_date=last_date,
        signal=signal,
        model=cfg.model,
        n_paths=len(paths),
        pred_len=cfg.pred_len,
    )


def forecast_many_for_chart(
    symbols: List[str],
    *,
    config: Optional[KronosConfig] = None,
    history_bars: int = 250,
) -> List[ChartForecast]:
    """Forecast several tickers sharing one loaded Kronos-base model."""
    cfg = config or base_config()
    forecaster = KronosForecaster(cfg)
    out: List[ChartForecast] = []
    for sym in symbols:
        try:
            out.append(
                forecast_for_chart(
                    sym, config=cfg, forecaster=forecaster, history_bars=history_bars
                )
            )
        except KronosUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - isolate one bad symbol
            logger.warning("Chart forecast failed for %s: %s", sym, exc)
            out.append(ChartForecast(_plain_symbol(sym), error=str(exc), model=cfg.model))
    return out


__all__ = [
    "ChartForecast",
    "base_config",
    "forecast_for_chart",
    "forecast_many_for_chart",
    "BASE_MODEL",
    "BASE_TOKENIZER",
]
