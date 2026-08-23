"""Market Temperature: a long-horizon valuation read for deployment decisions.

Not a trading strategy. See VALIDATION.md for why.
"""

from .config import DEFAULT_MARKET, MARKETS, Market
from .data import MarketDataUnavailable
from .service import (
    BandEvidence,
    MarketTemperature,
    compute_market_temperature,
    deployment_schedule,
)

__all__ = [
    "MARKETS",
    "DEFAULT_MARKET",
    "Market",
    "MarketDataUnavailable",
    "MarketTemperature",
    "BandEvidence",
    "compute_market_temperature",
    "deployment_schedule",
]
