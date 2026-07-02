# Swing-Trading Backtest (point-in-time)

Bulk-simulates this repo's swing-trading setup over history **without letting the
model see the future**. It reproduces the monthly watchlist refresh (~12×) and
the daily trade loop (~250 trading days/year) using only the data that existed on
each simulated day.

- **Start capital:** ₹5,00,000 (all cash, no positions on day 1 → it discovers and
  builds the book from scratch).
- **Goal:** +20% (₹6,00,000).

---

## Why this is a *mechanical* replica (read this first)

The live setup makes its actual decisions through the **GitHub Copilot LLM** using
**live web + screener.in tools** (`swing_trading_copilot.py`, `watchlist_curator.py`
Stage-2). That path is **inherently not point-in-time** — an LLM with live tools
always sees *today's* prices, news and fundamentals, so it cannot be "rewound" to
1/1/2026 without leaking the future. The repo's own docs note the screener scraper
is realtime-only.

So this backtest faithfully replays the **same playbook the LLM is instructed to
follow** (`SWING_PLAYBOOK` + the monthly Stage-1 mechanical screen) as a
**deterministic Python engine** driven only by historical OHLCV. This is the only
way to get a leak-free, reproducible result. The qualitative LLM vetting
(fundamentals/news/forensics) is intentionally **not** modelled — see Caveats.

---

## How point-in-time integrity is guaranteed

1. **Data:** daily OHLCV from **yfinance** (`auto_adjust`), downloaded once for the
   whole universe + Nifty benchmark with a warmup buffer, cached to disk
   (`data_cache/`). yfinance is a *historical* source, so as-of cuts are exact.
2. **As-of slicing:** every indicator is computed from `data.as_of(symbol, day)`,
   which returns only rows dated `<= day`. Rolling-high "breakout" tests exclude
   the current bar.
3. **Execution order (no look-ahead):**
   - Entry signals are generated from **day _t_'s close** and **filled at day _t+1_'s
     OPEN**.
   - Exits (stop / target / trail / reversal / time-stop) are checked against the
     **current day's OHLC**, so they fill intraday (gap-downs fill at the open).

---

## What it replays

### Monthly (watchlist) — `watchlist.py`
Reuses the live curator's **Stage-1 mechanical screen** (`watchlist_curator.py`):
SMA-stack / RSI / ATR% / 1-3-6m returns / relative strength vs Nifty / liquidity /
volume-surge → composite score → industry-diversified top-N. Rebuilt on the first
trading day of every month, each time using only data available then.

### Daily (trading) — `strategy.py` + `engine.py`
Deterministic encoding of the playbook:
- **Entry filters:** price above rising 50/200-DMA stack, 20-EMA > 50-EMA, RSI 55–70,
  MACD bullish, liquidity & ATR% sane. **Setup** ∈ {Breakout (vol ≥ 1.2× & not
  extended), Pullback (holding 20-EMA, RSI > 50), Momentum}.
- **Sizing:** 2% risk rule → `shares = floor(equity·2% / (entry−stop))`, capped by a
  per-name concentration limit and available cash.
- **Stop:** `entry − 1.5×ATR`. Reward:risk must be ≥ 2:1 or the trade is skipped.
- **Exits:** +20% target → book 50% & move stop to breakeven, then **trail** the rest
  by 2×ATR; **reversal** (close < 50-DMA / < 20-EMA after partial); **time-stop**
  (≥30 days, or ≥70% of the window with < 2% progress).
- **Rotation:** freed cash flows to the best-ranked fresh candidate next session.

---

## Run it

```bash
# 1-year backtest ending today, Nifty 200, ₹5L start, 20% goal (defaults)
python -m backtesting.swing_trading.run_backtest

# Explicit window + larger universe (slower first download)
python -m backtesting.swing_trading.run_backtest \
    --start 2025-01-01 --end 2025-12-31 --universe nifty500

# Quick rerun from cache on a smaller universe
python -m backtesting.swing_trading.run_backtest --universe nifty100
```

Useful flags: `--capital`, `--goal-pct`, `--universe` (nifty50/100/200/500/midcap150…),
`--universe-file`, `--watchlist-size`, `--max-positions`, `--target-pct`,
`--max-holding-days`, `--risk-per-trade`, `--no-cache`, `--tag`.

The first run downloads prices (cached afterwards, so reruns are fast/offline).

---

## Outputs — `results/<tag>/`

| File | Contents |
|------|----------|
| `summary.txt` / `summary.json` | headline metrics vs the goal (+ full config) |
| `trades.csv` | every closed trade: entry/exit, P&L, holding days, exit reason |
| `equity_curve.csv` | daily equity / cash / deployed / open positions |
| `watchlists.json` | the point-in-time monthly watchlists (with per-name detail) |
| `open_positions.json` | positions still open at the end of the window |

Metrics: total return, CAGR, max drawdown, Sharpe (rf=0), win rate, profit factor,
avg win/loss, avg holding, avg exposure, and `goal_reached`.

---

## Module map

```
config.py        parameters (capital, goal, dates, universe, playbook thresholds)
data.py          PointInTimeData — bulk download, disk cache, as_of slicing, calendar
indicators.py    SMA/EMA/RSI/MACD/ATR/returns/rolling-high (backward-only)
watchlist.py     monthly mechanical watchlist (reuses live curator Stage-1)
strategy.py      entry signals + sizing + exit rules (the playbook, deterministically)
portfolio.py     cash, positions, trade log, equity curve, costs
engine.py        the daily loop (fill → manage → mark → rebalance → queue)
metrics.py       performance stats + summary rendering
run_backtest.py  CLI entrypoint
```

---

## Caveats (important)

- **No LLM qualitative layer.** Fundamentals, news, promoter pledging and forensic
  red-flags that the live LLM weighs are **not** modelled — only the mechanical
  rules. Real-world results would differ where that judgement matters.
- **Survivorship / membership bias.** NSE index constituent lists are *current*
  membership; using them for past dates slightly favours names that are in the index
  today. Use a point-in-time constituent file via `--universe-file` to remove this.
- **Costs/slippage** are approximated by a small per-side commission and open-fills;
  no market-impact model.
- yfinance prices are split/dividend-adjusted (`auto_adjust`), which is correct for
  return calc but means absolute ₹ levels are adjusted, not raw traded prices.

**For research/education only — NOT investment advice.**
