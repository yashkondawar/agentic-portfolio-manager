"""
Technical Analyst Agent — 5-Strategy Weighted Ensemble.

Computes technical signals using:
1. Trend Following (25%) — EMA crossovers + ADX
2. Mean Reversion (20%) — Z-score + Bollinger + RSI
3. Momentum (25%) — Multi-timeframe momentum + volume confirmation
4. Volatility (15%) — Volatility regime analysis
5. Statistical Arbitrage (15%) — Hurst exponent + skewness

All computation is quantitative (no LLM needed for scoring).
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple

from agents.models import AnalystSignal, TechnicalMetrics

logger = logging.getLogger(__name__)

STRATEGY_WEIGHTS = {
    "trend": 0.25,
    "mean_reversion": 0.20,
    "momentum": 0.25,
    "volatility": 0.15,
    "stat_arb": 0.15,
}


def _get_price_history(symbol: str) -> pd.DataFrame:
    """Fetch 1-year daily OHLCV data via the unified data provider."""
    from scraper.data_provider import get_stock_data

    data = get_stock_data(symbol)
    df = data.price_history

    if df is not None and not df.empty:
        logger.info(
            f"[TECHNICAL] {symbol}: Fetched {len(df)} days of price data | "
            f"Range: {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')} | "
            f"Last close=₹{df['Close'].iloc[-1]:,.2f}, Vol={df['Volume'].iloc[-1]:,.0f}"
        )
        return df
    else:
        logger.warning(f"[TECHNICAL] {symbol}: No price data available")
        return pd.DataFrame()


def _calculate_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _calculate_adx(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate ADX (Average Directional Index)."""
    high, low, close = df["High"], df["Low"], df["Close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx = dx.rolling(period).mean()

    return adx.iloc[-1] if not adx.empty else 25.0


def _calculate_hurst(series: pd.Series, max_lag: int = 20) -> float:
    """Calculate Hurst exponent. H<0.5=mean-reverting, H=0.5=random, H>0.5=trending."""
    lags = range(2, min(max_lag, len(series) // 2))
    tau = []
    for lag in lags:
        tau.append(np.std(series.iloc[lag:].values - series.iloc[:-lag].values))

    if len(tau) < 2 or any(t == 0 for t in tau):
        return 0.5

    log_lags = np.log(list(lags))
    log_tau = np.log(tau)

    # Linear regression
    coeffs = np.polyfit(log_lags, log_tau, 1)
    return coeffs[0]


def strategy_trend(df: pd.DataFrame) -> Tuple[str, float, Dict]:
    """Strategy 1: Trend Following (EMA crossovers + ADX)."""
    close = df["Close"]

    ema_8 = _calculate_ema(close, 8)
    ema_21 = _calculate_ema(close, 21)
    ema_55 = _calculate_ema(close, 55)
    adx = _calculate_adx(df, 14)

    short_trend = ema_8.iloc[-1] > ema_21.iloc[-1]
    medium_trend = ema_21.iloc[-1] > ema_55.iloc[-1]
    trend_strength = min(adx / 100.0, 1.0)

    if short_trend and medium_trend:
        signal = "bullish"
        confidence = trend_strength * 80
    elif not short_trend and not medium_trend:
        signal = "bearish"
        confidence = trend_strength * 80
    else:
        signal = "neutral"
        confidence = 40

    return signal, confidence, {"adx": adx, "trend_strength": trend_strength}


def strategy_mean_reversion(df: pd.DataFrame) -> Tuple[str, float, Dict]:
    """Strategy 2: Mean Reversion (Z-score + Bollinger + RSI)."""
    close = df["Close"]

    ma_50 = close.rolling(50).mean()
    std_50 = close.rolling(50).std()
    z_score = ((close - ma_50) / std_50).iloc[-1]

    # Bollinger Bands
    bb_ma = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = (bb_ma + 2 * bb_std).iloc[-1]
    bb_lower = (bb_ma - 2 * bb_std).iloc[-1]

    price_vs_bb = (close.iloc[-1] - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

    rsi = _calculate_rsi(close, 14).iloc[-1]

    if z_score < -1.5 and price_vs_bb < 0.2 and rsi < 35:
        signal = "bullish"
        confidence = min(abs(z_score) / 3 * 80, 90)
    elif z_score > 1.5 and price_vs_bb > 0.8 and rsi > 65:
        signal = "bearish"
        confidence = min(abs(z_score) / 3 * 80, 90)
    else:
        signal = "neutral"
        confidence = 40

    return signal, confidence, {"z_score": z_score, "price_vs_bb": price_vs_bb, "rsi": rsi}


def strategy_momentum(df: pd.DataFrame) -> Tuple[str, float, Dict]:
    """Strategy 3: Momentum (multi-timeframe + volume confirmation)."""
    close = df["Close"]
    volume = df["Volume"]
    returns = close.pct_change()

    mom_1m = returns.rolling(21).sum().iloc[-1] if len(returns) > 21 else 0
    mom_3m = returns.rolling(63).sum().iloc[-1] if len(returns) > 63 else 0
    mom_6m = returns.rolling(126).sum().iloc[-1] if len(returns) > 126 else 0

    # Weighted composite
    momentum_score = 0.4 * mom_1m + 0.3 * mom_3m + 0.3 * mom_6m

    # Volume confirmation
    vol_avg = volume.rolling(21).mean().iloc[-1]
    volume_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1.0
    volume_confirmation = volume_ratio > 1.0

    if momentum_score > 0.03 and volume_confirmation:
        signal = "bullish"
        confidence = min(abs(momentum_score) * 400, 90)
    elif momentum_score < -0.03 and volume_confirmation:
        signal = "bearish"
        confidence = min(abs(momentum_score) * 400, 90)
    else:
        signal = "neutral"
        confidence = 40

    return signal, confidence, {
        "mom_1m": mom_1m, "mom_3m": mom_3m, "mom_6m": mom_6m,
        "volume_ratio": volume_ratio
    }


def strategy_volatility(df: pd.DataFrame) -> Tuple[str, float, Dict]:
    """Strategy 4: Volatility regime analysis."""
    close = df["Close"]
    returns = close.pct_change().dropna()

    hist_vol = returns.rolling(21).std() * np.sqrt(252)
    vol_ma = hist_vol.rolling(63).mean()

    if vol_ma.iloc[-1] > 0:
        vol_regime = hist_vol.iloc[-1] / vol_ma.iloc[-1]
    else:
        vol_regime = 1.0

    vol_std = hist_vol.rolling(63).std()
    vol_z = (hist_vol.iloc[-1] - vol_ma.iloc[-1]) / vol_std.iloc[-1] if vol_std.iloc[-1] > 0 else 0

    # Low vol + expanding = bullish setup; High vol + contracting = bearish
    if vol_regime < 0.8 and vol_z < -1:
        signal = "bullish"
        confidence = min(abs(vol_z) / 2 * 70, 80)
    elif vol_regime > 1.3 and vol_z > 1:
        signal = "bearish"
        confidence = min(abs(vol_z) / 2 * 70, 80)
    else:
        signal = "neutral"
        confidence = 40

    return signal, confidence, {
        "annualized_vol": float(hist_vol.iloc[-1]),
        "vol_regime": vol_regime,
        "vol_z_score": vol_z,
    }


def strategy_stat_arb(df: pd.DataFrame) -> Tuple[str, float, Dict]:
    """Strategy 5: Statistical Arbitrage (Hurst + skewness)."""
    close = df["Close"]
    returns = close.pct_change().dropna()

    # Hurst exponent
    hurst = _calculate_hurst(close.dropna(), max_lag=20)

    # Skewness and kurtosis
    skew = returns.rolling(63).skew().iloc[-1] if len(returns) > 63 else 0
    kurt = returns.rolling(63).kurt().iloc[-1] if len(returns) > 63 else 0

    # Mean-reverting + positive skew = bullish opportunity
    if hurst < 0.4 and skew > 0.5:
        signal = "bullish"
        confidence = (0.5 - hurst) * 150
    elif hurst < 0.4 and skew < -0.5:
        signal = "bearish"
        confidence = (0.5 - hurst) * 150
    elif hurst > 0.6:
        # Trending market — defer to trend strategy
        signal = "neutral"
        confidence = 30
    else:
        signal = "neutral"
        confidence = 40

    confidence = min(confidence, 80)

    return signal, confidence, {"hurst": hurst, "skewness": skew, "kurtosis": kurt}


def analyze_technical(symbol: str) -> Dict[str, Any]:
    """
    Run full 5-strategy technical analysis for a ticker.
    Returns structured signal + metrics.
    """
    logger.info(f"Technical analysis for {symbol}")

    try:
        df = _get_price_history(symbol)
        if df.empty or len(df) < 60:
            return {
                "signal": AnalystSignal(
                    signal="neutral", confidence=0,
                    reasoning=f"Insufficient price history for {symbol}"
                ),
                "metrics": None,
            }

        # Run all 5 strategies
        strategies = {
            "trend": strategy_trend(df),
            "mean_reversion": strategy_mean_reversion(df),
            "momentum": strategy_momentum(df),
            "volatility": strategy_volatility(df),
            "stat_arb": strategy_stat_arb(df),
        }

        # Weighted combination
        signal_values = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}
        weighted_sum = 0
        total_weight = 0

        for name, (sig, conf, _) in strategies.items():
            weight = STRATEGY_WEIGHTS[name]
            weighted_sum += signal_values[sig] * weight * (conf / 100)
            total_weight += weight * (conf / 100)

        if total_weight > 0:
            final_score = weighted_sum / total_weight
        else:
            final_score = 0

        # Determine final signal
        if final_score > 0.2:
            final_signal = "bullish"
        elif final_score < -0.2:
            final_signal = "bearish"
        else:
            final_signal = "neutral"

        final_confidence = min(abs(final_score) * 100, 95)

        # Build reasoning
        strategy_summaries = []
        for name, (sig, conf, _) in strategies.items():
            strategy_summaries.append(f"{name}:{sig}({conf:.0f}%)")
        reasoning = f"5-strategy ensemble: {', '.join(strategy_summaries)}. Score={final_score:.2f}"

        metrics = TechnicalMetrics(
            rsi=_calculate_rsi(df["Close"], 14).iloc[-1],
            macd_trend=strategies["trend"][0],
            adx=strategies["trend"][2].get("adx"),
            trend_score=strategies["trend"][1],
            mean_reversion_score=strategies["mean_reversion"][1],
            momentum_score=strategies["momentum"][1],
            volatility_score=strategies["volatility"][1],
            stat_arb_score=strategies["stat_arb"][1],
            overall_score=final_score * 100,
        )

        return {
            "signal": AnalystSignal(
                signal=final_signal,
                confidence=final_confidence,
                reasoning=reasoning,
            ),
            "metrics": metrics,
        }

    except Exception as e:
        logger.error(f"Technical analysis failed for {symbol}: {e}")
        return {
            "signal": AnalystSignal(
                signal="neutral", confidence=0,
                reasoning=f"Analysis error: {str(e)[:80]}"
            ),
            "metrics": None,
        }
