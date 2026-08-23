# GFS (Grandfather / Father / Son) — Backtest Harness

A leak-free, self-skeptical backtest for the multi-timeframe RSI strategy:

- **G**randfather — *monthly* candle RSI ≥ 60 → the stock is in a long-term uptrend.
- **F**ather — *weekly* candle RSI ≥ 60 → the medium-term trend agrees.
- **S**on — *daily* candle RSI ≤ 40 → a short-term dip inside that uptrend. **Entry.**
- **Exit** — daily RSI recovers to ~65, or price reaches prior resistance, or a stop
  is hit, or a time stop expires.

The thesis: a strong monthly/weekly structure will "pull up" a temporarily weak
daily chart. In academic terms this is **momentum** (Jegadeesh & Titman 1993)
combined with **short-term reversal** (Jegadeesh 1990, Lehmann 1990). Both are
real, documented anomalies. The specific 60/60/40 thresholds are folklore, and
this harness exists to find out whether they survive contact with data.

> **This package deliberately does not implement the live strategy.** No
> `strategies/gfs.py` wrapper exists yet, on purpose. Build the scanner only if
> the evidence below justifies it.

---

## Quick start

```bash
# Baseline run
python -m backtesting.gfs.run_backtest --start 2018-01-01 --end 2024-12-31

# The version you should actually believe: every leg ablated, plus a random-entry null
python -m backtesting.gfs.run_backtest --start 2018-01-01 --end 2024-12-31 \
    --universe nifty500 --ablations --monte-carlo 500

# Overfitting check: tune on train folds, report only test folds, deflate by trials
python -m backtesting.gfs.run_backtest --sweep --train-months 36 --test-months 12

# Is one threshold a plateau or a lucky spike?
python -m backtesting.gfs.run_backtest --stability g_rsi_min

# Size the survivorship / index-inclusion bias
python -m backtesting.gfs.run_backtest --universe nse_all
```

Artifacts (`summary.txt`, `trades.csv`, `equity_curve.csv`, `signals.csv`,
`ablations.json`, `sweep.json`) are written through `core.storage.save_artifacts`
unless you pass `--no-artifacts`.

---

## How look-ahead is prevented

This is the part worth auditing, because a multi-timeframe RSI strategy is
unusually easy to get wrong.

### 1. The higher-timeframe repainting trap

The obvious implementation — resample the full daily history to monthly, compute
RSI, read the last row — **leaks the future**. On 5 April, the "current" monthly
candle contains all of April. Reading its RSI on 5 April means reading the rest
of the month.

`indicators.resample_ohlc` uses `label="right", closed="right"`, so every candle
is keyed by its **period-end** date. Reindexing onto the daily calendar with
`method="ffill"` then resolves day *t* to the last candle whose period has
already *ended*. A partially elapsed period has no label yet, so it cannot be
seen. `htf_rsi_daily` returns `(rsi, closed_bar_count)`, and the bar count
enforces a warmup — no trading on a 3-observation monthly RSI.

### 2. `closed` vs `live` higher-timeframe candles

Two modes, both leak-free, with different realism trade-offs (`--htf-mode`):

| mode | what it shows | trade-off |
|---|---|---|
| `closed` *(default)* | only fully completed weekly/monthly candles | conservative; lags by up to a few days when the period-end label falls on a weekend |
| `live` | folds the in-progress candle in using **today's** daily close | matches what a trader actually sees on a Chartink/TradingView chart |

`live` is still causal: Wilder's RSI is recursive, so the state after the last
*closed* bar is a fixed `(avg_gain, avg_loss)` pair, and the in-progress bar is
folded in with a single O(1) update from data available today.

The exact invariant, asserted in `tests/test_gfs_leakage.py`:

> `live` on the last session of a period **equals** the value that period is
> stamped with once it closes, **equals** `closed` on the first session after the
> period label.

They do *not* agree mid-period, and `closed` genuinely lags across a weekend.
That is by design and always in the conservative direction.

### 3. Structural verification, not just inspection

The leakage tests do not read the code — they attack it:

- **Truncation invariance.** Panels built from history cut at *T* must match, row
  for row, panels built from the full history. Any future dependence breaks this.
- **Planted future shock.** A ±40% move is inserted *after* *T*. Nothing at or
  before *T* may change by a single float.
- **End-to-end append test.** The same check applied to the whole engine: appending
  future data must not change one day of the equity curve.
- **Hand-computed Wilder RSI.** Guards against the whole indicator layer drifting.

### 4. Execution ordering

Each simulated day, in this order:

1. Fill exits queued yesterday, at **today's open**.
2. Fill entries queued yesterday, at **today's open**.
3. Manage open positions against today's OHLC.
4. Record equity at **today's close**.
5. Scan for *tomorrow's* candidates using data up to today's close.

Consequences, all deliberately pessimistic:

- A signal at day *D*'s close never fills before *D+1*'s open.
- Price-level exits (stop, resistance) fill intrabar; **indicator** exits (RSI ≥ 65)
  and time stops queue for the next open, because you cannot know the closing RSI
  until the close (`--no-indicator-exit-delay` to disable, for comparison only).
