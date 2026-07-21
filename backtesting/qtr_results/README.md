# Quarterly-Results Backtest (point-in-time)

Bulk-simulates this repo's **quarterly-results momentum** strategy
(`qtr_results/`, strategy id `qtr_results`) over ~1 year of history **without
letting the model see the future**. It replays, day by day, the same playbook the
live strategy follows — discover a fresh result → verify the numbers → buy with a
PE-rerating target and a trailing stop → track the pick to exit — but every
decision uses only the data that existed on each simulated day.

- **Start capital:** ₹5,00,000 (all cash, no positions on day 1).
- **Goal:** +20% (₹6,00,000).

It is built as a sibling of `backtesting/swing_trading/` and reuses that setup's
point-in-time price store and metrics, plus the live `qtr_results` analysis/target
maths, so the two backtests share the same conventions.

---

## The strategy it replays (read this first)

The live `qtr_results` run each day:

1. **Discovers** NSE companies that just declared quarterly results (Copilot CLI
   web-grounding + the NSE corporate-filings feed).
2. **Verifies** each on screener.in — computes QoQ/YoY growth of **sales, net
   profit, EPS** and the **operating-margin** delta, a composite *strength score*,
   and gates on "strong" (YoY net-profit ≥ 20%, plus EPS-YoY ≥ 15% and QoQ-profit
   ≥ 5% when available).
3. **Targets** by **PE re-rating** — hold the market's multiple constant against
   the freshly-grown TTM EPS (`fair = P/E × new TTM EPS`), clamp the implied
   upside into the **10–20%** band (static-tier fallback when EPS/PE is missing),
   and set a **trailing stop at target ÷ 2**.
4. **Tracks** each pick in a ledger to its exit: **target** booked, **trailing
   stop** (ratcheted off the highest price seen), or a **3-week time-stop**.

The backtest reproduces steps 2–4 mechanically and replaces the live discovery
(step 1) with a leak-free historical equivalent — see below.

---

## Why this is a *mechanical* replica

The live discovery + verification path is **inherently not point-in-time**: the
NSE feed and the Copilot web search only ever return *today's* declarations, and
the screener scraper is realtime-only. Those cannot be "rewound" to a past date
without leaking the future.

So this backtest drives the **same deterministic rules** (`qtr_results.analysis`
selection + `qtr_results.targets` PE-rerating + the ledger exit logic) from
**historical data**, and models discovery from the as-reported quarterly history.
The qualitative Copilot layer (news, forensics, promoter checks) is intentionally
**not** modelled — see Caveats.

---

## How point-in-time integrity is guaranteed

1. **Prices** — daily OHLCV from **yfinance** (`auto_adjust`), downloaded once for
   the universe + Nifty benchmark with a warmup buffer and cached to disk. Served
   as `data.as_of(symbol, day)` slices (rows dated `<= day`). This is the swing
   backtest's `PointInTimeData`, reused verbatim.
2. **Fundamentals** — quarterly financials scraped **once** per symbol from
   **screener.in** (the live strategy's own source) and cached. The scraped values
   are *as-reported historicals* that do not change, so a result event for quarter
   *Q* consults **only the quarter columns up to and including Q** — never a later
   quarter. Screener's live "Current Price"/"Stock P/E" are **never** used.
3. **Discovery timing** — a quarter ending on `quarter_end` is treated as declared
   `--reporting-lag-days` (default **45**) later, i.e. the realistic Indian filing
   lag. The result is recognised on the first trading session on/after that date.
4. **Execution order (no look-ahead)** — a result recognised on day *t* is
   **FILLED at day *t+1*'s OPEN**, so **every pick is priced at the historical
   price at that point in time, never the current price**. Exits are checked
   against the current day's OHLC (gaps fill at the open). The trailing stop for a
   day is measured from the highest price through the *previous* day only.

---

## What it replays

### Discovery (`analysis.enumerate_events`)
Every parseable quarter column with ≥ 4 prior quarters becomes a candidate result
event, dated `quarter_end + reporting_lag_days`.

### Verification (`analysis.analyze_event`) — reuses `qtr_results.analysis`
YoY/QoQ growth of sales/net-profit/EPS, margin delta, composite strength score and
the "strong" gate — all computed with the live helpers, pinned to the declared
quarter. The PE for re-rating is derived from the **historical entry price** and
the **pre-result trailing EPS**, so the target is leak-free.

### Targets (`qtr_results.targets.build_target_plan`) — reused directly
PE-rerating upside clamped to 10–20% (static-tier fallback), trailing stop = target ÷ 2.

### Sizing (`strategy.size_position`)
The live strategy is a signal/ledger tracker with **no** position sizing, so the
backtest adds the swing setup's **2%-risk** sizer (per-share risk = the initial
trailing-stop distance), capped by a per-name concentration limit and cash.

