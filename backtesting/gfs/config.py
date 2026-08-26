"""
config.py
=========

Every knob of the GFS backtest in one dataclass, so a run is fully described by a
single serializable object (which is written next to the results, making any run
reproducible).

The defaults encode the strategy *as stated*: monthly RSI > 60, weekly RSI > 60,
buy when daily RSI dips below 40, exit when daily RSI recovers to 65. Almost
every default is deliberately a *hypothesis to be tested*, not a belief - the
sweep and ablation tooling exists precisely to find out which of them carry
weight.

Two knobs deserve special attention because they are where most public
"multi-timeframe" backtests quietly cheat:

``htf_mode``
    How the weekly/monthly RSI is observed on a given day.

    * ``"closed"`` - only fully completed higher-timeframe candles are used. On
      2024-03-06 the monthly RSI is February's final value.
    * ``"live"``   - the in-progress candle is included, built from daily data up
      to *and including* today. This is what a trader actually sees on a chart.

    **Both are leak-free** - the partial bar never contains a future session.
    They differ in responsiveness, not in honesty. The genuinely dishonest third
    option (resampling the whole history and reading the last monthly bar, which
    contains the rest of the month) is structurally impossible here; see
    ``indicators.htf_rsi_daily``.

``indicator_exit_delay``
    An RSI-based exit is only *knowable* at the close that produced it, so it is
    filled at the next session's open. Price-level exits (stop, target,
    resistance) are known in advance and so may fill intrabar. Turning this off
    lets an exit fill at the very close that generated it, which flatters
    results; it exists only so the cost of the assumption can be measured.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional

from .taxes import TaxConfig

HERE = Path(__file__).resolve().parent
DATA_CACHE_DIR = HERE / "data_cache"
RESULTS_DIR = HERE / "results"

# Higher-timeframe observation modes.
HTF_CLOSED = "closed"
HTF_LIVE = "live"

# Entry triggers on the "Son" (daily) timeframe.
TRIGGER_DIP = "dip"  # daily RSI is at/below the entry threshold
TRIGGER_RECROSS = "recross"  # daily RSI crosses back UP through the threshold

# Position sizing modes.
SIZING_RISK = "risk"  # shares = (equity * risk%) / stop distance
SIZING_EQUAL = "equal"  # equal rupee allocation per open slot

# Stop-placement modes.
STOP_ATR = "atr"
STOP_PCT = "pct"
STOP_SWING = "swing"

# Market-regime gate modes - the "is the market bullish?" step of the funnel.
#
# `breadth` asks only how much of the universe is in its own uptrend.
# `breadth+sma` additionally demands the benchmark close above its own SMA(n).
#
# The AND was the original design and reads like the safer of the two. It is
# not: it is the only regime setting in the study that loses to the benchmark in
# a sub-period (2013-2017), because the 200-DMA is a lagging line that keeps the
# book shut long after participation has recovered. See EXPLORATIONS.md.
REGIME_BREADTH = "breadth"
REGIME_BREADTH_SMA = "breadth+sma"

# Exit management modes.
EXIT_RSI = "rsi"  # pure GFS: leave when daily RSI reaches exit_rsi
EXIT_SCALE_OUT = "scale_out"  # book part at exit_rsi, trail the rest
EXIT_TRAIL = "trail"  # ignore RSI, ride an ATR trailing stop
EXIT_RESISTANCE = "resistance"  # leave at the prior swing high

# Candidate ranking modes ("random" is the null hypothesis for ranking).
RANK_COMPOSITE = "composite"
RANK_SECTOR_RS = "sector_rs"
RANK_DIP_DEPTH = "dip_depth"
RANK_HTF_STRENGTH = "htf_strength"
RANK_HEADROOM = "headroom"  # distance to the resistance the exit targets
RANK_REWARD_RISK = "reward_risk"  # that distance measured in units of stop
RANK_RANDOM = "random"

# The label used when a stock's industry is not known. It is deliberately *not*
# treated as a sector by the concentration cap - see `strategy.can_open_sector`.
UNKNOWN_SECTOR = "Unknown"


@dataclass
class GFSConfig:
    # ── Backtest window ──────────────────────────────────────────────────────
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # Extra history pulled BEFORE start_date. Monthly RSI(14) with Wilder
    # smoothing is only meaningful after a few dozen monthly candles, so this
    # has to be measured in years, not the ~1 year a daily-only system needs.
    warmup_days: int = 2600  # ~7 calendar years

    # ── Universe ─────────────────────────────────────────────────────────────
    # Comma-separated NSE index keys are merged (first occurrence wins), e.g.
    # "nifty500,niftysmallcap250".
    universe_index: str = "nifty500"
    universe_file: Optional[Path] = None
    benchmark: str = "^NSEI"
    use_cache: bool = True

    # ── The GFS core: Grandfather (monthly) / Father (weekly) / Son (daily) ──
    htf_mode: str = HTF_CLOSED
    rsi_period_monthly: int = 14
    rsi_period_weekly: int = 14
    rsi_period_daily: int = 14
    g_rsi_min: float = 60.0  # Grandfather: monthly RSI above this
    f_rsi_min: float = 60.0  # Father: weekly RSI above this
    s_rsi_entry: float = 40.0  # Son: daily RSI dips to/below this
    entry_trigger: str = TRIGGER_DIP

    # Warmup guards - a name is simply not evaluated until each timeframe has
    # enough closed candles for its RSI to mean anything.
    min_daily_bars: int = 250
    min_weekly_bars: int = 52
    min_monthly_bars: int = 30

    # ── Tradability filters ──────────────────────────────────────────────────
    min_price: float = 50.0
    min_turnover_cr: float = 5.0  # 20d median traded value, Rs crore
    max_atr_pct: float = 9.0  # skip names too volatile to stop sensibly

    # ── Helicopter view: market regime gate ──────────────────────────────────
    use_regime_filter: bool = True
    # Breadth alone is the default. Adding the benchmark's own 200-DMA on top
    # costs nothing in drawdown but is the difference between a strategy that is
    # positive in every sub-period and one that is not - see EXPLORATIONS.md,
    # "Decomposing the regime gate".
    regime_mode: str = REGIME_BREADTH
    regime_sma: int = 200  # benchmark SMA(n); only read in `breadth+sma` mode
    min_breadth_pct: float = 40.0  # % of universe above SMA(200); 0 disables

    # ── Aerial view: sector gate ─────────────────────────────────────────────
    use_sector_filter: bool = True
    sector_rs_lookback: int = 63  # ~3 months of sessions
    sector_top_n: int = 5  # only trade the N strongest sectors
    min_sector_members: int = 3  # ignore sectors too small to average

    # ── Microscopic view: candidate ranking ──────────────────────────────────
    rank_by: str = RANK_COMPOSITE
    max_per_sector: int = 2  # concentration cap among open positions

    # Minimum distance to resistance, in percent, for a dip to be tradable.
    # 0 disables the filter. This is the only entry filter the conviction study
    # found that survived an out-of-sample test, and it is mechanical rather
    # than statistical: the exit is defined at resistance, so a signal with no
    # headroom has no room to pay for its own stop.
    min_headroom_pct: float = 0.0

    # ── Capital, sizing and risk ─────────────────────────────────────────────
    starting_capital: float = 500_000.0
    sizing_mode: str = SIZING_EQUAL
    risk_per_trade_pct: float = 2.0  # used when sizing_mode == "risk"
    max_positions: int = 8
    max_position_pct: float = 15.0  # per-name ceiling as % of equity

    stop_mode: str = STOP_ATR
    atr_period: int = 14
    atr_stop_mult: float = 2.0
    fixed_stop_pct: float = 4.0  # used when stop_mode == "pct"
    swing_low_lookback: int = 20  # used when stop_mode == "swing"
    swing_low_buffer_pct: float = 0.5

    # ── Exits ────────────────────────────────────────────────────────────────
    exit_mode: str = EXIT_RSI
    exit_rsi: float = 65.0
    scale_out_frac: float = 0.5  # fraction booked at exit_rsi in scale_out mode
    trail_atr_mult: float = 3.0
    resistance_lookback: int = 63  # prior swing high used as a price target
    max_holding_days: int = 60  # calendar-day time stop
    move_stop_to_breakeven_at_r: float = 0.0  # 0 disables
    indicator_exit_delay: bool = True
    # Thesis-invalidation exit: leave when the "Father" that justified the trade
    # breaks down mid-trade, regardless of P&L. 0 disables. This is not a stop
    # and not a target - it is the entry condition ceasing to be true.
    exit_f_rsi: float = 0.0

    # ── Costs ────────────────────────────────────────────────────────────────
    commission_pct: float = 0.05  # per side, %
    slippage_bps: float = 15.0  # per side, basis points

    # Idle cash is not dead money in practice: a portfolio this lightly deployed
    # would hold the balance in a liquid fund. Defaulted to 0 so existing
    # results stay comparable; set it explicitly to model the realistic case.
    cash_yield_pct: float = 0.0

    # Statutory charges and capital gains are modelled separately from
    # execution costs above: STT and stamp duty do not shrink because you traded
    # well, and capital gains tax is levied annually on realised profit rather
    # than per fill. See taxes.py.
    tax: TaxConfig = field(default_factory=TaxConfig)

    # ── Reproducibility ──────────────────────────────────────────────────────
    seed: int = 7
    label: str = "gfs"

    def resolved_universe_keys(self) -> List[str]:
        return [k.strip() for k in str(self.universe_index).split(",") if k.strip()]

    def validate(self) -> None:
        if self.start_date is None or self.end_date is None:
            raise ValueError("start_date and end_date are required")
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        if self.htf_mode not in (HTF_CLOSED, HTF_LIVE):
            raise ValueError(f"htf_mode must be {HTF_CLOSED!r} or {HTF_LIVE!r}")
        if self.entry_trigger not in (TRIGGER_DIP, TRIGGER_RECROSS):
            raise ValueError(f"entry_trigger must be {TRIGGER_DIP!r} or {TRIGGER_RECROSS!r}")
        if self.sizing_mode not in (SIZING_RISK, SIZING_EQUAL):
            raise ValueError(f"sizing_mode must be {SIZING_RISK!r} or {SIZING_EQUAL!r}")
        if self.stop_mode not in (STOP_ATR, STOP_PCT, STOP_SWING):
            raise ValueError("stop_mode must be one of atr/pct/swing")
        if self.exit_mode not in (EXIT_RSI, EXIT_SCALE_OUT, EXIT_TRAIL, EXIT_RESISTANCE):
            raise ValueError("exit_mode must be one of rsi/scale_out/trail/resistance")
        if self.rank_by not in (
            RANK_COMPOSITE,
            RANK_SECTOR_RS,
            RANK_DIP_DEPTH,
            RANK_HTF_STRENGTH,
            RANK_HEADROOM,
            RANK_REWARD_RISK,
            RANK_RANDOM,
        ):
            raise ValueError("rank_by is not a known ranking mode")
        if self.max_positions < 1:
            raise ValueError("max_positions must be >= 1")
        if not 0 < self.scale_out_frac < 1:
            raise ValueError("scale_out_frac must be strictly between 0 and 1")
        if not 0 <= self.exit_f_rsi <= 100:
            raise ValueError("exit_f_rsi must be between 0 and 100")
        if self.exit_f_rsi > 0 and self.exit_f_rsi >= self.f_rsi_min:
            raise ValueError(
                "exit_f_rsi must be below f_rsi_min, otherwise every position "
                "exits on the bar it opens"
            )
        if self.regime_mode not in (REGIME_BREADTH, REGIME_BREADTH_SMA):
            raise ValueError(
                f"regime_mode must be {REGIME_BREADTH!r} or {REGIME_BREADTH_SMA!r}"
            )
        if self.use_regime_filter and self.regime_mode == REGIME_BREADTH_SMA:
            if self.regime_sma < 2:
                raise ValueError("regime_sma must be >= 2 when the trend leg is on")


@dataclass
class AblationVariant:
    """A named config override used to isolate one leg of the strategy."""

    name: str
    question: str  # what this variant is meant to answer
    overrides: dict = field(default_factory=dict)