- If a stop and a target could both have been hit in one bar, **the stop wins**.
- A gap through the stop fills at the open, not the stop price.
- Stops are re-derived from the *actual* fill price, so an overnight gap cannot
  silently shrink the sized risk.

---

## The falsifiability layer

A backtest that can only say "yes" is worthless. Four independent challenges are
wired into the same code path so they cannot be skipped:

| challenge | question it answers |
|---|---|
| **Buy & hold** | Does this beat simply owning the index? |
| **Forward-return study** | Ignoring the portfolio entirely, do stocks meeting the GFS condition outperform over 5/10/21/63 days? |
| **Random-entry Monte Carlo** | Matching trade count and holding periods but randomising *which* stock and *when*, where does the real strategy rank? |
| **Ablations** | Remove exactly one leg. If results don't change, that leg is decoration. |

Two notes on statistical honesty:

- The forward-return t-statistic is computed on **day-averaged** returns. Signals
  fired on the same day are heavily correlated (they share market direction);
  treating them as independent observations inflates *t* enormously and is the
  single most common way to manufacture a fake edge.
- The forward-return study looks *forward* on purpose. That is legitimate
  measurement after the fact — it never feeds a trading decision.

### Overfitting control (`--sweep`)

Walk-forward with **purge + embargo**: parameters are chosen on each training
fold and reported only on the untouched test fold. The embargo is 90 days,
deliberately wider than the 60-day time stop, so no position opened in training
can still be open when the test window starts. Selection uses Sharpe, not CAGR;
configurations with fewer than 10 trades score `-inf`. The **Deflated Sharpe
Ratio** is fed the full trial count, which is what makes "best of 324" honest.

`--stability <param>` prints a response curve instead of a winner. Read it as a
shape: a broad plateau suggests a real effect, an isolated spike is curve-fitting
even when it is the best number on the page.

---

## Known biases — read before quoting any number

1. **Survivorship & index-inclusion bias (largest).** The universe is *today's*
   index membership. Companies delisted or merged during the window are absent
   from every variant, and index membership today is partly a *consequence* of
   performance during the test window. Every index-based number here is an
   **optimistic upper bound**. `--universe nse_all` uses the full NSE equity list,
   which removes the index-inclusion circularity (though not survivorship) and is
   the more defensible figure. `universe_bias_note()` prints this caveat with
   every result so it cannot be quietly dropped.
2. **Sector labels are present-day.** `apply_sector_map` back-fills industry from
   the current nifty500 file. Far less distorting than membership, but not
   point-in-time.
3. **The top-down funnel's qualitative leg is not modelled.** "Check global
   markets and news" cannot be made point-in-time — an LLM with live tools always
   sees today. It is replaced with quantifiable proxies (benchmark above SMA200,
   market breadth, sector relative strength). The real workflow's judgement layer
   is therefore *not* validated here, in either direction.
4. **Costs are modelled, impact is not.** 0.05%/side commission plus 15 bps
   slippage. No market-impact model; the liquidity filter (median 20-day turnover)
   is the only capacity control.
5. **Crowding.** The GFS screen is publicly circulated as a Chartink screener. A
   backtest cannot see the crowding that public knowledge creates.

---

## Findings (2018-01-02 → 2024-12-31)

Reproduce with `--ablations --monte-carlo 500` on each universe.

### Nifty 500

| | strategy | benchmark |
|---|---|---|
| CAGR | **+11.7%** | +12.4% |
| Max drawdown | **−14.5%** | −38.4% |
| Sharpe | 1.04 | — |
| Avg exposure | **30.3%** | 100% |
| Trades / win rate | 218 / 46.8% | — |
| Expectancy | +0.267 R (+3.25%/trade) | — |

Random-entry Monte Carlo: **99.6th percentile — passes.** Strategy average trade
+3.25% vs +1.43% for random entries in the same universe over the same holding
periods. The entries carry information.

Forward-return study: **fails.** |t| < 2 at every horizon, and the raw edge is
*negative* at 5/10/21 days (−0.20%, −0.41%, −0.47%), turning mildly positive only
at 63 days (+0.83%, t = 1.45).

### Nifty 100

| | strategy | benchmark |
|---|---|---|
| CAGR | **+2.8%** | +12.4% |
| Max drawdown | −10.7% | −38.4% |
| Avg exposure | 20.1% | 100% |

Monte Carlo: **52.4th percentile — fails.** Indistinguishable from random.
Forward-return edge ≈ 0 at every horizon.

### What the ablations say (Nifty 500)

