"""Central configuration and shared defaults.

Thin, dependency-free wrappers around environment variables plus the
default values used across strategies. Keeping them here avoids sprinkling
``os.getenv`` calls and magic numbers throughout the codebase.
"""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv

# Load .env once, at import time, for the whole backend.
load_dotenv()

# ── Portfolio / sizing defaults ────────────────────────────────────────────
DEFAULT_PORTFOLIO_VALUE: float = 1_000_000.0  # ₹10L

# ── Swing-trading defaults (mirrors swing_trading_copilot module) ──────────
DEFAULT_TARGET_PROFIT_PCT: float = 20.0
DEFAULT_MAX_HOLDING_DAYS: int = 30

# ── Watchlist curation defaults ────────────────────────────────────────────
DEFAULT_WATCHLIST_INDEX: str = "nifty500"
DEFAULT_WATCHLIST_FINAL_SIZE: int = 20


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


def use_free_scraper() -> bool:
    """Whether to prefer the free scraper tools over Bright Data (paid)."""
    return env_bool("USE_FREE_SCRAPER", True)


__all__ = [
    "DEFAULT_PORTFOLIO_VALUE",
    "DEFAULT_TARGET_PROFIT_PCT",
    "DEFAULT_MAX_HOLDING_DAYS",
    "DEFAULT_WATCHLIST_INDEX",
    "DEFAULT_WATCHLIST_FINAL_SIZE",
    "env",
    "env_bool",
    "use_free_scraper",
]
