"""Configuration for the all-time-high breakout sleeve."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_CACHE_DIR = PACKAGE_DIR / "data_cache"
RESULTS_DIR = PACKAGE_DIR / "results"
STATE_PATH = DATA_CACHE_DIR / "daily_portfolio.json"


@dataclass
class AthBreakoutConfig:
    """Every knob the sleeve exposes.

    The first block is the strategy proper and is reported verbatim in the
    dossier's Configuration section; the trailing block is plumbing (which
    index to scan, which window to run, which benchmark to compare against).
    """

    # ── Strategy ─────────────────────────────────────────────────────────────
    max_positions: int = 28
    sl_pct: float = 0.16
    ath_band: float = 0.15
    selection_rule: str = "mom_3m"
    lookback: int = 252
    slot_reset_freq: str = "Q"
    cost_bps: float = 25.0
    stcg_rate: float = 0.20
    ltcg_rate: float = 0.125
    start_capital: float = 10_000_000.0
    signal_price: str = "adjusted"

    # ── Plumbing ─────────────────────────────────────────────────────────────
    momentum_lookback: int = 63
    stale_exit_sessions: int = 21
    universe_index: str = "niftytotalmarket"
    benchmark: str = "^NSEI"
    broad_index: str = "^CRSLDX"
    start_date: Optional[date] = field(default=date(2012, 10, 19))
    end_date: Optional[date] = field(default=date(2026, 8, 24))

    # ── Derived ──────────────────────────────────────────────────────────────
    @property
    def starting_capital(self) -> float:
        """Alias used by the shared dossier helpers."""
        return self.start_capital

    @property
    def cost_rate(self) -> float:
        """Brokerage plus impact as a fraction of notional."""
        return self.cost_bps / 10_000.0

    @property
    def stop_multiple(self) -> float:
        """Fraction of the anchor the trailing stop sits at."""
        return 1.0 - self.sl_pct

    @property
    def ath_floor(self) -> float:
        """Minimum close / lifetime-high ratio an entry must clear."""
        return 1.0 - self.ath_band

    def validate(self) -> None:
        if self.max_positions < 1:
            raise ValueError("max_positions must be at least 1")
        if not 0.0 < self.sl_pct < 1.0:
            raise ValueError("sl_pct must be a fraction strictly between 0 and 1")
        if not 0.0 <= self.ath_band < 1.0:
            raise ValueError("ath_band must be a fraction in [0, 1)")
        if self.lookback < 2:
            raise ValueError("lookback must be at least 2 sessions")
        if self.momentum_lookback < 1:
            raise ValueError("momentum_lookback must be at least 1 session")
        if self.cost_bps < 0.0:
            raise ValueError("cost_bps cannot be negative")
        if self.start_capital <= 0.0:
            raise ValueError("start_capital must be positive")
        if self.slot_reset_freq not in {"Q", "M", "A", "Y", "N"}:
            raise ValueError("slot_reset_freq must be one of Q, M, A, Y, N")
        if self.selection_rule not in {"mom_3m", "mom_6m", "mom_12m", "proximity"}:
            raise ValueError(f"unknown selection_rule {self.selection_rule!r}")
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValueError("start_date must fall before end_date")
