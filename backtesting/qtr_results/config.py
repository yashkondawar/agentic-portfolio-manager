"""
config.py
=========

Central configuration for the **quarterly-results** backtest. Mirrors the live
strategy's tunables (``qtr_results.config``: selection thresholds, target band,
trailing-stop ratio, holding window) so the backtest reasons within the SAME
playbook the live strategy follows, and adds the capital/goal/window/universe
knobs a portfolio simulation needs (same shape as the swing-trading backtest).

All values are overridable from the CLI (see ``run_backtest.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

# Reuse the live strategy defaults so the backtest starts from identical numbers.
from qtr_results import config as live_config

HERE = Path(__file__).resolve().parent
PRICE_CACHE_DIR = HERE / "data_cache"
FUND_CACHE_DIR = HERE / "fundamentals_cache"
RESULTS_DIR = HERE / "results"


@dataclass
class BacktestConfig:
    # ── Capital / goal ────────────────────────────────────────────────────────
    starting_capital: float = 500_000.0       # ₹5,00,000 to start (all cash)
    goal_return_pct: float = 20.0             # +20% goal → ₹6,00,000

    # ── Backtest window ───────────────────────────────────────────────────────
    # Defaults: trailing ~1 year ending "today". Resolved in run_backtest if None.
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # Extra price history downloaded BEFORE start_date so nothing cold-starts.
    warmup_days: int = 60                      # calendar days of price warmup

    # ── Universe (companies whose result declarations we replay) ──────────────
    universe_index: str = "nifty200"           # nifty50/100/200/500/midcap150...
    universe_file: Optional[Path] = None       # optional custom symbol file
    benchmark: str = "^NSEI"                   # Nifty 50 (defines the calendar)

    # ── Result-event discovery / timing ───────────────────────────────────────
    # Indian companies file Q results anywhere between ~15 and ~45 days after
    # quarter-end (large caps file first, mid/small caps later). Rather than
    # collapse this month-long distribution onto a single day (which produces a
    # correlated basket-buy every quarter), we assign each symbol a deterministic
    # lag drawn from ``[reporting_lag_min, reporting_lag_max]`` and use that as
    # its assumed filing date. The entry is then priced at the first trading
    # session's OPEN on/after that date, so every pick uses the historical price
    # at that point in time — never today's.
    reporting_lag_min: int = 15
    reporting_lag_max: int = 45
    # When True, replace the estimated (quarter_end + lag) declaration date with
    # the REAL announcement date from NSE wherever it is available (per-quarter,
    # per-symbol), falling back to the estimate only for gaps. See
    # ``data.ResultsCalendarStore`` / ``scraper.nse_events.historical_result_dates``.
    use_real_decl_dates: bool = True
    # When True, only trade events that have a REAL NSE declaration date (drops
    # the estimated-lag fallbacks). Gives a clean high-integrity regime — used to
    # study/tune filters on the window where timing is exact (currently 2024).
    real_dates_only: bool = False

    # ── B10: pre-declaration "anticipation" mode ─────────────────────────────
    # Indian equities frequently drift up BEFORE a good result (informed flow /
    # leaks). This mode enters a position ``anticipation_lead_days`` trading
    # sessions BEFORE the (real) declaration date when the stock is showing a
    # pre-result run-up (relative strength vs the benchmark over
    # ``anticipation_rs_lookback`` sessions ≥ ``anticipation_min_rs``). On the
    # declaration day the result is graded: a STRONG result rides on (target +
    # trailing stop), a WEAK result is dumped at the next open to dodge the
    # post-result reversal. Requires real declaration dates (needs the exact day).
    anticipation_mode: bool = False
    anticipation_lead_days: int = 10
    anticipation_rs_lookback: int = 20
    # 0.12 = require a +12% pre-declaration run-up vs the benchmark. A neighbourhood
    # sweep on the 2024 real-dated window shows a robust positive plateau across
    # 0.11–0.14 (PF 1.3–1.9); below ~0.10 and above ~0.15 the edge collapses (too
    # loose = noise, too tight = too few names). Best used WITH the regime throttle
    # + debt gate, which together turned that window from -6.6% into +14%.
    anticipation_min_rs: float = 0.12
    max_new_per_day: int = 5                    # cap simultaneous fresh buys/day

    # ── Selection thresholds (mirror qtr_results.config) ──────────────────────
    min_yoy_profit_growth: float = live_config.MIN_YOY_PROFIT_GROWTH   # 20%
    min_qoq_profit_growth: float = live_config.MIN_QOQ_PROFIT_GROWTH   # 5%
    min_yoy_eps_growth: float = live_config.MIN_YOY_EPS_GROWTH         # 15%

    # ── Target band + trailing stop + holding window ─────────────────────────
    # Targets mirror the live playbook (10-20% PE-rerating band). The holding
    # window and trailing-stop mechanics are the backtest's own — see below.
    target_min_pct: float = live_config.TARGET_MIN_PCT                 # 10%
    target_max_pct: float = live_config.TARGET_MAX_PCT                 # 20%

    # "Ride-the-wave" exit: when True the fixed PE-rerating profit target is
    # DISABLED and a position is only closed by the ATR trailing stop or the
    # time-stop. This lets a genuine earnings-momentum winner run the full swing
    # (e.g. a +50% PEAD move) instead of being clipped at +20% — at the cost of
    # giving back the last ATR-band of every runner. Pair with a wider
    # ``max_holding_days`` so the time-stop doesn't cut the drift short.
    #
    # DEFAULT True: on the Nifty-500 union / 2023-2026 study the fixed +20% cap
    # was almost never the binding exit (only 11 of 70 winners ever exceeded it)
    # and clipped the few real runners, so ride-the-wave dominated the capped
    # variant on every axis (hedged Sharpe 0.42 → higher, avg win +20%).
    disable_profit_target: bool = True

    # Holding window: post-earnings-announcement drift (PEAD) in Indian equities
    # is strongest over 30-90 days after declaration, not 15-21 (Sehgal & Bijoy
    # 2015; NSE working papers). The live 21-day time-stop kills winners well
    # before their fundamental thesis can play out, so the backtest extends it.
    # The wide ATR trail (below) needs room to ride, so 90 not 60.
    max_holding_days: int = 90

    # ── Trailing stop (ATR-based, DECOUPLED from target) ─────────────────────
    # The original stop was ``target_pct/2`` which gave tight 5-10% stops on
    # positions targeting a 20% move — asymmetric noise-out risk, and penalised
    # the highest-conviction picks with the tightest stops (bigger target ⇒
    # bigger stop = the opposite of what you want). Instead we use an ATR-based
    # stop measured in each stock's own volatility units, computed point-in-time
    # from the OHLCV history BEFORE the entry day.
    atr_period: int = 14                       # ATR lookback in sessions
    # Stop distance = atr_stop_multiplier x ATR. A multiplier sweep (2.5/3/3.5/4/
    # 5/6) on the Nifty-500 / 2023-2026 study showed 2.5 was far too tight for
    # volatile mid/small-caps (4-5%/day ATR ⇒ a ~10% trail that whipsaws winners
    # out on the FIRST normal pullback). Widening to 6x was the most REGIME-STABLE
    # setting in a split-half test (H1 17.6% / H2 18.6% CAGR — the only value that
    # repeated across both halves; 3.5/4x were front-loaded to the 2023-24 bull).
    # Trade-off: a 6x trail ≈ ~27% giveback from the peak and a ~70-day hold, so it
    # is a position-trade horizon and is UNTESTED against a sustained bear — pair
    # with ``regime_filter`` for the downside tail the wide stop cannot handle.
    atr_stop_multiplier: float = 6.0           # stop distance = 6 x ATR
    # Safety fallbacks in case ATR can't be computed (insufficient history).
    fallback_stop_pct: float = 8.0             # default 8% stop distance

    # ── PE-percentile guard (B3) ──────────────────────────────────────────────
    # A "strong result" screen selects into "peak earnings suspicion" territory
    # — companies posting +20% YoY profit growth are often already re-rated, and
    # their PE multiple compresses when the market suspects a cyclical top. To
    # avoid buying at the top of a name's own PE distribution, we look at where
    # the pre-result trailing PE sits within the last ``pe_history_years`` of
    # its daily PE distribution. If the PE percentile is above
    # ``pe_pct_cap_threshold`` (i.e. already stretched), we halve the target
    # into the low end of the band.
    pe_history_years: int = 3
    pe_pct_cap_threshold: float = 80.0         # percentile threshold (0-100)
    pe_pct_target_cap: float = 10.0            # target if PE is already stretched

    # ── Entry confirmation (B4) ───────────────────────────────────────────────
    # Signal-day (declaration day) confirmation filters — remove trades where
    # the market itself is rejecting the fundamental beat or the stock is in a
    # broader downtrend.
    #
    # ``require_signal_day_green`` (close > open on the signal day) is a
    # tight day-trader check that also filters mildly-red digestion days after
    # a gap-up (very common in Indian mid/small caps that saw the news pre-open).
    # Empirically it removes too many PEAD winners, so it's OFF by default.
    # The broader uptrend filter (close > SMA20 AND SMA20 slope >= 0) is a much
    # cleaner "not broken" check and IS on by default — it strips the pathological
    # "great result inside a downtrend" trades that repeatedly stopped out.
    require_signal_day_green: bool = False     # tight intraday check (OFF)
    require_uptrend: bool = True               # broader trend check (ON)
    trend_ma_period: int = 20                  # SMA period for the trend filter

    # ── Sector concentration cap (B5) ────────────────────────────────────────
    # Cap the % of equity that can be deployed into a single yfinance sector at
    # any one time. Prevents same-day 5-of-5 baskets from being one theme.
    max_sector_pct: float = 30.0

    # ── Static-tier fallback targets (B6) ────────────────────────────────────
    # Live static tiers assign the FULL 20% target to any strong result whose
    # PE/EPS is unavailable (banks, PSUs, holding cos). Without a valuation
    # anchor that's over-ambitious — halve the targets for the fallback path.
    # Format: [(strength_threshold, target_pct), ...] sorted high → low.
    static_target_tiers: tuple = ((75.0, 10.0), (55.0, 8.0), (0.0, 5.0))

    # ── Liquidity filter (B7) ─────────────────────────────────────────────────
    # Skip names whose median 20-day rupee turnover is below this floor. Small
    # nominal notionals here (₹5cr) still protect against micro-cap slippage /
    # index-membership survivors that are effectively illiquid.
    min_liquidity_median_20d: float = 5_00_00_000.0  # ₹5 crore

    # ── Balance-sheet quality filter (B8) ─────────────────────────────────────
    # The v3 backtest's losing trades cluster in HIGHLY-LEVERED companies: a
    # "strong result" in a debt-heavy business whipsaws out of the ATR trailing
    # stop far more often than the same beat in a clean-balance-sheet compounder
    # (winners' median debt/equity was ~0.04 vs ~0.25 for losers). We gate on
    # point-in-time debt/equity (Borrowings ÷ (Equity Capital + Reserves) from the
    # latest annual balance sheet on/before the declared quarter) and, optionally,
    # a minimum ROCE. Banks/NBFCs are exempt from the debt gate (leverage is
    # inherent to their model); a missing value never rejects (data-gap safe).
    #   ``None`` = filter disabled.
    max_debt_to_equity: Optional[float] = 0.05   # near-debt-free names only (B8)
    min_roce: Optional[float] = None             # e.g. 15 (%) quality floor
    apply_quality_to_financials: bool = False    # exempt banks/NBFCs from debt gate

    # ── Market-regime throttle (B9) ───────────────────────────────────────────
    # The stock-selection filters (B1-B8) fix pick QUALITY but not portfolio
    # DRAWDOWN: earnings-momentum longs take correlated hits in a broad market
    # correction (the Nifty-500/3yr test drew down ~19% around the 2025 sell-off
    # regardless of the debt filter). This gate stops OPENING new positions while
    # the benchmark (Nifty) is below its ``regime_ma_period``-day SMA — i.e. it
    # only deploys fresh risk in an up-market. Existing positions keep running
    # their own stops/targets. Point-in-time (uses benchmark prices <= signal day).
    regime_filter: bool = False                  # opt-in; validated before default
    regime_ma_period: int = 100                  # benchmark SMA period (sessions)
    regime_require_slope: bool = False           # also require non-declining SMA

    # ── Earnings-SURPRISE signal (SUE) — ideal-state redesign ────────────────
    # The legacy gate is ABSOLUTE growth (yoy_profit >= 20%), which is the wrong
    # economic object: +20% YoY when the market expected +40% is a negative
    # surprise and the stock falls. PEAD is driven by the surprise vs EXPECTATION.
    # When enabled, we compute Standardized Unexpected Earnings (Foster-Olsen-
    # Shevlin) from the company's own EPS history — no consensus vendor needed —
    # and surface it on the event log; under `cross_sectional` it becomes the
    # primary ranking signal. Off by default so the legacy path is unchanged.
    use_sue: bool = False
    sue_window: int = 8                          # trailing quarters for SUE drift/vol
    reaction_lookback: int = 1                   # sessions for the declaration reaction

    # ── Cross-sectional construction (top-quantile) ──────────────────────────
    # The legacy engine buys EVERY name clearing fixed thresholds (basket size
    # drifts with the tape). When enabled, the day's candidates are ranked against
    # each other by a composite z-score (SUE + declaration reaction + a graded
    # leverage tilt) and only the top slice is bought — self-normalizing to how
    # strong the season is. Off by default (opt-in).
    cross_sectional: bool = False
    top_quantile: Optional[float] = 0.20         # keep the top fraction of the field
    min_composite_score: Optional[float] = None  # optional absolute floor on the z-score
    w_sue: float = 0.5                           # composite weight — surprise leads
    w_reaction: float = 0.3                      # composite weight — price confirmation
    w_quality: float = 0.2                       # composite weight — leverage tilt (soft)

    # ── Beta-hedge overlay (isolate the alpha) ───────────────────────────────
    # A long-only earnings book is dominated by market direction; hedging its net
    # beta with a short index overlay isolates the PEAD alpha — and is the honest
    # out-of-sample test (if the hedged alpha isn't positive, there is no edge).
    # Applied as a post-hoc overlay on the equity curve, so the long-only path is
    # byte-for-byte unchanged. Off by default.
    hedge_enabled: bool = False
    hedge_ratio: float = 1.0                     # fraction of beta to short (1 = neutral)
    hedge_book_beta: float = 1.0                 # assumed beta (replaced by measured one)
    hedge_use_measured_beta: bool = True         # estimate book beta via OLS when possible
    hedge_annual_carry_pct: float = 1.0          # roll/borrow carry on the short (%/yr)
    hedge_commission_pct: float = 0.02           # per-side cost on hedge rebalancing (%)

    # ── Validation / honesty ─────────────────────────────────────────────────
    # Number of configurations explored to arrive at this run. Feeds the DEFLATED
    # Sharpe so a curve-fit result can't masquerade as an edge. Set it honestly.
    num_trials: int = 1

    # ── Portfolio sizing (the capital overlay the live signal-tracker lacks) ──
    # The live strategy is a signal/ledger tracker with no position sizing; a
    # backtest needs one. We reuse the swing setup's risk model: risk a fixed %
    # of equity per trade, where the per-share risk is the initial trailing-stop
    # distance (entry * trailing_stop_pct/100). Capped by a per-name concentration
    # limit and available cash.
    risk_per_trade_pct: float = 2.0
    max_positions: int = 10                    # max concurrent open positions
    max_position_pct: float = 20.0             # per-name concentration cap (%)

    # ── Costs ─────────────────────────────────────────────────────────────────
    # Realistic Indian retail all-in cost per side: STT (0.1% on delivery sells),
    # exchange charges, GST, SEBI/stamp, brokerage, plus a slippage proxy for the
    # next-day-open fill. ~20 bps per side ⇒ ~40 bps round-trip.
    commission_pct: float = 0.20               # per-side cost proxy (%)

    # ── Misc ──────────────────────────────────────────────────────────────────
    use_cache: bool = True                     # reuse downloaded price/fundamentals
    max_symbols: Optional[int] = None          # cap universe size (for quick runs)

    def goal_capital(self) -> float:
        return self.starting_capital * (1 + self.goal_return_pct / 100.0)
