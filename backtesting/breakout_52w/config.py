"""Configuration for the 52-week-high breakout backtest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
DATA_CACHE_DIR = HERE / "data_cache"
RESULTS_DIR = HERE / "results"


@dataclass
class BreakoutConfig:
    starting_capital: float = 500_000.0
    goal_return_pct: float = 20.0
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    warmup_days: int = 500

    universe_index: str = "nifty500"
    universe_file: Optional[Path] = None
    benchmark: str = "^NSEI"

    breakout_lookback: int = 252
    min_volume_ratio: float = 2.0
    volume_average_days: int = 20
    liquidity_average_days: int = 50
    min_average_volume: float = 500_000.0
    min_turnover_cr: float = 5.0
    min_breakout_pct: float = 0.5
    relative_strength_days: int = 63
    min_relative_strength_3m_pct: float = 15.0
    sma50_slope_days: int = 20
    min_sma50_slope_pct: float = 2.0
    max_extension_atr: float = 1.0
    min_price: float = 20.0

    risk_per_trade_pct: float = 1.0
    max_open_risk_pct: float = 5.0
    max_positions: int = 12
    max_position_pct: float = 15.0
    max_positions_per_sector: int = 3
    enable_sector_cap: bool = True
    enable_correlation_cap: bool = True
    max_correlation: float = 0.85
    correlation_lookback: int = 63
    stop_method: str = "atr"
    atr_stop_mult: float = 1.5
    technical_stop_buffer_atr: float = 0.1
    profit_target_atr: float = 4.0

    regime_sma_fast: int = 50
    regime_sma_slow: int = 200
    regime_scaling: bool = False
    regime_use_breadth: bool = True
    enforce_earnings_blackout: bool = True
    earnings_blackout_sessions: int = 5

    trail_method: str = "chandelier"
    trail_activation_atr: float = 2.0
    chandelier_atr_mult: float = 4.0
    enable_partial_profit: bool = True
    partial_profit_atr: float = 3.5
    partial_profit_fraction: float = 0.20
    false_breakout_closes: int = 2
    time_exit_sessions: int = 10
    time_exit_progress_pct: float = 5.0

    commission_pct: float = 0.05
    use_realistic_costs: bool = True
    brokerage_pct: float = 0.0
    stt_pct: float = 0.1
    exchange_txn_pct: float = 0.00297
    sebi_pct: float = 0.0001
    gst_pct: float = 18.0
    stamp_duty_pct: float = 0.015
    slippage_bps: float = 5.0
    adv_participation_pct: float = 5.0
    use_cache: bool = True

    def __post_init__(self) -> None:
        if self.stop_method not in {"atr", "breakout_candle", "wider"}:
            raise ValueError("stop_method must be atr, breakout_candle, or wider")
        if self.trail_method not in {"chandelier", "sma20"}:
            raise ValueError("trail_method must be chandelier or sma20")
        if self.profit_target_atr <= 0:
            raise ValueError("profit_target_atr must be positive")
        if not 0.0 < self.partial_profit_fraction < 1.0:
            raise ValueError("partial_profit_fraction must be between 0 and 1")
        if self.relative_strength_days <= 0:
            raise ValueError("relative_strength_days must be positive")
        if self.sma50_slope_days <= 0:
            raise ValueError("sma50_slope_days must be positive")
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")

    def goal_capital(self) -> float:
        return self.starting_capital * (1 + self.goal_return_pct / 100.0)

    def build_cost_model(self):
        """Return a realistic Indian delivery CostModel, or None for the flat model."""
        if not self.use_realistic_costs:
            return None
        from backtesting.swing_trading.portfolio import CostModel

        return CostModel(
            brokerage_pct=self.brokerage_pct,
            stt_pct=self.stt_pct,
            exchange_txn_pct=self.exchange_txn_pct,
            sebi_pct=self.sebi_pct,
            gst_pct=self.gst_pct,
            stamp_duty_pct=self.stamp_duty_pct,
            slippage_bps=self.slippage_bps,
        )
