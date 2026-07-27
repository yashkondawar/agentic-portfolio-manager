"""Kronos forecasting service — from a ticker to a trading signal.

This is the façade the strategy (and any nightly batch job) calls. It:

  1. fetches recent daily OHLCV for a symbol (reusing yfinance, like the
     backtest data layer),
  2. prepares the Kronos input frame + historical/future timestamps,
  3. samples forecast paths via :class:`kronos.predictor.KronosForecaster`,
  4. derives a risk-aware :class:`kronos.signals.KronosSignal`.

Only step 3 needs torch/Kronos; steps 1/2/4 are plain pandas. When Kronos is
unavailable the service raises :class:`kronos.predictor.KronosUnavailable`
(carrying install guidance) so callers can surface it cleanly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from .config import KronosConfig
from .predictor import KronosForecaster, KronosUnavailable
from .signals import KronosSignal, derive_signal

logger = logging.getLogger("kronos.service")

_OHLCV = ["open", "high", "low", "close", "volume"]


def _yf_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s.endswith((".NS", ".BO")):
        s = f"{s}.NS"
    return s


def _plain_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".NS", "").replace(".BO", "")


def _normalise(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Lower-cased OHLCV with a tz-naive daily index (mirrors backtest data)."""
    if df is None or df.empty:
        return None
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    rename = {c: c.lower() for c in df.columns}
    df = df.rename(columns=rename)
    keep = [c for c in _OHLCV if c in df.columns]
    df = df[keep].dropna(subset=["close"])
    idx = pd.to_datetime(df.index)
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    df.index = idx.normalize()
    return df[~df.index.duplicated(keep="last")].sort_index()


def fetch_ohlcv(symbol: str, lookback: int, warmup: int = 40) -> Optional[pd.DataFrame]:
    """Download recent daily OHLCV for one symbol (most recent ``lookback`` rows)."""
    import yfinance as yf

    period_days = (lookback + warmup) * 2 + 30  # generous calendar buffer
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
    return df.tail(lookback)


def _future_business_days(last: pd.Timestamp, pred_len: int) -> pd.Series:
    """Generate the next ``pred_len`` business-day timestamps after ``last``."""
    days = pd.bdate_range(start=last + pd.Timedelta(days=1), periods=pred_len)
    return pd.Series(days)


def prepare_inputs(df: pd.DataFrame, pred_len: int):
    """Split a history frame into (x_df, x_timestamp, y_timestamp) for Kronos."""
    x_df = df.reset_index(drop=True)[[c for c in _OHLCV if c in df.columns]].copy()
    x_timestamp = pd.Series(pd.to_datetime(df.index))
    y_timestamp = _future_business_days(pd.Timestamp(df.index[-1]), pred_len)
    return x_df, x_timestamp, y_timestamp


@dataclass
class ForecastResult:
    symbol: str
    signal: Optional[KronosSignal]
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.signal is not None


def forecast_symbol(
    symbol: str,
    *,
    config: Optional[KronosConfig] = None,
    forecaster: Optional[KronosForecaster] = None,
) -> ForecastResult:
    """End-to-end: fetch → forecast → signal for a single symbol."""
    cfg = config or KronosConfig()
    forecaster = forecaster or KronosForecaster(cfg)
    lookback = cfg.clamped_lookback()

    df = fetch_ohlcv(symbol, lookback)
    if df is None or len(df) < 30:
        return ForecastResult(symbol, None, error="insufficient price history")

    x_df, x_ts, y_ts = prepare_inputs(df, cfg.pred_len)
    last_close = float(df["close"].iloc[-1])

    paths = forecaster.predict_paths(
        x_df, x_ts, y_ts, pred_len=cfg.pred_len, sample_paths=cfg.sample_paths
    )
    signal = derive_signal(
        _plain_symbol(symbol), last_close, paths, horizon=cfg.pred_len
    )
    return ForecastResult(symbol, signal)


def forecast_symbols(
    symbols: List[str], *, config: Optional[KronosConfig] = None
) -> List[ForecastResult]:
    """Forecast several symbols, sharing one loaded model. Never raises per-symbol.

    A single :class:`KronosUnavailable` (torch/model missing) is re-raised because
    it applies to every symbol; per-symbol data errors are captured in-result.
    """
    cfg = config or KronosConfig()
    forecaster = KronosForecaster(cfg)
    results: List[ForecastResult] = []
    for sym in symbols:
        try:
            results.append(forecast_symbol(sym, config=cfg, forecaster=forecaster))
        except KronosUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - isolate one bad symbol
            logger.warning("Forecast failed for %s: %s", sym, exc)
            results.append(ForecastResult(sym, None, error=str(exc)))
    return results


__all__ = [
    "ForecastResult",
    "fetch_ohlcv",
    "prepare_inputs",
    "forecast_symbol",
    "forecast_symbols",
]
