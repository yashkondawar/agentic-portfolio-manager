# qtr_results backtest dossier

A one-command Excel workbook that reports the `qtr_results` strategy the same
way the reference `dossier_*.xlsx` files report the 52-week-high strategy: nine
sheets, the same four headline columns, the same tax treatment.

```bash
uv run python -m backtesting.qtr_results.build_dossier
```

Writes `backtesting/qtr_results/results/qtr_results_dossier.xlsx`.

## What it produces

| Sheet | Contents |
| --- | --- |
| `Summary` | Headline metrics in four columns — net of cost+tax, before tax, before cost & tax, NIFTY 50 — plus the config that produced them and the caveat notes |
| `Equity_Curve` | Daily portfolio value on all three cost bases, alongside NIFTY 50, NIFTY 500 and an equal-weight universe, all rebased to the starting capital |
| `Positions` | One row per closed round trip: entry/exit dates and prices, holding days, P&L gross and net, and the exit reason |
| `Trades` | One row per fill (both legs), with quantity, price, cost, cash after, and the realised short/long-term gain tagged on the sell |
| `Yearly_Returns` | Calendar-year returns vs all three benchmarks; partial years marked `*` |
| `Rolling_3Y` / `Rolling_5Y` | Empty — see [Known limits](#known-limits) |
| `Daily_Returns_Portfolio` | Daily return series behind the ratio metrics |
| `Tax_Ledger` | Per-financial-year capital-gains working: short/long-term gains, set-off, carry-forward, and tax due |

## Useful flags

```bash
--start 2024-04-01        # default; see "Why the window starts there"
--end 2026-08-28          # defaults to the last bar in the store
--capital 500000
--universe nifty500       # or nifty50 / a symbols file
--max-symbols 100         # trim for a fast smoke run
--out path\to\file.xlsx
--no-sync-benchmark       # skip the ^CRSLDX download if already local
--no-cache
```

## How it is wired

`build_dossier.py` is a thin CLI. It runs the ordinary `qtr_results` backtest
engine, then hands the resulting portfolio to `dossier.py`, which computes the
metrics and writes the workbook. Nothing about the strategy logic lives here —
if the engine changes, the dossier follows automatically.

Two supporting changes make this possible:

- **`portfolio.py` journals every fill.** `Portfolio.fills` is an ordered list
  of `Fill` records; `ClosedTrade` also carries `gross_pnl` and `costs`. The
  `Trades` sheet is a direct rendering of that journal.
- **`config.py` exposes `live_mirror_config()`.** The backtest defaults had
  drifted from the live strategy (risk per trade 2% vs 4%, different target
  tiers). This preset reads the tunables straight from the live
  `qtr_results.config` so the dossier describes the system actually in
  production, not a stale copy of it. Pass overrides as keyword arguments; an
  unknown name raises rather than being silently ignored.

## Costs and taxes

Two separate deductions, applied once each:

1. **Trading friction** — `COMMISSION_PCT`, 0.20% per side, charged inside the
   engine. The live config documents this as an all-in proxy for STT, exchange
   charges, and slippage. The engine's reported P&L is already net of it.
2. **Capital-gains tax** — computed by `dossier.classify_trades` and
   `build_tax_ledger`, reusing `backtesting/gfs/taxes.py` for the rates, the
   23-Jul-2024 rate change, the ₹1.25L long-term exemption, and loss
   carry-forward. Tax is charged against the curve at each 31 March.

The statutory per-leg charge stack in `gfs/taxes.py` is deliberately **not**
applied: friction (1) already includes STT and charges, so running both would
bill the same costs twice.

The three portfolio columns are therefore:

```
before_cost_and_tax[t] = equity[t] + cumulative costs paid up to t
before_tax[t]          = equity[t]
net[t]                 = equity[t] - tax for every FY ended on or before t
```

## Known limits

Read these before quoting a number from the workbook.

**The window starts 2024-04-01 because of data depth, not choice.** The
fundamentals cache holds at most 13 quarters per symbol, the earliest being
Mar 2023. The strategy screens on year-on-year growth, so it needs a year-ago
comparable — the first gradeable quarter is Mar 2024, declared from late April.
Backtesting from an earlier date does not add trades, it only parks capital in
cash and drags the CAGR down for a reason that has nothing to do with the
strategy. An earlier start is available via `--start` but is not meaningful
until deeper fundamentals are sourced.

**`Rolling_3Y` and `Rolling_5Y` are empty by construction.** The tradeable
history is roughly 2.4 years, so no three- or five-year window fits. The sheets
are kept, with an in-sheet explanation, so the file structure matches the
reference workbook exactly.

**Long-term capital-gains columns are structurally zero.** `MAX_HOLDING_DAYS`
is 90, so no position can reach the 365-day long-term threshold. The columns
are present for structural parity and will populate if that cap is ever raised.

**The LLM conviction gate is not represented.** The live strategy runs a
Tier-2 language-model review over the mechanically screened candidates. That
judgement cannot be replayed historically, so the backtest reflects the
mechanical screen alone. Treat the results as the floor the conviction layer
builds on, not as a simulation of the full live system.
