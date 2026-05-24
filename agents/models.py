"""
Structured signal models for the parallel multi-analyst system.
Every analyst agent outputs signals in this standardized format.
"""

from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel, Field


class AnalystSignal(BaseModel):
    """Standard output from any analyst agent for a single ticker."""

    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0, le=100, description="Confidence 0-100")
    reasoning: str = Field(description="Concise reasoning for the signal")


class TechnicalMetrics(BaseModel):
    """Detailed technical analysis metrics."""

    rsi: Optional[float] = None
    macd_trend: Optional[str] = None
    adx: Optional[float] = None
    trend_score: Optional[float] = None
    mean_reversion_score: Optional[float] = None
    momentum_score: Optional[float] = None
    volatility_score: Optional[float] = None
    stat_arb_score: Optional[float] = None
    overall_score: Optional[float] = None


class FundamentalMetrics(BaseModel):
    """Fundamental analysis scoring breakdown."""

    profitability_score: int = Field(ge=0, le=3)
    growth_score: int = Field(ge=0, le=3)
    health_score: int = Field(ge=0, le=3)
    valuation_score: int = Field(ge=0, le=3)
    total_score: int = Field(ge=0, le=12)


class ValuationResult(BaseModel):
    """Valuation analysis output."""

    intrinsic_value: Optional[float] = None
    market_cap: Optional[float] = None
    margin_of_safety_pct: Optional[float] = None
    dcf_value: Optional[float] = None
    ev_ebitda_value: Optional[float] = None
    method_used: str = ""


class RiskMetrics(BaseModel):
    """Risk manager output per ticker."""

    daily_volatility: float
    annualized_volatility: float
    volatility_percentile: float
    max_position_pct: float = Field(description="Max % of portfolio for this ticker")
    max_position_value: float = Field(description="Max ₹ exposure for this ticker")
    reasoning: str


class PortfolioDecision(BaseModel):
    """Final portfolio manager decision per ticker."""

    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(ge=0, le=100)
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    position_size_pct: Optional[float] = Field(
        None, description="% of portfolio to allocate"
    )
    reasoning: str
    time_horizon: str = "1-7 days"


class StockAnalysis(BaseModel):
    """Complete analysis for a single stock — all agent signals combined."""

    symbol: str
    company_name: str = ""
    current_price: Optional[float] = None
    analyst_signals: Dict[str, AnalystSignal] = Field(default_factory=dict)
    risk_metrics: Optional[RiskMetrics] = None
    final_decision: Optional[PortfolioDecision] = None