### Exits (`strategy.evaluate_exit`)
An OHLC-aware version of `qtr_results.ledger`: trailing stop (ratcheted off the
high), PE-rerating target, and the 3-week time-stop.

---

## Run it

```bash
# 1-year backtest ending today, Nifty 200, ₹5L start, 20% goal (defaults)
python -m backtesting.qtr_results.run_backtest

# Explicit window + bigger universe (slower first scrape/download)
python -m backtesting.qtr_results.run_backtest \
    --start 2025-01-01 --end 2025-12-31 --universe nifty500

# Quick rerun from cache on a small universe
python -m backtesting.qtr_results.run_backtest --universe nifty50 --max-symbols 30
```

Useful flags: `--capital`, `--goal-pct`, `--universe`, `--universe-file`,
`--max-symbols`, `--reporting-lag-days`, `--max-new-per-day`, `--max-positions`,
`--max-holding-days`, `--risk-per-trade`, `--min-yoy-profit-growth`,
`--max-debt-to-equity`, `--min-roce`, `--quality-on-financials`,
`--regime-filter`, `--regime-ma-period`, `--target-max-pct`, `--max-position-pct`,
`--no-real-dates`, `--real-dates-only`, `--anticipation-mode`,
`--anticipation-lead-days`, `--anticipation-min-rs`, `--anticipation-rs-lookback`,
`--no-cache`, `--tag`.

> **B8 — balance-sheet quality (leverage) filter.** The v3 backtest's losing
> trades clustered in highly-levered companies: a "strong result" in a debt-heavy
> business whipsawed out of the ATR trailing stop far more often than the same
> beat in a clean-balance-sheet compounder (winners' median debt/equity ≈ 0.04 vs
> ≈ 0.25 for losers). Gating on point-in-time **debt/equity ≤ 0.05**
> (`Borrowings ÷ (Equity Capital + Reserves)` from the latest annual balance
> sheet on/before the declared quarter; banks/NBFCs exempt) lifted the 1-year
> Nifty-200 backtest from **+2.3% → +11.7%**, win rate **40% → 59%**, profit
> factor **1.13 → 2.17**, and max drawdown **−6.5% → −3.3%** — cutting
> trailing-stop losers from 40 to 16 while *growing* target wins. It is the new
> default (`config.max_debt_to_equity = 0.05`); pass a large value to disable.
> The edge **validated out-of-sample**: on an independent Nifty-500 / 3-year run
> it ~3×'d the return (**+4.2% → +12.5%**, PF 1.05 → 1.24).

> **B9 — market-regime throttle (opt-in).** B1–B8 fix pick *quality* but not
> portfolio *drawdown*: earnings-momentum longs take correlated hits in a broad
> correction (the Nifty-500 / 3-year run drew down **~19%** regardless of the debt
> filter). `--regime-filter` stops *opening* new positions while the benchmark is
> below its `--regime-ma-period` SMA (default **100**), only deploying fresh risk
> in an up-market (existing positions keep running their stops/targets; point-in-
> time on benchmark prices ≤ signal day). On Nifty-500 / 3-year it nearly **halved
> max drawdown (−18.8% → −10.6%)** while slightly *raising* return
> (**+12.5% → +12.9%**), Sharpe (0.46 → 0.55) and PF (1.24 → 1.33). It is
> **insurance**, so it is **off by default**: in a benign uptrend (Nifty-200 /
> 1-year) it costs return (+11.7% → +6.1%) by sitting out shallow dips. Enable it
> for broad/volatile universes or when drawdown control is the priority.