| variant | CAGR | MaxDD | Sharpe | Trades | Win% | ExpR |
|---|---|---|---|---|---|---|
| baseline | 11.7% | −14.4% | 1.04 | 218 | 46.8% | 0.27 |
| no_grandfather_father | 12.2% | −28.3% | 0.82 | 482 | 43.8% | 0.16 |
| no_son_dip | 6.1% | −27.7% | 0.44 | 2094 | 51.8% | 0.01 |
| no_sector_gate | 14.0% | −34.4% | 0.97 | 419 | 44.6% | 0.19 |
| no_regime_gate | 10.0% | −25.9% | 0.79 | 255 | 44.3% | 0.20 |
| random_ranking | 12.6% | −15.7% | 1.13 | 218 | 49.1% | 0.30 |
| tight_pct_stop | 10.5% | −11.4% | 1.13 | 283 | 30.4% | 0.57 |
| scale_out_and_trail | 13.0% | −16.3% | 1.14 | 277 | 62.5% | 0.84 |
| risk_based_sizing | 14.2% | −17.5% | 1.16 | 211 | 47.4% | 0.29 |
| live_htf_candles | 5.8% | −10.1% | 0.92 | 94 | 48.9% | 0.36 |

Five conclusions, each of which contradicts some part of the strategy as pitched:

1. **The G+F filter is a risk control, not a return generator.** Removing it
   *raises* CAGR slightly (12.2% vs 11.7%) while nearly doubling drawdown (−28.3%
   vs −14.4%). Its value is in what it avoids, not what it finds. Marketing GFS as
   a way to find winners is backwards.
2. **The daily dip is the load-bearing leg.** Without it, 2,094 trades earn an
   expectancy of 0.01 R — statistically nothing. The dip is what concentrates a
   diffuse signal into something tradable.
3. **The proposed 3–5% fixed stop is inside the noise.** 48% of eventual winners
   first fell more than 3%, and 24.5% fell more than 5%. The `tight_pct_stop`
   ablation confirms it: win rate collapses from 46.8% to 30.4%. Meanwhile the
   2×ATR stop sits comfortably outside the noise — median winner MAE is −0.41 R,
   and only 8.8% of winners came within 80% of the stop.
4. **Ranking adds nothing.** `random_ranking` matches the baseline. Any effort
   spent scoring candidates is currently wasted.
5. **Realism costs half the return.** `live_htf_candles` — using the in-progress
   monthly/weekly candle a real trader sees on a chart — drops CAGR from 11.7% to
   5.8%. Published GFS backtests almost certainly use closed candles without
   saying so.

### Honest verdict

On the Nifty 500 the strategy **matches the index return using a third of the
exposure and 40% of the drawdown**, and its entries beat a random-entry null at
the 99.6th percentile. That is a real risk-adjusted result and not nothing.

But it **does not beat buy-and-hold on return**, it **collapses on large caps**,
the **G+F filter does not do what it is advertised to do**, and the
portfolio-free forward-return study — the cleanest test of the signal itself —
**shows no significant edge at any horizon**. The Monte Carlo pass is therefore
plausibly attributable to the gates, the ATR stop and the exit logic rather than
to the GFS condition.

Add the survivorship and index-inclusion bias on top, and the defensible summary
is: *a decent risk-managed swing framework whose distinctive ingredient is the
least useful part of it.*

### If you pursue this anyway

The ablations point at a better strategy than the one described:

- Replace the RSI-65 target with `scale_out_and_trail` (ExpR 0.84 vs 0.27,
  win rate 62.5%).
- Use `risk_based_sizing` (CAGR 14.2%, Sharpe 1.16).
- Keep the ATR stop; discard the 3–5% fixed stop.
- Keep G+F for drawdown control, but stop believing it selects winners.
- Fix the 30% exposure problem — cash drag is most of the gap to buy-and-hold.

All of that is *suggested by* an in-sample ablation table and is therefore a
hypothesis, not a result. Run `--sweep` and `--universe nse_all` before
committing capital.

---

## Module map

| file | role |
|---|---|
| `config.py` | every knob, with `validate()` |
| `indicators.py` | Wilder RSI/ATR + the leak-free HTF projection — **the trust anchor** |
| `panels.py` | vectorized causal pre-computation; `PANEL_COLUMNS` is the engine contract |
| `strategy.py` | entry qualification, stops, exits, sizing |
| `portfolio.py` | cash, positions, costs, R-multiples, MAE/MFE |
| `engine.py` | the daily loop and its ordering |
| `metrics.py` | performance, excursions, exit attribution |
| `baselines.py` | buy & hold, forward-return study, random-entry null, ablations |
| `sweep.py` | walk-forward sweep, DSR, parameter-stability curves |
| `universe.py` | NSE index / all-equity loading, sector map, bias note |
| `service.py` | orchestration; caches the expensive indicator pass across variants |
| `run_backtest.py` | CLI |

Tests live in `tests/test_gfs_leakage.py`, `tests/test_gfs_mechanics.py` and
`tests/test_gfs_engine.py` (62 tests). The leakage suite is the one that matters;
run it before trusting any change to `indicators.py` or `panels.py`.

### A note on the panel cache

`build_panels` accepts a cache keyed by `base_panel_key(cfg)`. Thresholds like
`g_rsi_min` only re-evaluate a boolean, whereas RSI periods change the expensive
indicator pass — so an 11-variant ablation or a 324-configuration sweep pays for
the indicator pass once. `test_base_panel_cache_cannot_change_results` proves the
cache is a pure optimisation, because a stale cache would silently corrupt every
sweep result while every single-config test still passed.
