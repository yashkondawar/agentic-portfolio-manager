"""
Risk Manager Agent — Volatility-adjusted position sizing.

Computes per-ticker position limits based on:
1. Annualized volatility (higher vol → smaller position)
2. Correlation with other positions (higher corr → smaller position)

No LLM needed — pure quantitative.
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List

from agents.models import RiskMetrics

logger = logging.getLogger(__name__)


def _get_price_histories(symbols: List[str], period: str = "3mo") -> Dict[str, pd.Series]:
    """Fetch close price series for multiple symbols."""
    import yfinance as yf

    histories = {}
    for symbol in symbols:
        ticker_symbol = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
        try:
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(period=period, interval="1d")
            if not df.empty:
                histories[symbol] = df["Close"]
        except Exception as e:
            logger.warning(f"Could not fetch history for {symbol}: {e}")

    return histories


def _calculate_volatility(close_series: pd.Series) -> Dict[str, float]:
    """Calculate volatility metrics for a single stock."""
    returns = close_series.pct_change().dropna()

    if len(returns) < 20:
        return {
            "daily_volatility": 0.02,
            "annualized_volatility": 0.30,
            "volatility_percentile": 50.0,
        }

    recent_returns = returns.tail(60)
    daily_vol = recent_returns.std()
    annualized_vol = daily_vol * np.sqrt(252)

    # Percentile rank
    rolling_vol = returns.rolling(20).std().dropna()
    if len(rolling_vol) > 0:
        vol_percentile = (rolling_vol <= daily_vol).mean() * 100
    else:
        vol_percentile = 50.0

    return {
        "daily_volatility": float(daily_vol),
        "annualized_volatility": float(annualized_vol),
        "volatility_percentile": float(vol_percentile),
    }


def _volatility_adjusted_limit(annualized_vol: float) -> float:
    """
    Compute max position size as % of portfolio based on volatility.
    Low vol → larger position (up to 25%), High vol → smaller (down to 5%).
    """
    base_limit = 0.20  # 20% baseline

    if annualized_vol < 0.15:
        multiplier = 1.25
    elif annualized_vol < 0.30:
        multiplier = 1.0 - (annualized_vol - 0.15) * 3.33  # Linear decay
    elif annualized_vol < 0.50:
        multiplier = 0.50 - (annualized_vol - 0.30) * 1.25
    else:
        multiplier = 0.25

    multiplier = max(min(multiplier, 1.25), 0.25)
    return base_limit * multiplier


def _correlation_multiplier(avg_correlation: float) -> float:
    """
    Adjust position limit based on correlation with existing positions.
    High correlation → reduce, Low correlation → slight increase.
    """
    if avg_correlation >= 0.80:
        return 0.70
    elif avg_correlation >= 0.60:
        return 0.85
    elif avg_correlation >= 0.40:
        return 1.00
    elif avg_correlation >= 0.20:
        return 1.05
    else:
        return 1.10


def analyze_risk(
    symbols: List[str],
    portfolio_value: float = 1000000.0,  # Default ₹10 Lakh
) -> Dict[str, RiskMetrics]:
    """
    Compute risk metrics and position limits for all tickers.

    Args:
        symbols: List of NSE stock symbols to analyze
        portfolio_value: Total portfolio value in ₹

    Returns:
        Dict mapping symbol → RiskMetrics
    """
    logger.info(f"Risk analysis for {symbols}")

    try:
        # Fetch all price histories
        histories = _get_price_histories(symbols, period="3mo")

        if not histories:
            # Return default limits if no data
            default_limit = portfolio_value * 0.15
            return {
                symbol: RiskMetrics(
                    daily_volatility=0.02,
                    annualized_volatility=0.30,
                    volatility_percentile=50.0,
                    max_position_pct=15.0,
                    max_position_value=default_limit,
                    reasoning="Default limit (no historical data available)",
                )
                for symbol in symbols
            }

        # Calculate correlation matrix
        returns_df = pd.DataFrame(
            {sym: series.pct_change().dropna() for sym, series in histories.items()}
        ).dropna()

        corr_matrix = returns_df.corr() if len(returns_df) > 10 else pd.DataFrame()

        # Compute per-ticker risk metrics
        results = {}
        for symbol in symbols:
            if symbol not in histories:
                results[symbol] = RiskMetrics(
                    daily_volatility=0.02,
                    annualized_volatility=0.30,
                    volatility_percentile=50.0,
                    max_position_pct=15.0,
                    max_position_value=portfolio_value * 0.15,
                    reasoning="Default limit (no price data)",
                )
                continue

            # Volatility metrics
            vol_metrics = _calculate_volatility(histories[symbol])

            # Volatility-adjusted position limit
            vol_limit = _volatility_adjusted_limit(vol_metrics["annualized_volatility"])

            # Correlation adjustment
            if not corr_matrix.empty and symbol in corr_matrix.columns:
                other_corrs = corr_matrix[symbol].drop(symbol, errors="ignore")
                avg_corr = other_corrs.mean() if len(other_corrs) > 0 else 0
            else:
                avg_corr = 0.3  # Assume moderate correlation

            corr_mult = _correlation_multiplier(avg_corr)

            # Final position limit
            final_limit_pct = vol_limit * corr_mult * 100  # Convert to percentage
            final_limit_value = portfolio_value * (final_limit_pct / 100)

            reasoning = (
                f"Vol={vol_metrics['annualized_volatility']:.1%} → base limit {vol_limit:.1%}. "
                f"Avg corr={avg_corr:.2f} → mult {corr_mult:.2f}. "
                f"Final: {final_limit_pct:.1f}% = ₹{final_limit_value/1e5:.1f}L"
            )

            results[symbol] = RiskMetrics(
                daily_volatility=vol_metrics["daily_volatility"],
                annualized_volatility=vol_metrics["annualized_volatility"],
                volatility_percentile=vol_metrics["volatility_percentile"],
                max_position_pct=round(final_limit_pct, 1),
                max_position_value=round(final_limit_value, 0),
                reasoning=reasoning,
            )

        return results

    except Exception as e:
        logger.error(f"Risk analysis failed: {e}")
        default_limit = portfolio_value * 0.15
        return {
            symbol: RiskMetrics(
                daily_volatility=0.02,
                annualized_volatility=0.30,
                volatility_percentile=50.0,
                max_position_pct=15.0,
                max_position_value=default_limit,
                reasoning=f"Error fallback: {str(e)[:60]}",
            )
            for symbol in symbols
        }
