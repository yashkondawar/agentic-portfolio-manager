"""Index price loading for the Market Temperature module.

Design rule: **there is no fallback**. The original framework silently
substituted a seeded random walk whenever a download failed, and then printed
the results as though they were real. Two of the indices it shipped with are
delisted on Yahoo, so several of its published signals were pure noise.

Here, a failed download raises. A dashboard that says "I don't know" is useful.
A dashboard that quietly invents numbers is worse than no dashboard.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from core.storage import get_cache, put_cache

from .config import CACHE_NAMESPACE, CACHE_TTL_HOURS, Market

logger = logging.getLogger(__name__)


class MarketDataUnavailable(RuntimeError):
    """Raised when an index cannot be loaded. Never swallowed silently."""


def _download(ticker: str) -> pd.Series:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise MarketDataUnavailable(
            "yfinance is not installed; cannot load index history."
        ) from exc

    try:
        frame = yf.Ticker(ticker).history(
            period="max", interval="1d", auto_adjust=False
        )
    except Exception as exc:
        raise MarketDataUnavailable(f"Download failed for {ticker}: {exc}") from exc

    if frame is None or frame.empty or "Close" not in frame:
        raise MarketDataUnavailable(
            f"No usable price history returned for {ticker}. "
            "The ticker may have been delisted or renamed."
        )

    close = frame["Close"].dropna()
    if close.empty:
        raise MarketDataUnavailable(f"All closes were NaN for {ticker}.")
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


def _cache_key(ticker: str) -> str:
    return f"close::{ticker}"


def load_daily_close(market: Market, *, refresh: bool = False) -> pd.Series:
    """Daily closing prices for `market`, cached for `CACHE_TTL_HOURS`."""
    key = _cache_key(market.ticker)
    if not refresh:
        entry = get_cache(CACHE_NAMESPACE, key)
        if entry is not None:
            try:
                cached = pd.read_json(io.StringIO(entry.payload.decode()), typ="series")
                cached.index = pd.to_datetime(cached.index)
                if not cached.empty:
                    return cached.astype(float)
            except Exception:
                logger.warning("Discarding unreadable cache entry for %s", market.ticker)

    close = _download(market.ticker)
    put_cache(
        CACHE_NAMESPACE,
        key,
        close.to_json().encode(),
        format="json",
        metadata={"ticker": market.ticker, "rows": len(close)},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=CACHE_TTL_HOURS),
    )
    return close


def to_month_end_total_return(close: pd.Series, div_yield: float) -> pd.Series:
    """Convert a daily price index into a month-end approximate total-return index.

    Dividends are accrued at a constant assumed yield rather than taken from
    actual payout data, which is not available at index level from a free source.
    This is an explicit approximation, and it matters: the long-horizon rules ask
    whether the market "went nowhere", and over 12 years a 1.3% yield compounds
    to roughly 17pp — wider than the +/-15pp band those rules use.
    """
    month_end = close.resample("ME").last().dropna()
    if len(month_end) < 2:
        raise MarketDataUnavailable("Not enough month-end observations to build a series.")
    monthly_dividend = (1.0 + div_yield) ** (1.0 / 12.0) - 1.0
    returns = month_end.pct_change().fillna(0.0) + monthly_dividend
    total_return = (1.0 + returns).cumprod()
    total_return.iloc[0] = 1.0
    return total_return


def load_market(market: Market, *, refresh: bool = False) -> tuple[pd.Series, pd.Series]:
    """Return `(month_end_price, month_end_total_return_index)` for a market."""
    close = load_daily_close(market, refresh=refresh)
    price = close.resample("ME").last().dropna()
    total_return = to_month_end_total_return(close, market.div_yield)
    return price, total_return
