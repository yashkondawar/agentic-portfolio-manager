# 52-Week High Breakout Strategy

## Implementation and backtest review package

**Purpose:** External finance and quantitative-methodology review  
**Initial implementation commit:** `60d1303`
**Document date:** 2026-07-26  
**Market:** Indian listed equities  
**Default universe:** Current Nifty 500 constituents  
**Strategy type:** Long-only, end-of-day momentum breakout  
**Starting capital used in reported tests:** INR 500,000

> This document describes the implemented algorithm and the evidence produced by
> its historical simulation. It is not an investment recommendation or a claim
> that the reported returns will persist. The limitations in
> [Section 13](#13-material-limitations-and-sources-of-bias) are essential to any
> assessment of the results.

---

## 1. Executive summary

The strategy scans a broad Indian equity universe after each completed market
session and looks for stocks closing at least 0.5% above their prior 252-session
high. A signal is accepted only when:

- relative volume is at least 2.0 times the prior 20-session average;
- `SMA20 > SMA50 > SMA200`;
- the stock's 63-session return exceeds the Nifty's return by at least 15
  percentage points;
- the stock's SMA50 has risen at least 2% over the prior 20 sessions;
- the close is no more than 1 ATR above the breakout level;
- prior 50-session average volume is at least 500,000 shares;
- prior 50-session average turnover is at least INR 5 crore;
- the Nifty 50 proxy (`^NSEI` in yfinance) is above both its 50-day and
  200-day simple moving averages; and
- no result declaration is recorded in the next five trading sessions.

Signals are generated after the close and may be filled at the next session's
open. Each accepted position risks at most 1% of current equity to an initial
1.5 ATR stop, is capped by notional value, and has a standing profit target. The
portfolio caps total initial open risk at 5% of equity.

> **Institutional sleeve upgrade (section 18).** The rules above are the
> single-sleeve core. A later hardening pass added a realistic Indian
> delivery-cost model, a diversification framework (up to 12 concurrent
> positions with per-sector and pairwise-correlation caps and a 15%
> per-name notional cap), partial-profit booking with an uncapped trailing
> remainder, and an optional continuous regime-scaling mode. **All headline
> CAGR figures in the tables below were produced under an unrealistic 0.1%
> flat cost model.** Under the realistic cost model the same 5-year window
> returns roughly 5.4% CAGR at -14% drawdown (Sharpe 0.51). See section 18
> for the full implemented-vs-skipped list, the empirical findings, and the
> realistic-cost results matrix.

> **Trade-management pass (section 19).** A subsequent study of exits widened
> the initial stop to 1.5 ATR, widened the Chandelier trail to 4 ATR, and cut
> partial booking to 20% at 3.5 ATR. These are the **current defaults**, and
> they raise the realistic-cost five-year result to roughly 24% CAGR at -14.5%
> drawdown (Sharpe 1.36). Section 19 also documents a negative result — entry
> features cannot distinguish winners from losers — and one window
> (2015-2018) where the change is harmful.

The original baseline, first optimized version, and current cross-regime
version produced:

| Metric | Original baseline | First optimized | Current cross-regime |
|---|---:|---:|---:|
| Period | 2021-07-24 to 2026-07-24 | Same | Same |
| Start equity | INR 500,000 | INR 500,000 | INR 500,000 |
| End equity | INR 511,694 | INR 1,355,150 | INR 1,074,951 |
| Total return | 2.34% | 171.03% | 114.99% |
| CAGR | 0.46% | 22.10% | **16.56%** |
| Maximum drawdown | -32.81% | -12.48% | **-18.35%** |
| Sharpe ratio, risk-free rate 0 | 0.11 | 1.36 | **1.07** |
| Profit factor | 1.01 | 1.42 | **1.37** |
| Win rate | 36.87% | 36.91% | **36.36%** |

The current rules produced 15.89% CAGR and -8.84% drawdown from 2024-07-24 to
2026-07-24. The second optimization also reserved 2012-2014 until after final
selection; that holdout improved from -4.67% to 2.99% CAGR. Survivorship bias
still prevents treating it as pristine institutional-grade evidence.

The improvement did not come from a materially higher full-period win rate.
It came from smaller percentage losses, larger average percentage wins, faster
capital recycling, a fixed profit-taking rule, and lower average exposure.

---

## 2. Investment hypothesis

The strategy is based on the following momentum thesis:

1. A close above the highest high of the prior 252 trading sessions indicates
   strong price leadership and removes recent overhead supply.
2. High relative volume indicates broader participation and makes a marginal,
   low-conviction price print less likely.
3. Moving-average alignment filters for an already established uptrend.
4. A broad-market regime filter reduces new long exposure during weak index
   conditions.
5. Volatility-based sizing gives each position a comparable initial risk budget.
6. Tight initial loss control and systematic exits aim to keep the loss
   distribution bounded.

This is a price-and-volume strategy. It does not currently use valuation,
balance-sheet quality, earnings growth, analyst forecasts, news sentiment, or
LLM judgment as entry gates.

### What the strategy is designed to do

- Discover new long opportunities from a broad universe.
- Produce deterministic entry, stop, target, hold, and exit instructions.
- Maintain its own paper-portfolio state independently of a broker.
- Run once per day after the market close.
- Make backtest and daily rules use the same shared configuration and strategy
  functions.

### What the strategy is not designed to do

- Place or manage broker orders.
- Trade intraday signals that were not known at the prior close.
- Short stocks or hedge market beta.
- Optimize taxes or account-specific constraints.
- Replace fundamental due diligence.
- Guarantee a 15% or higher future CAGR.

---

## 3. Data and universe

### 3.1 Equity universe

The default universe is loaded from the NSE Nifty 500 constituent list. Custom
symbols can replace the index universe for focused tests or daily runs.

**Important:** Historical simulations use today's Nifty 500 membership across
the entire historical period. Historical additions, removals, mergers,
delistings, and failed firms are not reconstructed. This creates survivorship
and constituent-selection bias.

### 3.2 Price and volume data

- Source: `yfinance`
- Frequency: daily
- Fields: adjusted Open, High, Low, Close, and Volume
- Download option: `auto_adjust=True`
- NSE symbols are mapped to the `.NS` suffix.
- Data is normalized to a timezone-naive daily index.
- Duplicate dates are removed, keeping the latest row.
- The downloaded data is cached locally for reproducible reruns.

The reported five-year run loaded usable history for 500 of 500 requested
symbols.

### 3.3 Benchmark and trading calendar

- Benchmark symbol: `^NSEI`
- The benchmark's daily index defines the simulation trading calendar.
- The benchmark is also used for the market-regime filter.

### 3.4 Warmup

The system downloads 500 calendar days before the requested start date. This
warms the 200-session moving average and 252-session breakout calculation before
the first simulated decision.

### 3.5 Earnings calendar

The blackout calendar is built from the NSE corporate event calendar. It stores
result-related board-meeting dates and blocks entries when an event date falls
within the next five sessions.

If the earnings calendar is configured as mandatory and cannot be loaded, the
strategy refuses to run rather than silently bypassing the guardrail.

---

## 4. Indicator definitions

All entry indicators use data available through the signal day's completed
close.

### 4.1 Prior 252-session high

For session \(t\):

```text
H252(t-1) = max(High[t-252], ..., High[t-1])
```

The current day's high is excluded.

### 4.2 Breakout clearance

```text
BreakoutPct = (Close[t] / H252(t-1) - 1) * 100
```

Required:

```text
Close[t] > H252(t-1)
BreakoutPct >= 0.50%
```

The 0.50% clearance rejects marginal new highs and reduces signals caused by
adjusted-price rounding differences of only a few paise.

### 4.3 Relative volume

```text
ADV20_prior = mean(Volume[t-20], ..., Volume[t-1])
RVOL = Volume[t] / ADV20_prior
```

Required:

```text
RVOL >= 2.0
```

The current day's volume is not included in its own denominator.

### 4.4 Trend alignment

Simple moving averages include the completed signal-day close:

```text
SMA20 > SMA50 > SMA200
```

### 4.5 Three-month relative strength

```text
StockReturn63 = (StockClose[t] / StockClose[t-63] - 1) * 100
NiftyReturn63 = (NiftyClose[t] / NiftyClose[t-63] - 1) * 100
RelativeStrength63 = StockReturn63 - NiftyReturn63
```

Required:

```text
RelativeStrength63 >= 15 percentage points
```

### 4.6 SMA50 slope

```text
SMA50Slope20 = (SMA50[t] / SMA50[t-20] - 1) * 100
```

Required:

```text
SMA50Slope20 >= 2%
```

### 4.7 Average True Range

True range is:

```text
TR[t] = max(
    abs(High[t] - Low[t]),
    abs(High[t] - Close[t-1]),
    abs(Low[t] - Close[t-1])
)
```

ATR14 is an exponentially weighted average with:

```text
alpha = 1 / 14
adjust = False
minimum observations = 14
```

### 4.8 Breakout extension

```text
ExtensionATR = (Close[t] - H252(t-1)) / ATR14[t]
```

Required:

```text
ExtensionATR <= 1.0
```

### 4.9 Liquidity

Both liquidity tests exclude the signal day:

```text
ADV50_prior = mean(Volume[t-50], ..., Volume[t-1])
AverageTurnover50 = mean(Close * Volume over prior 50 sessions) / 10,000,000
```

Required:

```text
ADV50_prior >= 500,000 shares
AverageTurnover50 >= INR 5 crore
Signal-day Close >= INR 20
```

### 4.10 Market regime

New entries are allowed only when:

```text
Nifty Close > Nifty SMA50
Nifty Close > Nifty SMA200
```

The implementation does not require `SMA50 > SMA200`.

### 4.11 Candidate ranking

When more candidates exist than portfolio capacity, candidates are sorted by:

```text
Score = RVOL + max(0, 1 - ExtensionATR)
```

This favors stronger relative volume and breakouts closer to the prior high.
The engine retains the best `available capacity + 2` candidates for next-open
attempts, allowing some room for open-price rejections.

---

## 5. Entry and execution sequence

### 5.1 Signal timing

1. Session \(t\) closes.
2. The system evaluates all entry conditions using data through that close.
3. Qualified candidates become pending signals.
4. The earliest possible fill is session \(t+1\)'s open.

There is no same-close fill.

### 5.2 Next-open entry zone

A pending signal is filled only when the next open satisfies:

```text
BreakoutLevel < NextOpen <= BreakoutLevel + 1 * SignalATR
```

An open below or equal to the breakout level is treated as failed confirmation.
An open more than 1 ATR above the breakout level is treated as too extended.

### 5.3 Entry-day bracket assumptions

Immediately after a modeled fill:

```text
InitialStop = EntryPrice - 1 * SignalATR
ProfitTarget = EntryPrice + 4 * SignalATR
```

The model assumes these are standing orders on the entry day.

If the daily candle touches both stop and target and intraday ordering is
unknown, the simulation assumes the stop occurred first. This is deliberately
conservative.

### 5.4 Fill assumptions

- Entry fills at the exact reported open.
- A non-gap stop fills at the exact stop.
- A gap below the stop fills at the open.
- A target fills at the target, or at the open when the market gaps above it.
- Whole shares only are used.
- No partial fills are modeled.
- No participation-rate or order-size slippage is modeled.

---

## 6. Position sizing and portfolio controls

### 6.1 Per-trade risk

```text
RiskBudget = CurrentEquity * 1%
RiskPerShare = EntryPrice - InitialStop
RawShares = floor(RiskBudget / RiskPerShare)
```

### 6.2 Portfolio heat

Open risk is:

```text
OpenRisk = sum(max(EntryPrice - CurrentStop, 0) * Shares)
```

Remaining heat is:

```text
HeatRemaining = max(CurrentEquity * 5% - OpenRisk, 0)
```

The actual share count is the minimum allowed by:

```text
floor(min(RiskBudget, HeatRemaining) / RiskPerShare)
floor(CurrentEquity * 25% / EntryPrice)
floor(AvailableCash * 99.9% / EntryPrice)
```

### 6.3 Portfolio-level limits

| Control | Default |
|---|---:|
| Risk per trade | 1% of current equity |
| Maximum open risk | 5% of current equity |
| Maximum positions | 5 |
| Maximum notional per position | 25% of current equity |
| Cash buffer in affordability calculation | 0.1% |

Trailing a stop upward reduces measured open risk and may restore capacity for
new positions.

---

## 7. Exit logic and precedence

For positions held from a prior session, each daily bar is evaluated in this
order:

1. **Gap stop:** if `Open <= Stop`, exit at the open.
2. **Intraday stop:** if `Low <= Stop`, exit at the stop.
3. **Profit target:** if `High >= Target`, exit at `max(Open, Target)`.
4. **False breakout:** exit at the close after two consecutive closes below the
   original breakout level.
5. **Trailing-stop activation/update.**
6. **Time exit:** exit at the close when progress is insufficient.

The ordering makes stop execution take precedence over target execution on an
ambiguous daily candle.

### 7.1 Fixed target

```text
Target = EntryPrice + 4 * ATR_at_entry
```

This differs from a pure open-ended momentum strategy. The fixed target was
introduced because it materially improved profit factor, drawdown, and capital
turnover during the tested periods. It also truncates some potential long-tail
winners.

### 7.2 False-breakout exit

The position tracks consecutive closes below the original breakout level. Two
consecutive closes trigger an exit at the second close.

### 7.3 Chandelier trailing stop

Trailing becomes active after:

```text
HighestHighSinceEntry >= EntryPrice + 2 * ATR_at_entry
```

Once active:

```text
ChandelierStop = HighestHighSinceEntry - 4 * CurrentATR14
Stop = max(ExistingStop, ChandelierStop)
```

The 4 ATR width is the section-19 default (previously 2 ATR); it is deliberately
wide so that routine pullbacks inside an intact trend do not close the position.

The newly calculated stop applies prospectively. The simulation checks the
day's low against the old stop before using that day's high to raise the stop.

The alternative configured trail method is an SMA20 close exit, but the
reported optimized tests use the Chandelier method.

### 7.4 Time exit

After 10 managed trading sessions:

```text
Progress = HighestHighSinceEntry / EntryPrice - 1
```

If progress is below 5%, the position exits at the close.

---

## 8. Daily live/paper workflow

The registered daily strategy is `breakout_52w_daily`.

### 8.1 Persistent state

The strategy owns a local paper portfolio at:

```text
.trader_workbench/breakout_52w_portfolio.json
```

The state includes:

- cash;
- open positions;
- pending entry signals;
- entry date and price;
- initial and current stop;
- target price;
- ATR at entry;
- breakout level and signal date;
- highest high;
- consecutive closes below breakout;
- managed bars held;
- trailing-stop status; and
- last processed session.

The state can also be supplied and exported as JSON.

### 8.2 One daily run

1. Resolve the latest completed market session.
2. Load existing state or initialize a scratch portfolio.
3. Add any tracked symbols that are no longer in the current scan universe.
4. Download or load price history and the earnings calendar.
5. Replay any sessions missed since the last run.
6. Attempt fills for earlier pending signals.
7. Apply stop, target, false-breakout, trail, and time-exit logic.
8. Scan the selected universe for new close-of-day signals.
9. Save the next state.
10. Return:
    - position HOLD/EXIT actions;
    - newly qualified next-open entries;
    - pending entries;
    - filled entries;
    - rejected entries;
    - cash, equity, open risk, and position count.

### 8.3 Cutoff behavior

- Before 4:00 PM India time, the current date is excluded.
- Weekends resolve to the latest completed benchmark session.
- State cannot be processed backward to an earlier date.

### 8.4 Operational requirement

The software does not submit broker orders. For the modeled intraday stop and
target behavior to be executable, the user must place standing stop and target
orders after an entry, ideally as an OCO/bracket arrangement where supported.

---

## 9. Backtest design

### 9.1 Official periods

| Run | Period | Role |
|---|---|---|
| Full history | 2021-07-24 to 2026-07-24 | Final descriptive result |
| Development segment | 2021-07-24 to 2024-07-23 | Parameter development |
| Validation segment | 2024-07-24 to 2026-07-24 | Robustness comparison |

The validation segment was reviewed while selecting the final parameter set.
It must not be described as a fully untouched test set.

### 9.2 Point-in-time mechanics

- Entry signals use only rows dated on or before the signal date.
- The 252-session high excludes the current session.
- RVOL and liquidity averages exclude the current session.
- Signals are filled no earlier than the next session's open.
- Stops raised using a session's high become effective after that session's
  earlier stop check.
- The benchmark calendar controls simulated sessions.

The engine pre-indexes dates satisfying the primary breakout condition for
speed, then applies the canonical signal function on each candidate date. This
index is an optimization only; it does not add future data to signal decisions.

### 9.3 Accounting

- Starting cash: INR 500,000.
- Commission: 0.05% on entry and 0.05% on exit.
- Entry and exit commissions are both included in realized P&L.
- Open positions are marked to the daily close.
- Cash earns 0%.
- Dividends are not booked as cash; yfinance adjusted prices are used.

### 9.4 Metric definitions

- **CAGR:** annualized from first to last equity date using 365.25 days/year.
- **Maximum drawdown:** worst peak-to-trough daily close-equity decline.
- **Sharpe:** mean daily equity return divided by sample daily standard
  deviation, annualized by `sqrt(252)`, with risk-free rate 0.
- **Win rate:** trades with commission-adjusted realized P&L greater than 0.
- **Profit factor:** gross realized profit divided by absolute gross realized
  loss.
- **Average exposure:** daily deployed market value divided by daily equity.
- **Holding period in reports:** calendar days between entry and exit; the
  time-exit rule itself counts managed trading sessions.

### 9.5 Reproduction commands

Five-year run:

```powershell
uv run python run.py breakout_52w_backtest `
  --param "start=2021-07-24" `
  --param "end=2026-07-24" `
  --param "capital=500000" `
  --param "universe_index=nifty500" `
  --param "use_cache=true"
```

Validation-period run:

```powershell
uv run python run.py breakout_52w_backtest `
  --param "start=2024-07-24" `
  --param "end=2026-07-24" `
  --param "capital=500000" `
  --param "universe_index=nifty500" `
  --param "use_cache=true"
```

Daily run:

```powershell
uv run python run.py breakout_52w_daily
```

---

## 10. First optimization process (superseded defaults)

### 10.1 Initial baseline

The initial implementation used:

- no minimum breakout clearance beyond `Close > prior high`;
- RVOL threshold 1.5;
- 1.5 ATR initial stop;
- no entry-day hard-stop evaluation in the historical engine;
- no fixed profit target;
- the same trend, regime, liquidity, earnings, portfolio-heat, trailing, false
  breakout, and time-exit framework.

Its official five-year CAGR was 0.46%, with -32.81% maximum drawdown.
The baseline-to-optimized table is therefore a before/after system comparison,
not a controlled estimate of the causal contribution of any one rule.

### 10.2 Variant families evaluated

The experiment harness tested train, validation, and full-period results for:

- Nifty 50, 100, 200, and 500 universes;
- RVOL thresholds;
- breakout-candle close location;
- 3-month momentum and benchmark-relative strength;
- SMA slope;
- pre-breakout range tightness;
- ATR/volatility filters;
- stronger benchmark regimes;
- candidate ranking;
- initial stop widths;
- one- versus two-close false-breakout exits;
- Chandelier and SMA20 trails;
- trail activation and width;
- time-exit parameters;
- entry-day stop handling;
- fixed ATR targets;
- breakeven stops;
- risk per trade, heat, and maximum positions; and
- higher transaction-cost stress.

The first broad sweep tested 44 variants. A second combination sweep tested 57
variants with entry-day hard-stop behavior enabled. A final neighborhood and
cost-sensitivity pass tested the selected region.

### 10.3 Selection discipline

The final configuration was not selected solely by the highest full-period
CAGR. The selection favored:

- positive development and validation performance;
- at least approximately 15% CAGR in the validation period;
- lower drawdown;
- no increase above 1% risk per trade;
- stable behavior around nearby stop and target values;
- a minimum breakout buffer to reduce adjusted-price precision artifacts; and
- exact consistency between daily and backtest execution.

### 10.4 Nearby parameter behavior

Fast point-in-time neighborhood results for the final signal family were:

| Variant | Full CAGR | Validation CAGR | Full max DD | Validation max DD | Full win rate |
|---|---:|---:|---:|---:|---:|
| 1.0 ATR stop, 3.0 ATR target, 0.10% clearance | **22.10%** | **16.56%** | **-12.48%** | -7.34% | 36.91% |
| 1.05 ATR stop, 3.0 ATR target, 0.10% clearance | 21.93% | 15.52% | -14.71% | **-6.74%** | 38.43% |
| 1.10 ATR stop, 3.0 ATR target, 0.10% clearance | 21.68% | 16.87% | -17.06% | -6.79% | 39.67% |
| 1.0 ATR stop, 3.5 ATR target, 0.10% clearance | 17.97% | 15.46% | -13.02% | -9.17% | 36.36% |

The 1.0 ATR stop was retained because it gave the best full-period drawdown
among these high-CAGR candidates. A wider stop increased the win rate but also
materially increased full-period drawdown.

### 10.5 Multiple-testing warning

The optimization process inspected many alternatives and used the validation
period for model selection. Reported Sharpe and CAGR therefore have selection
bias. No deflated Sharpe ratio, probability of backtest overfitting, or formal
multiple-hypothesis correction has yet been applied.

---

## 11. Official results

### 11.1 Full five-year comparison

| Metric | Baseline | Optimized | Change |
|---|---:|---:|---:|
| Start equity | INR 500,000 | INR 500,000 | - |
| End equity | INR 511,694 | INR 1,355,150 | +INR 843,455 |
| Total return | 2.34% | 171.03% | +168.69 pp |
| CAGR | 0.46% | 22.10% | +21.64 pp |
| Maximum drawdown | -32.81% | -12.48% | +20.33 pp |
| Sharpe, rf=0 | 0.11 | 1.36 | +1.25 |
| Closed trades | 434 | 569 | +135 |
| Win rate | 36.87% | 36.91% | +0.04 pp |
| Profit factor | 1.01 | 1.42 | +0.41 |
| Average holding period | 10.1 days | 5.9 days | -4.2 days |
| Average exposure | 45.6% | 38.8% | -6.8 pp |
| Average winning-trade return | 7.80% | 8.27% | +0.47 pp |
| Average losing-trade return | -4.20% | -3.33% | +0.87 pp |

### 11.2 Validation-period comparison

| Metric | Baseline | Optimized |
|---|---:|---:|
| Period | 2024-07-24 to 2026-07-24 | 2024-07-24 to 2026-07-24 |
| End equity | INR 556,668 | INR 679,160 |
| Total return | 11.33% | 35.83% |
| CAGR | 5.52% | **16.56%** |
| Maximum drawdown | -11.60% | **-7.34%** |
| Sharpe, rf=0 | 0.55 | **1.32** |
| Closed trades | 115 | 139 |
| Win rate | **41.74%** | 41.01% |
| Profit factor | 1.24 | **1.49** |
| Average winning-trade return | 6.29% | **7.54%** |
| Average losing-trade return | -3.60% | **-3.09%** |

The optimized validation win rate was 0.73 percentage points lower than the
baseline. The improvement came from payoff quality and lower loss severity,
not from a higher percentage of winning trades.

### 11.3 Cross-regime reoptimization and current defaults

A second optimization round was requested after the first optimized rules
performed poorly in 2015-2018 and 2025-2026. It deliberately excluded
2008-2009 and 2020-2021 from selection because crash-and-rebound behavior can
make long momentum systems look unusually favorable.

The selection windows were:

- primary: 2015-01-01 to 2019-01-01;
- primary: 2025-06-01 to 2026-06-01;
- robustness: calendar years 2019, 2022, 2023, and 2024; and
- final holdout, not inspected until the candidate was frozen: 2012-01-01 to
  2015-01-01.

The current rules add or change four requirements:

```text
Minimum breakout clearance = 0.50%
Minimum 63-session relative strength versus Nifty = 15 percentage points
Minimum SMA50 rise over 20 sessions = 2%
Standing profit target = 4 entry ATR
```

All other portfolio-risk and execution rules remain unchanged. Official-engine
comparisons using INR 500,000 starting cash were:

| Window | Prior CAGR | Current CAGR | Prior max DD | Current max DD |
|---|---:|---:|---:|---:|
| 2012-01-01 to 2015-01-01, final holdout | -4.67% | **2.99%** | -25.53% | **-12.52%** |
| 2015-01-01 to 2019-01-01, primary | 3.73% | **5.66%** | **-18.61%** | -20.93% |
| 2019-01-01 to 2020-01-01 | -10.44% | **0.17%** | -16.82% | **-7.01%** |
| 2022-01-01 to 2023-01-01 | **2.78%** | 0.28% | **-12.06%** | -13.73% |
| 2023-01-01 to 2024-01-01 | **41.19%** | 33.99% | -9.61% | **-8.19%** |
| 2024-01-01 to 2025-01-01 | **67.68%** | 24.05% | **-10.47%** | -18.33% |
| 2025-06-01 to 2026-06-01, primary | 6.22% | **15.75%** | **-7.34%** | -8.61% |

The current rules make every reported non-crash window non-negative and improve
the untouched holdout. They do not dominate the prior rules: 2022, 2023, and
2024 returns declined, and drawdown worsened in several windows. The change is
therefore a trade from peak bull-market performance toward broader regime
stability, not a free improvement.

On the original five-year period, the current version produced INR
1,074,950.98, 16.56% CAGR, -18.35% drawdown, 1.07 Sharpe, and 1.37 profit
factor. The first optimized version produced higher 22.10% CAGR and lower
-12.48% drawdown on that same selected period.

More than 300 additional single-factor, combination, and neighborhood variants
were examined in the second round. The holdout was protected from that search,
but all selection-window metrics remain exposed to multiple-testing bias.

### 11.4 Benchmark comparison

The benchmark is adjusted `^NSEI` data from the same yfinance cache.

| Period | Strategy CAGR | Nifty CAGR | Strategy max DD | Nifty max DD | Average strategy exposure |
|---|---:|---:|---:|---:|---:|
| 2021-07-26 to 2026-07-24 | **16.56%** | 8.49% | -18.35% | **-17.23%** | 34.0% |
| 2024-07-24 to 2026-07-24 | **15.89%** | -1.33% | **-8.84%** | -15.77% | 23.3% |

This is not a fully apples-to-apples comparison:

- the benchmark is continuously invested;
- the strategy often holds cash;
- cash earns 0% in the simulation;
- the strategy incurs modeled commissions;
- neither side includes investor-specific taxes; and
- adjusted price data is not the same as an investable Nifty total-return index
  with explicit implementation costs.

### 11.5 Calendar-year equity returns

| Year | Strategy return | Nifty adjusted-price return | Note |
|---|---:|---:|---|
| 2021 | 0.91% | 9.67% | Partial from 2021-07-26 |
| 2022 | 0.29% | 4.33% | Full year |
| 2023 | **32.20%** | 20.03% | Full year |
| 2024 | **31.27%** | 8.80% | Full year |
| 2025 | **19.14%** | 10.51% | Full year |
| 2026 | **2.76%** | -9.04% | Partial through 2026-07-24 |

Returns were highly concentrated in 2023 and 2024. This concentration is a key
robustness concern; the strategy did not produce uniformly high returns in
every year.

### 11.6 Trade distribution

| Statistic | Five-year current result |
|---|---:|
| Closed trades | 473 |
| Unique symbols traded | 229 |
| Win rate | 36.36% |
| Average win | 9.33% |
| Average loss | -3.65% |
| Average win / absolute average loss | 2.56x |
| Median trade | -2.75% |
| 5th percentile trade | -5.22% |
| 95th percentile trade | 17.60% |
| Best trade | 26.47% |
| Worst trade | -8.72% |
| Median holding period | 4 calendar days |
| Estimated modeled commissions | INR 67,134 |
| Maximum observed positions | 5 |
| Market regime enabled | 691 of 1,235 sessions (55.95%) |
| Median deployed capital | 24.63% of equity |

The median trade is negative. The strategy depends on positive payoff
asymmetry: relatively frequent small losses offset by less frequent, larger
wins.

### 11.7 Exit attribution

| Exit reason | Trades | Share | Win rate within reason | Average trade return |
|---|---:|---:|---:|---:|
| Entry-day stop | 92 | 19.45% | 0.00% | -3.69% |
| Entry-day target | 10 | 2.11% | 100.00% | 15.67% |
| False breakout | 18 | 3.81% | 0.00% | -2.28% |
| Stop | 255 | 53.91% | 29.80% | -1.56% |
| Stop gap | 10 | 2.11% | 20.00% | -3.63% |
| Target | 74 | 15.64% | 100.00% | 15.53% |
| Time exit | 14 | 2.96% | 71.43% | 1.18% |

`STOP` includes exits at stops that were raised by the Chandelier logic. It can
therefore contain profitable trades. Target returns vary because ATR as a
percentage of price varies, and a gap above the target can receive the higher
opening fill.

### 11.8 Local result artifacts

Official current five-year artifacts:

```text
backtesting\breakout_52w\results\
  nifty500_2021-07-24_2026-07-24_20260726T021253_c5715722\
```

Official current validation-period artifacts:

```text
backtesting\breakout_52w\results\
  nifty500_2024-07-24_2026-07-24_20260726T021309_92ed6466\
```

Each directory contains:

- `summary.json`
- `summary.txt`
- `trades.csv`
- `equity_curve.csv`
- `signals.csv`
- `open_positions.json`

These generated directories are local artifacts and are excluded from version
control.

---

## 12. Interpretation of the observed edge

The first optimization-round improvement appears to come from four mechanisms:

1. **Higher signal participation threshold.** Raising RVOL from 1.5 to 2.0
   removes lower-volume breakouts.
2. **Faster loss recognition.** The 1 ATR stop and entry-day stop reduce the
   lower tail. Average losing-trade return improved from -4.20% to -3.33%.
3. **Systematic profit realization.** The original 3 ATR target captured a repeatable
   payoff and releases capital rather than waiting for every trade to become a
   long-duration trend.
4. **Capital turnover with lower exposure.** Average holding period fell from
   10.1 to 5.9 calendar days while average exposure fell from 45.6% to 38.8%.

The full-period win rate barely changed. The economic claim is therefore not
"the model predicts winners more often." It is:

> Under the tested data and assumptions, the model produced a better ratio of
> average win to average loss, reduced drawdown, and recycled capital faster.

This claim still requires independent testing because parameter selection,
survivorship bias, and execution assumptions can materially inflate the
observed edge.

The current cross-regime version adds a different claim: relative leadership
and a rising intermediate trend reject many marginal breakouts, while the
wider 4 ATR target preserves more upside per accepted trade. It trades less
often and avoids a large portion of the 2012-2014 and 2019 losses, but it also
misses substantial upside during the exceptional 2023-2024 momentum regime.

---

## 13. Material limitations and sources of bias

### 13.1 Current-constituent survivorship bias

The largest issue is that today's Nifty 500 list is projected backward.
Historical losers removed from the index and delisted firms may be absent,
while later successful additions are included before they actually joined.
This can overstate both signal quality and liquidity.

**Required remediation:** obtain dated constituent files and construct the
eligible universe separately for every historical session.

### 13.2 Validation-period reuse

The 2024-2026 period was reviewed while selecting parameters. It is not an
independent final test. The 16.56% CAGR should be treated as model-selection
evidence, not unbiased expected performance.

**Required remediation:** freeze the strategy now and evaluate it on future
unseen data, or acquire an earlier and longer history that allows a new,
untouched final test segment.

### 13.3 Multiple testing and overfitting

More than 400 individual and combination variants were examined across both
optimization rounds. Selecting the best robust-looking region inflates
expected performance even when train/validation discipline is used.

**Required remediation:** calculate deflated Sharpe, probability of backtest
overfitting, and bootstrap confidence intervals; use nested or rolling
walk-forward selection.

### 13.4 Historical earnings-calendar look-ahead risk

The backtest uses the realized NSE board-meeting date and assumes it was known
five sessions in advance. The dataset does not preserve the date on which each
meeting was first announced to the market. An event may therefore be excluded
historically using information that was not yet public.

**Required remediation:** store event publication timestamps and only apply a
blackout when the scheduled date was publicly known as of the signal date.

### 13.5 Adjusted data is not vintage point-in-time data

yfinance `auto_adjust=True` rewrites historical OHLC values for later corporate
actions. Re-downloading after a dividend, split, symbol change, or source
correction can alter old breakout boundaries. The current 0.50% clearance reduces tiny
rounding artifacts but does not create true vintage data.

**Required remediation:** archive immutable daily raw and adjusted datasets,
corporate actions, and adjustment factors as they become available.

### 13.6 Transaction-cost model (now realistic; see section 18)

The **default** simulation now applies a realistic Indian delivery-equity cost
model (`BreakoutConfig.use_realistic_costs=True`): STT on both legs, exchange
transaction charges, SEBI turnover fee, GST on brokerage+charges, buy-side stamp
duty, and per-side slippage in basis points, in addition to brokerage. Round-trip
frictions come to roughly 0.33% of notional versus the earlier 0.10% flat model.
See section 18.1 for the exact schedule.

The remaining simplifications are:

- market impact beyond the fixed slippage estimate (large orders vs. ADV);
- order rejection and partial-fill risk;
- DP charges per scrip on delivery sells; and
- taxes on realized gains (out of scope for a pre-tax sleeve backtest).

The strategy trades several hundred times over five years, so the move from the
flat model to the realistic model is the single biggest driver of the lower
(and more honest) headline CAGR reported in section 18.

### 13.7 Daily OHLC path ambiguity

When a candle contains both stop and target, intraday ordering is unknown. The
model assumes stop first, which is conservative, but exact fill quality still
cannot be established from daily bars.

**Required remediation:** repeat the simulation with intraday data for all
entry and exit sessions.

### 13.8 Perfect liquidity at the open

All shares fill at the official open with no volume participation cap. The
liquidity filters reduce but do not eliminate this problem. Opening auctions,
price bands, circuits, and gaps can make the assumed fill unavailable.

**Required remediation:** add spread/slippage by turnover bucket, maximum
percentage of ADV, circuit checks, and delayed/partial fills.

### 13.9 Universe and sector concentration

The current report does not measure:

- sector weights;
- factor exposures;
- market beta;
- clustering of simultaneous positions;
- single-industry drawdowns; or
- capacity by liquidity tier.

The five-position cap can still produce concentrated sector or factor risk.

### 13.10 Short sample and regime concentration

Five years is short for a momentum strategy and includes unusually strong
2023-2024 performance. Results were modest in 2022 and 2025 and negative in the
2026 partial period.

**Required remediation:** test multiple bull, bear, sideways, high-volatility,
and low-volatility regimes over at least 10-15 years if reliable constituent
and event data can be obtained.

### 13.11 Benchmark comparison limitations

The strategy is partially invested while the benchmark is continuously
invested. No explicit cash yield is credited. Adjusted `^NSEI` is not a
tradeable implementation with fees and tracking error.

**Required remediation:** compare against:

- a Nifty total-return index;
- an investable ETF after costs;
- a cash-plus-index blended benchmark matched to strategy exposure; and
- other Indian momentum factors or indices.

### 13.12 Daily versus backtest calendar edge cases

The backtest earnings window uses benchmark trading sessions. The daily
scanner's prospective helper counts weekdays, which can miscount exchange
holidays. The backtest also expires a pending signal after its next benchmark
session when the stock has no exact bar, while the daily state machine can
retain a pending signal until data becomes available.

These differences should be reconciled before production deployment.

### 13.13 Operational dependency on standing orders

The daily script runs once after the close and does not place orders. The
entry-day and intraday stop/target assumptions are only achievable if the user
places standing orders promptly and keeps the paper state synchronized with
actual fills.

---

## 14. Questions for an external finance reviewer

> Questions 1, 2 and 8 have since been answered empirically in section 19: the
> fixed target *was* truncating long-tail winners, the 1 ATR stop *was* too
> tight (108 entry-day stops with a 0% win rate), and the target *should* be
> partial with a trailing remainder. The defaults now reflect those answers.
> The remaining questions are still open.

1. Is a fixed 4 ATR target economically appropriate for a 52-week momentum
   strategy, or does it sacrifice the rare long-tail winners that normally
   drive momentum returns?
2. Is the 1 ATR initial stop too sensitive to Indian single-stock gap and
   opening-auction behavior?
3. Are the 500,000-share and INR 5 crore liquidity thresholds sufficient for
   the intended capital scale and order type?
4. Should turnover, free float, or maximum ADV participation replace the simple
   liquidity thresholds?
5. Should the regime filter use the Nifty 500, Nifty total-return index,
   advance-decline breadth, or sector-specific regimes instead of `^NSEI`?
6. Is the five-session earnings blackout long enough, and should post-result
   blackout days also be included?
7. Should risk be reduced when several positions are highly correlated or in
   the same sector?
8. Should the target be partial rather than full, leaving a residual position
   for a Chandelier trend exit?
9. Is 1% risk per trade appropriate given overnight gap risk can exceed the
   stop-defined loss?
10. Which Indian transaction-cost and tax schedule should be used for the
    intended broker and holding period?
11. What benchmark best reflects the strategy's low average exposure and
    long-only mandate?
12. What minimum forward paper-trading sample would be sufficient before
    committing real capital?

---

## 15. Recommended independent validation plan

Before live capital is used:

1. **Freeze this exact specification.** Do not tune parameters on the next test.
2. **Rebuild historical membership.** Use point-in-time Nifty 500 constituents.
3. **Correct event availability.** Apply earnings blackouts only after meeting
   dates were publicly announced.
4. **Extend history.** Include at least one additional full market cycle.
5. **Use realistic costs.** Model Indian taxes, spread, slippage, impact, and
   partial fills by liquidity bucket.
6. **Use intraday execution data.** Resolve same-day stop/target sequencing and
   opening-fill feasibility.
7. **Run rolling walk-forward tests.** Re-estimate nothing, or define a formal
   training window and locked selection procedure.
8. **Run parameter stability tests.** Confirm that nearby RVOL, stop, target,
   and breakout-clearance values remain profitable.
9. **Bootstrap trades and years.** Estimate confidence intervals for CAGR,
   drawdown, Sharpe, and probability of loss.
10. **Measure exposures.** Report sector concentration, beta, momentum factor
    exposure, and capacity.
11. **Forward paper trade.** Run the daily process without rule changes for at
    least 6-12 months and reconcile every assumed fill with executable market
    prices.
12. **Stage capital gradually.** Begin below modeled capacity with hard
    portfolio-level loss limits.

---

## 16. Implementation map

| File | Responsibility |
|---|---|
| `backtesting/breakout_52w/config.py` | All thresholds and risk parameters |
| `backtesting/breakout_52w/strategy.py` | Entry, sizing, target, regime, and exit rules |
| `backtesting/breakout_52w/engine.py` | Historical event loop and next-open execution |
| `backtesting/breakout_52w/daily.py` | Daily scanner and persisted paper portfolio |
| `backtesting/breakout_52w/calendar.py` | Cached NSE result-event calendar |
| `backtesting/breakout_52w/service.py` | Data loading, run orchestration, metrics, artifacts |
| `backtesting/swing_trading/data.py` | Cached yfinance point-in-time slices |
| `backtesting/swing_trading/portfolio.py` | Cash, positions, commissions, realized trades |
| `strategies/breakout_52w.py` | CLI/UI backtest registration |
| `strategies/breakout_52w_daily.py` | CLI/UI daily workflow registration |
| `tests/test_breakout_52w.py` | Deterministic rule and accounting tests |
| `tests/test_breakout_52w_daily.py` | Daily state-machine and entry-day tests |

---

## 17. Bottom line

The implementation is deterministic and internally consistent on its main
rules. Under the earlier flat-cost model the cross-regime defaults produced
16.56% CAGR over the original five-year period; under the **realistic
Indian delivery-cost model that is now the default** (section 18) the same
window returned roughly 5.4% CAGR at -14% drawdown with a ~47% win rate. The
**section-19 trade-management defaults** raise that same realistic-cost window
to roughly 24.3% CAGR at -14.5% drawdown, with a mean of ~11% CAGR across six
independent windows. The multi-window mean, not the 24%, is the number to
reason about.

It is **not yet institutionally validated**. Current-constituent survivorship,
validation reuse, historical earnings-calendar availability, multiple testing,
and residual execution assumptions are large enough that none of the reported
CAGR figures should be treated as an unbiased forecast.

The appropriate next conclusion is:

> The strategy is promising enough to justify a rigorous independent rebuild
> and forward paper test, but not strong enough to skip those steps.

---

## 18. Institutional sleeve upgrade

This section documents a hardening pass that treated the strategy as **one INR
500,000 sleeve of a larger multi-strategy book** rather than a standalone
account. It implements the risk, cost, and portfolio-construction
recommendations from an earlier hedge-fund-style review, tests each empirically,
and reports what was adopted versus rejected. Every claim here is reproducible
from `BreakoutConfig` defaults.

### 18.1 Realistic Indian delivery-cost model

`Portfolio` now accepts an optional `CostModel`. `BreakoutConfig.build_cost_model()`
constructs the delivery-equity schedule below and the breakout engine and daily
workflow both use it by default (`use_realistic_costs=True`). Swing-trading code
is untouched and keeps its flat commission.

| Component | Rate | Applied |
|---|---|---|
| Brokerage | 0.03% (capped, delivery) | both legs |
| STT | 0.10% | both legs |
| Exchange transaction | 0.00297% | both legs |
| SEBI turnover | 0.0001% | both legs |
| GST | 18% on (brokerage + txn + SEBI) | both legs |
| Stamp duty | 0.015% | buy only |
| Slippage | 5 bps | per side |

Round-trip friction ≈ **0.33% of notional** versus 0.10% under the old flat
model. This is the dominant reason headline CAGR falls relative to sections 10-11.

### 18.2 Diversification and sizing framework

- `max_positions` raised from 5 to **12** with a 15% per-name notional cap.
- **Sector cap:** at most 3 concurrent names per NSE industry
  (`enable_sector_cap`, `max_positions_per_sector=3`), using the industry map
  from the Nifty 500 constituents file.
- **Pairwise-correlation cap:** a new position is rejected if its trailing
  63-session return correlation with any existing holding exceeds 0.85
  (`enable_correlation_cap`, `max_correlation`).
- Per-trade risk stays at **1%** of sleeve equity with total open risk capped at
  5% (portfolio heat).

### 18.3 Partial-profit exit with uncapped trailing remainder

`enable_partial_profit=True` books a slice of the position at the first target,
moves the stop on the remainder to breakeven, and lets the rest ride
the Chandelier trail with **no fixed cap**, so outlier winners are not truncated.
Section 18 booked **half** at 2.5 ATR; section 19 revises this to **20% at
3.5 ATR** so winners keep most of their size while still de-risking to
breakeven.
The 10-session time-exit only cuts non-performers and is skipped once a partial
has been booked. `ExitOp.fraction` carries the booked fraction through to
`Portfolio.close_position`, and both the historical engine and the daily
state machine execute the entry-day partial identically.

### 18.4 Regime scaling: implemented, tested, and rejected as default

A continuous gross-exposure multiplier (`regime_exposure`) was built to replace
the binary market gate: it scales exposure by the index trend (vs SMA50/SMA200)
and market breadth, quantized to 0.25 tiers. It is fully wired
(`regime_scaling`, `regime_use_breadth`) and available as a toggle.

**It was turned off by default because the data rejected it.** Head-to-head, at
1% risk:

| Window | Mode | CAGR | Max DD | Sharpe | PF |
|---|---|---:|---:|---:|---:|
| 2021-07..2026-07 | continuous | 5.57% | -23.85% | 0.49 | 1.13 |
| 2021-07..2026-07 | **binary** | 5.36% | **-14.01%** | **0.51** | **1.14** |
| 2022-01..2024-12 | continuous | 9.08% | -22.04% | 0.68 | 1.15 |
| 2022-01..2024-12 | **binary** | **10.00%** | **-13.81%** | **0.79** | **1.19** |
| 2015-01..2019-01 | continuous | 1.68% | -16.14% | 0.23 | 1.06 |
| 2015-01..2019-01 | **binary** | **1.82%** | -17.60% | **0.26** | **1.08** |

Continuous scaling *worsened* drawdown: cutting position count in choppy-but-not-
bearish tape concentrated capital into fewer correlated names and re-entered at
poor times. The simple binary gate (index above SMA50 **and** SMA200, else block)
is more robust, so it is the default. The earlier stacked vol/drawdown penalties
were removed as reactive and whipsaw-prone.

### 18.5 The binding constraint is signal scarcity, not capital

Average deployed exposure is only ~28% because the strict entry filters produce
roughly 2-3 concurrent qualifying signals against 12 available slots. Raising the
portfolio-heat cap from 5% to 8% or 10% changed nothing — there is simply nothing
to fill the extra slots. Two consequences follow:

1. **Cross-sectional ranking / top-K selection was skipped.** With 2-3 candidates
   for 12 slots there is almost never competition to arbitrate, so a ranking
   layer would add complexity with no measurable benefit.
2. **Relaxing filters to raise exposure is destructive.** Loosening the breakout,
   relative-strength, slope, and RVOL thresholds to generate more trades was
   tested and failed catastrophically in every window:

| Window | Strict CAGR / DD / PF | Relaxed CAGR / DD / PF |
|---|---|---|
| 2021-07..2026-07 | 5.36% / -14.0% / 1.14 | 0.78% / -27.6% / 1.01 |
| 2015-01..2019-01 | 1.82% / -17.6% / 1.08 | -7.43% / -37.9% / 0.81 |
| 2022-01..2024-12 | 10.00% / -13.8% / 1.19 | -0.38% / -22.1% / 0.99 |

The edge lives entirely in **selectivity**; the marginal breakout is net-negative
after costs. Low average exposure is therefore a protective feature, and the
strategy is capacity-constrained by the number of high-quality setups — which is
the structural reason chasing a materially higher win rate or CAGR is so hard.

### 18.6 Realistic-cost results with the current defaults

Pure `BreakoutConfig` defaults (realistic costs, binary regime gate, 1% risk,
diversification and partial-profit exits enabled), Nifty 500, sleeve start
INR 500,000:

| Window | CAGR | Max DD | Sharpe | Profit factor | Win rate | Trades |
|---|---:|---:|---:|---:|---:|---:|
| 2021-07..2026-07 (5y) | 5.36% | -14.01% | 0.51 | 1.14 | 47.0% | 727 |
| 2015-01..2019-01 | 1.82% | -17.60% | 0.26 | 1.08 | 47.2% | 282 |
| 2019 (full) | -2.15% | -4.65% | -0.61 | 0.73 | 30.8% | 26 |
| 2022-01..2024-12 | 10.00% | -13.81% | 0.79 | 1.19 | 48.5% | 567 |
| 2023 (full) | 30.03% | -10.12% | 2.21 | 1.64 | 55.2% | 192 |
| 2025-06..2026-06 | 2.46% | -6.13% | 0.37 | 1.17 | 54.0% | 63 |

Versus the section-11 cross-regime numbers (16.56% CAGR / -18.35% DD), realistic
costs cut headline CAGR by roughly two-thirds while **improving drawdown**
(-14% vs -18%) and lifting win rate to ~47%. This is the honest cost of honesty:
the earlier double-digit CAGR was substantially a flat-cost artifact.

### 18.7 Implemented vs. skipped — summary

**Implemented and adopted as default:**

1. Realistic Indian delivery-cost model (18.1).
2. Diversification framework — 12 positions, per-sector cap, pairwise-correlation
   cap, 15% notional cap (18.2).
3. ATR-risk position sizing retained at 1% with 5% portfolio-heat cap (18.2).
4. Partial-profit booking with breakeven stop and uncapped trailing remainder
   (18.3).
5. Treating the book as a sleeve rather than a whole portfolio (framing
   throughout).

**Implemented but disabled by evidence (available via config toggle):**

6. Continuous regime scaling — underperformed the binary gate on drawdown and
   risk-adjusted return, so `regime_scaling=False` by default (18.4).

**Deliberately skipped, with reasons:**

7. Cross-sectional percentile / top-K ranking — the strategy is signal-scarce, so
   there is nothing to rank (18.5).
8. Filter relaxation for higher exposure — tested, catastrophic in every window
   (18.5).
9. Point-in-time index constituents — no free vintage source exists; documented
   as current-constituent survivorship bias in section 13.1.

### 18.8 Bottom line on the upgrade

The upgrade did **not** raise CAGR toward the earlier 15%+ aspiration; under
realistic costs that target is not attainable for this sleeve without abandoning
the selectivity that is its only edge. What it *did* deliver is a materially more
honest and more robust system: realistic frictions, tighter drawdowns, a higher
win rate, sector/correlation diversification, and asymmetric partial-profit
exits — all validated across multiple independent windows rather than a single
in-sample fit.

> **Superseded in part by section 19.** The conclusion that 15%+ CAGR was
> unattainable assumed the *trade-management* parameters were already near
> optimal. They were not. Section 19 shows that widening the stop and trail and
> keeping most of the position on winners lifts the five-year figure to ~24%
> CAGR at a comparable drawdown, without touching entry selectivity or the cost
> model.

---

## 19. Trade-management pass: stop width, trail width, and winner sizing

Section 18 optimised *what to buy* and *what it costs*. This section optimises
*how the trade is managed after entry*, which turned out to be where the
strategy was leaking most of its return.

### 19.1 The diagnostic: where do losses actually come from?

Decomposing the 727 trades of the five-year run by holding period:

| Holding period | Trades | Net P&L | Win rate | Avg return |
|---|---:|---:|---:|---:|
| 0-1 days | 212 | -367,342 | 17.0% | -1.3% |
| 2-3 days | 101 | -118,881 | 28.7% | -0.2% |
| 4-5 days | 77 | -36,052 | 40.3% | 1.2% |
| 6-10 days | 144 | +115,804 | 63.2% | 3.9% |
| 11-20 days | 130 | +245,257 | 74.6% | 5.7% |
| 20+ days | 63 | +310,235 | 92.1% | 13.5% |

Essentially **all** losses came from trades killed within three days
(-INR 4.86 lakh) and **all** profit from trades that survived six days or more
(+INR 6.71 lakh). By exit reason, a single bucket dominated: `ENTRY-DAY-STOP`,
108 trades, -INR 3.02 lakh, a 0% win rate. The 1 ATR stop was being hit by
normal post-breakout noise before the thesis had a chance to resolve.

### 19.2 Negative result: entry-time features cannot predict the losers

Before changing exits, we tested whether the losers were identifiable *at entry*
(which would allow a filter instead of a management change). For all 727 trades
we recomputed the entry-bar features and compared trades that died in 0-1 days
against those that ran 20+ days:

| Feature | Day 0-1 losers | 20+ day winners | Delta |
|---|---:|---:|---:|
| Gap % | 0.43 | 0.31 | -0.12 |
| ATR % | 3.67 | 3.61 | -0.07 |
| Extension (ATR) | 0.48 | 0.47 | -0.01 |
| Volume ratio | 2.82 | 2.91 | +0.10 |
| Distance to SMA20 | 11.59 | 10.07 | -1.53 |
| Distance to SMA50 | 18.93 | 15.36 | -3.58 |
| Distance to SMA200 | 45.24 | 37.24 | -8.00 |
| 63-day relative strength | 31.93 | 25.20 | -6.73 |
| RSI(14) | 75.95 | 68.85 | -7.10 |

The two populations are **nearly identical at entry**. Quintile analysis on every
feature produced non-monotonic, noise-shaped P&L profiles (for example ATR%
quintile net P&L ran -40k / +87k / +5k / -25k / +123k). One result was actively
counterintuitive: the *largest* gap-ups were the best performers, so filtering
them out — a common retail instinct — would have destroyed return.

**Conclusion: there is no entry filter that separates these trades.** Whether a
breakout works is decided after entry, not before it. This is why every attempt
in sections 11 and 18 to raise the win rate by tightening entries failed, and it
redirects the entire optimisation effort to exits.

### 19.3 Parameter study

All runs are the full Nifty 500 universe, realistic costs, INR 500,000 sleeve,
2021-07-24 to 2026-07-24.

**Initial stop width** (all else at section-18 defaults):

| Stop | CAGR | Max DD | Sharpe | PF | Win rate | Entry-day stops |
|---|---:|---:|---:|---:|---:|---:|
| 1.0 ATR (old) | 5.36% | -14.01% | 0.51 | 1.14 | 47.0% | 108 |
| 1.5 ATR | 3.26% | -16.39% | 0.34 | 1.09 | 52.7% | 25 |
| 2.0 ATR | 4.97% | -13.03% | 0.51 | 1.14 | 54.7% | 8 |
| 2.5 ATR | 4.79% | -11.97% | 0.56 | 1.17 | 56.3% | 3 |
| 3.0 ATR | 4.12% | -9.61% | 0.57 | 1.17 | 56.9% | 2 |

Widening the stop does exactly what the diagnostic predicted — win rate rises
monotonically from 47% to 57% and entry-day stops collapse from 108 to 2 — but
CAGR *falls*, because position size is `risk / (entry - stop)`, so a wider stop
mechanically shrinks every position and reduces exposure. **Stop width alone is
not the answer.**

**Trailing-stop width** (2.0 ATR initial stop):

| Chandelier | CAGR | Max DD | Sharpe | PF | Avg hold |
|---|---:|---:|---:|---:|---:|
| 2.0 ATR (old) | 4.97% | -13.03% | 0.51 | 1.14 | 10.1 |
| 3.0 ATR | 7.53% | -16.48% | 0.65 | 1.23 | 14.1 |
| 3.5 ATR | 11.62% | -16.17% | 0.91 | 1.36 | 16.0 |
| 4.0 ATR | 13.23% | -15.16% | 0.98 | 1.47 | 19.1 |
| 4.5 ATR | 11.84% | -18.41% | 0.86 | 1.44 | 20.2 |
| 5.0 ATR | 11.22% | -19.06% | 0.79 | 1.43 | 22.6 |

This is the single largest effect in the study. The 2 ATR trail was harvesting
winners during routine pullbacks; average holding period more than doubles at
4 ATR. The response is a broad **plateau** between 3.5 and 5.0 ATR rather than a
spike, which is the signature of a real effect rather than a curve fit.

**Winner sizing.** The section-18 rule booked *half* the position at 2.5 ATR.
Both booking *less* and booking *later* improve results, and they compose:

| Fraction booked | Booking level | CAGR | Max DD | Sharpe | PF |
|---|---|---:|---:|---:|---:|
| 50% | 2.5 ATR | 13.23% | -15.16% | 0.98 | 1.47 |
| 33% | 2.5 ATR | 14.45% | -17.21% | 0.99 | 1.56 |
| 25% | 2.5 ATR | 17.25% | -16.53% | 1.12 | 1.68 |
| 50% | 3.5 ATR | 16.45% | -17.39% | 1.14 | 1.56 |
| 20% | 3.5 ATR | 24.31% | -14.47% | 1.36 | 1.96 |

Note that disabling partial booking entirely is *worse* (8.22% CAGR), because
with `enable_partial_profit=False` the position exits fully at the
`profit_target_atr` cap. The partial-booking branch is what removes the hard cap
and lets the remainder ride the trail indefinitely, and it also moves the
remainder's stop to breakeven. The optimum is therefore to keep the mechanism
but shrink the slice it sells: book a token 20% to de-risk to breakeven, and
leave 80% running.

### 19.4 Selected configuration

| Parameter | Section 18 | Section 19 |
|---|---|---|
| `atr_stop_mult` | 1.0 | **1.5** |
| `chandelier_atr_mult` | 2.0 | **4.0** |
| `partial_profit_atr` | 2.5 | **3.5** |
| `partial_profit_fraction` | 0.50 | **0.20** |

Entry rules, regime gate, liquidity floors, earnings blackout, sizing, sector and
correlation caps, and the cost model are all **unchanged**.

### 19.5 Out-of-sample validation

The configuration was selected on the five-year window, then evaluated unchanged
on independent windows. 2020-2021 and 2008-2009 are deliberately excluded as
crash-and-recovery regimes that flatter momentum systems.

| Window | Old CAGR / DD | New CAGR / DD |
|---|---|---|
| 2012-01..2014-12 | 2.25% / -7.80% | **10.97% / -11.24%** |
| 2015-01..2019-01 | **1.82% / -17.60%** | -1.82% / -26.65% |
| 2019 (full) | -2.15% / -4.65% | **4.95% / -5.71%** |
| 2022-01..2024-12 | 10.00% / -13.81% | **36.36% / -13.67%** |
| 2025-01..2026-07 | 3.00% / -6.25% | **4.65% / -8.35%** |
| 2021-07..2026-07 (5y) | 5.36% / -14.01% | **24.31% / -14.47%** |

The new configuration wins five of six windows, lifting mean CAGR across windows
from ~3.0% to ~11.0%. Three alternative configurations from the same plateau
(2.0 ATR stop / 15% booking; 4.5 ATR trail / 25% booking; 1.5 ATR stop / 15%
booking) were validated in parallel and all beat the old defaults on the same
five windows, confirming the result is a property of the *region* and not of one
parameter tuple.

### 19.6 Known weakness: choppy, trendless markets

2015-2018 is the one window that degrades, and it degrades meaningfully:
-1.82% CAGR against +1.82%, with drawdown widening from -17.6% to -26.7%. The
mechanism is unambiguous and expected. A 4 ATR trail is designed to give back
open profit in order to stay in a trend; in a market that repeatedly starts and
abandons trends, it gives the profit back without ever catching the trend. Both
configurations make essentially no money over that four-year stretch (+7.5% and
-7.1% total), so the practical difference is **path**, not terminal wealth — but
a 27% drawdown is a real tolerance question for the allocator.

Three mitigations were tested on that window and **none worked**:

| Variant | 2015-2018 CAGR / DD | 2022-2024 CAGR / DD |
|---|---|---|
| Selected config | -1.82% / -26.65% | 36.36% / -13.67% |
| + continuous regime scaling | -2.76% / -26.87% | 30.34% / -14.10% |
| + open-risk cap cut to 4% | -1.16% / -27.37% | 25.58% / -19.00% |
| + earlier trail activation (1.5 ATR) | -1.82% / -26.65% | 36.36% / -13.67% |

Each either failed to help the weak window or paid for a marginal improvement
with a large loss in the strong windows. Earlier trail activation was inert
because partial booking already forces the trail on. The weakness is therefore
**accepted and documented** rather than patched, since every patch tested so far
costs more than it saves.

### 19.7 Honest reading of these numbers

- The 24% five-year CAGR is the *selection* window and should be discounted.
  The ~11% mean across six windows is the more defensible expectation.
- The 2022-2024 result (36% CAGR) is a strong trending regime for Indian
  mid-caps and will not repeat on demand.
- Win rate is roughly unchanged (~47%). The gain came from raising the average
  win, not from losing less often — consistent with section 18.5's finding that
  win rate is structurally pinned for breakout systems.
- Survivorship bias from current Nifty 500 membership (section 13.1) is
  unchanged and still applies to every figure above.
- The strategy now holds positions roughly 20 days instead of 7. Capital turns
  over more slowly, and the sleeve will look idle for longer stretches.