> **B10 — pre-declaration "anticipation" mode (opt-in, `--anticipation-mode`).**
> Indian equities frequently front-run a good result (informed flow / leaks), so
> instead of buying the *reaction* this mode buys the *anticipation*: it enters
> `--anticipation-lead-days` (default **10**) trading sessions **before** the real
> declaration when the stock shows a pre-result run-up — relative strength vs the
> benchmark over `--anticipation-rs-lookback` (20) sessions ≥ `--anticipation-min-rs`
> (default **0.12** = +12%). The pre-result position is *held through* the window
> (no trailing-stop knock-out); on the declaration day the result is graded and a
> **strong + low-debt** result rides on (target + trailing stop re-anchored to the
> post-result price) while a **weak** result is dumped at the next open to dodge
> the reversal — often still banking the run-up. It requires **real** declaration
> dates (needs the exact day), so it is implicitly `--real-dates-only`; the only
> real-dated window today is **calendar 2024** (NSE's per-symbol archive ends at
> the Dec-2024 quarter). On that window — where every *non*-anticipation config
> loses money (standard **−6.6%**, standard+regime **−11.8%**) — anticipation with
> `--regime-filter` + the debt gate turned it **positive: +14.1%, win 57%, PF 1.87,
> maxDD −9.2%** (47 trades; all entries verified to precede their declaration
> date). The RS threshold shows a robust positive plateau across **0.11–0.14**
> (PF 1.3–1.9, peak 0.12); it collapses if too loose (noise) or too tight (too few
> names), and needs the regime + debt gates to work — so it is **off by default**.
> Caveat: validated on a single ~1-year window (~47 trades); a longer test needs
> an NSE-XBRL historical-financials backfill to extend fundamentals before 2023.

The first run scrapes screener.in (rate-limited, ~2 s/symbol) and downloads
prices; both are cached, so reruns are fast and offline.

---

## Outputs — `results/<tag>/`

| File | Contents |
|------|----------|
| `summary.txt` / `summary.json` | headline metrics vs the goal (+ full config, exit-reason mix) |
| `trades.csv` | every closed trade: quarter, method, strength, entry/exit, P&L, holding days, exit reason |
| `equity_curve.csv` | daily equity / cash / deployed / open positions |
| `events.csv` | every discovered result event and its point-in-time verdict (strong?, growth numbers) |
| `open_positions.json` | positions still open at the end of the window |

Metrics: total return, CAGR, max drawdown, Sharpe (rf=0), win rate, profit factor,
avg win/loss, avg holding, avg exposure, and `goal_reached`.

---

## Module map

```
config.py        parameters (capital, goal, window, universe, lag, live thresholds)
data.py          PointInTimeData (reused, prices) + FundamentalsStore (screener cache)
analysis.py      point-in-time per-quarter verification (reuses qtr_results.analysis)
strategy.py      2%-risk sizing + OHLC-aware exits (ledger semantics)
portfolio.py     cash, positions, trade log, equity curve, costs
engine.py        the daily loop (fill → manage → mark → discover → queue)
metrics.py       performance stats (reused) + summary rendering
run_backtest.py  CLI entrypoint
```

---

## Caveats (important)

- **No LLM qualitative layer.** News, forensics, promoter pledging and the
  liquidity/mainboard judgement the live Copilot applies are **not** modelled —
  only the mechanical numbers. Real results would differ where that matters.
- **Declaration dates — now real (with fallback).** By default the backtest
  times each event to the **actual NSE announcement date** (`broadCastDate` from
  the corporates-financial-results feed, matched per quarter and cached to
  disk). Where NSE can't resolve a symbol/quarter it falls back to the old
  estimate `quarter-end + reporting_lag` (a deterministic per-symbol lag). Pass
  `--no-real-dates` to force the estimate everywhere. Entries always fill at the
  historical open on/after the declaration date, so a post-close announcement is
  bought the next session — genuinely point-in-time either way. The engine log
  and `events.csv` (`decl_date_real` column) report how many events used a real
  date vs the fallback. Note: NSE's per-symbol archive currently returns history
  through the **Dec-2024** quarter, so events after that fall back to the estimate.
- **Position sizing is an overlay.** The live strategy tracks signals without
  sizing; the 2%-risk sizer here is the backtest's addition to turn it into a
  capital simulation.
- **Survivorship / membership bias.** NSE index constituent lists are *current*
  membership. Use a point-in-time constituent file via `--universe-file` to remove
  it. Screener history is also the current snapshot (restatements are ignored).
- **Costs/slippage** are a small per-side commission with open-fills; no
  market-impact model. yfinance prices are split/dividend-adjusted.

**For research/education only — NOT investment advice.**
