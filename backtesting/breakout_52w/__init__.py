"""Deterministic 52-week-high breakout backtest."""

from .config import BreakoutConfig
from .service import run_backtest

__all__ = ["BreakoutConfig", "run_backtest"]
