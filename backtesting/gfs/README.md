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

> **Read order note.** The "Honest verdict" section reports the strategy *as
> taught* (2×ATR stop, RSI-65 exit, 60-day time stop) and finds no edge. That
> section is still accurate for those settings. **It is then partially overturned
> by the conviction study further down**, which removes the time stop, widens the
> stop, and adds a resistance-headroom entry filter — and does reach the 70%+ win
> rate and index-beating return. The final section, **"Making it tradeable"**,
> supersedes both on the *level* of returns: it adds the Indian tax stack and,
> more importantly, stops assuming idle cash earns nothing. Quote that section's
> numbers, not the earlier ones — and quote its `nse_all` caveat with them, because
> on the full listed universe the post-tax edge does not survive. The last section,
> **"Loosening the filters"**, adds the single dial worth changing (`--s-rsi 43`)
> and one caveat that outranks the rest: split at 2019, the excess return is
> **+4.08% in 2019-2026 and −0.04% in 2013-2019**.

> **See also [`EXPLORATIONS.md`](EXPLORATIONS.md)** — the research log. This file
> documents what the harness *is*; that one documents *how we got here*, in the
> order it happened, including every rejected idea and why. If you are about to
> try something on this strategy, check there first: roughly two thirds of the
> ideas tested did not work, and several of them were good ideas.

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

# The full results workbook, net of brokerage AND capital-gains tax
python -m backtesting.gfs.run_dossier --start 2016-01-01 --capital 10000000 \
    --out reports\gfs_dossier.xlsx
```

Artifacts (`summary.txt`, `trades.csv`, `equity_curve.csv`, `signals.csv`,
`ablations.json`, `sweep.json`) are written through `core.storage.save_artifacts`
unless you pass `--no-artifacts`.

The dossier is a separate, self-contained deliverable — a nine-sheet Excel
workbook covering the equity curve, every fill, per-year and rolling returns, and
a capital-gains ledger, with every headline metric reported three times (raw,
after costs, after costs **and** tax). It reads the live configuration straight
out of `gfs/config.py`, so it always describes the strategy actually being
traded. See [DOSSIER.md](DOSSIER.md).

---

## The top-down funnel, and how much of it is real

The strategy is taught as a four-level funnel. Three levels are quantified here;
one is not, and pretending otherwise would be the easiest way to overstate the
result.

| Level | Modelled? | Implementation |
|---|---|---|
| 🛰️ **Satellite** — world markets, news, sentiment | **No** | Not derivable from Indian price data. See "Known biases" below. |
| 🚁 **Helicopter** — Indian market direction | **Yes** | `build_regime_panel`: benchmark above its own SMA(200), plus optional breadth (share of the universe above SMA200). No entries on a closed regime. |
| ✈️ **Aerial** — sector strength | **Yes** | `build_sector_panel`: equal-weighted sector indices, 63-session relative strength, trade only the top `sector_top_n` (default 5). |
| 🔬 **Microscopic** — the stock | **Yes** | G/F/S conditions, liquidity and ATR filters, composite ranking, `max_per_sector` concentration cap. |

The gates are not decorative. Over the 2021–2026 run they rejected candidates
like this:

```
sector_weak      1,210   <- aerial
regime_closed      365   <- helicopter
capacity           279   <- 8-position limit
sector_cap         170   <- 2-per-sector cap
```

The regime gate was open on only 74.9% of sessions. Each layer can be switched
off individually (`--no-regime-filter`, `--no-sector-filter`) and each has a
matching ablation, which is how the harness establishes that these gates — not
the G/F/S condition — are carrying the result.

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
2. **Sector labels are present-day, and absent entirely on `nse_all`.**
   `apply_sector_map` back-fills industry from the current nifty500 file. Far
   less distorting than membership, but not point-in-time. More importantly, it
   covers *none* of the ~2,300 names in `nse_all`, so that universe has no sector
   gate and no per-sector cap. This is not cosmetic: an earlier version of this
   harness counted every unlabelled stock into a single "Unknown" bucket, so a
   cap of 2 held the book to two positions instead of eight and made `nse_all`
   look like it returned 2.8% CAGR when the correct figure is 12.0%. Unknown
   sectors are now uncapped, and `universe_bias_note` says so in the output.
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

### Full NSE equity list (`--universe nse_all`) — the survivorship check

| | strategy | benchmark |
|---|---|---|
| CAGR | +12.0% | +12.4% |
| Max drawdown | −31.5% | −38.4% |
| Sharpe | 0.77 | — |

Monte Carlo: **80.4th percentile — fails.** Forward-return edge is **negative and
significant** at short horizons: −0.31% at 5d (t = −2.08) and −0.45% at 10d
(t = −2.18).

**How large is the index-inclusion bias?** Not as large as it first appears, and
getting this right required fixing a bug (see below). `nse_all` has *no* industry
labels, so its sector gate and per-sector cap are inert. Comparing it against a
default Nifty 500 run therefore compares two different strategies. Matching the
settings — Nifty 500 with `--no-sector-filter --max-per-sector 0` — gives the
honest comparison:

| universe, sector control off | CAGR | MaxDD | Sharpe | exposure |
|---|---|---|---|---|
| Nifty 500 | 12.47% | −30.2% | 0.84 | 60.2% |
| NSE all | 12.0% | −31.5% | 0.77 | ~63% |

So index-inclusion bias is worth roughly **0.5 pp of CAGR here, not 9 pp**.
Survivorship bias (delisted companies missing from both) is still unmeasured and
still favours the strategy.

That same table exposes something more interesting: turning sector control *on*
moves the Nifty 500 run from 12.5% CAGR / −30.2% DD to 11.7% CAGR / −14.4% DD.
**The sector gate and position cap are the single biggest risk lever in the whole
system** — worth roughly half the drawdown for 0.8 pp of return. They have
nothing to do with G, F or S.

### Overfitting check (`--sweep`, 324 configurations, 3 folds)

| test window | CAGR | Sharpe | MaxDD | trades |
|---|---|---|---|---|
| 2021-04 → 2022-04 | −2.60% | −0.43 | −8.5% | 22 |
| 2022-04 → 2023-04 | −6.97% | −0.40 | −15.3% | 71 |
| 2023-04 → 2024-04 | +62.01% | 3.15 | −9.2% | 65 |

**Deflated Sharpe Ratio: 0.0.** After accounting for 324 trials, the
out-of-sample performance is indistinguishable from the luckiest cell of the
grid. Two of three test folds lose money; one fold carries everything.

Parameter stability across folds is the most damning single number in this
document:

| parameter | modal value | fold agreement |
|---|---|---|
| `atr_stop_mult` | 1.5 | **100%** |
| `exit_rsi` | 70 | 66.7% |
| `s_rsi_entry` | 45 | 66.7% |
| `f_rsi_min` | 65 | **33.3%** ← unstable |
| `g_rsi_min` | 65 | **33.3%** ← unstable |

The two thresholds that *define* GFS — the "60" in Grandfather and Father — pick
a different optimum in every fold. A parameter with no stable value is not a
parameter, it is noise. The only perfectly stable choice is the ATR stop
multiplier, i.e. the risk control.

### Out-of-sample-ish rerun: the most recent 5 years (2021-08-23 → 2026-08-21)

The findings above use 2018–2024. Rerunning the same default configuration on
the most recent five years — a window that includes 2025 and 2026, largely
unseen when the parameters above were being looked at — reproduces the pattern
rather than rescuing it:

```
Equity          Rs 500,000 -> Rs 672,885     (+34.58%)
CAGR                        +6.13%     vs benchmark +8.02%   (excess -1.89%)
Max drawdown               -18.29%     (459 sessions under water)
Sharpe / Sortino        0.57 / 0.82
Avg exposure                34.2%

Closed trades                 175
Win rate                   42.29%
Profit factor                1.32
Avg win / avg loss    +13.99% / -7.19%   (payoff 1.95)
Expectancy            +0.109 R  (+1.77%/trade)
Holding avg/median      28.9 / 27.0 days
```

Exit attribution:

| exit | n | % of trades | % of P&L | avg |
|---|---|---|---|---|
| stop | 92 | 52.6% | −303.1% | −7.62% |
| `rsi_target` | 60 | 34.3% | **+391.5%** | +16.28% |
| `time_stop` | 23 | 13.1% | +11.7% | +1.47% |

Year by year, which is the part worth staring at:

| 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| −3.03% | −0.75% | **+24.60%** | **+26.75%** | −9.87% | −1.76% |

Four of six years are flat to negative; 2023 and 2024 are the entire result.
That is the same "one fold carries everything" shape the walk-forward sweep
found, showing up independently in calendar time. The forward-return study on
this window is again negative at every horizon under 63 days (−0.05% at 5d,
−0.27% at 10d, −0.57% at 21d with t = −1.96).

Note also the **42.3% win rate**. Public GFS backtests advertise 70–80%. Nothing
in this harness has ever produced that.

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

Note the ablation caveat: on `nse_all` the `no_sector_gate` row is *bit-identical*
to the baseline, because that universe has no industry labels for the gate to act
on. An ablation that changes nothing is evidence about the data, not the
strategy. That is now stated in the bias note.

Five conclusions, each of which contradicts some part of the strategy as pitched:

1. **The G+F filter is a risk control, not a return generator.** On the Nifty 500,
   removing it *raises* CAGR slightly (12.2% vs 11.7%) while nearly doubling
   drawdown (−28.3% vs −14.4%). On `nse_all` it does add return (12.0% vs 9.9%)
   but again its dominant effect is on drawdown (−31.5% vs −43.5%). Its value is
   in what it avoids, not what it finds. Marketing GFS as a way to *find winners*
   is backwards.
2. **The daily dip is the load-bearing leg.** Without it, 2,094 trades earn an
   expectancy of 0.01 R — statistically nothing. The dip is what concentrates a
   diffuse signal into something tradable.
3. **The proposed 3–5% fixed stop is inside the noise.** 48% of eventual winners
   first fell more than 3%, and 24.5% fell more than 5%. The `tight_pct_stop`
   ablation confirms it: win rate collapses from 46.8% to 30.4%. Meanwhile the
   2×ATR stop sits comfortably outside the noise — median winner MAE is −0.41 R,
   and only 8.8% of winners came within 80% of the stop. This is the single
   clearest actionable finding in the whole study.
4. **Ranking adds nothing.** `random_ranking` matches or beats the baseline on
   every universe tested. Any effort spent scoring candidates is currently wasted.
5. **Realism costs half the return.** `live_htf_candles` — using the in-progress
   monthly/weekly candle a real trader actually sees on a chart — drops Nifty 500
   CAGR from 11.7% to 5.8%. Published GFS backtests almost certainly use closed
   candles without saying so.

### Honest verdict

**The strategy does not have a demonstrable edge, and the evidence against it is
stronger than the evidence for it.**

What survives scrutiny:

- On the Nifty 500 with sector control on, it matches the index return with a
  third of the exposure and 40% of the drawdown (Sharpe 1.04). That is a real
  risk-adjusted result.
- Its entries beat a random-entry null at the 99.6th percentile *on that one
  configuration*.

What does not survive scrutiny:

- **The forward-return study — the cleanest test of the signal, free of any
  portfolio construction — shows no positive edge on any universe, and a
  significantly *negative* edge at 5 and 10 days on the full NSE list**
  (t = −2.08, −2.18). Stocks meeting the GFS condition underperform in exactly
  the short window the strategy claims to profit from.
- **The Monte Carlo pass does not replicate.** 99.6th percentile on Nifty 500,
  but 52.4th on Nifty 100 and 80.4th on `nse_all` — both failures.
- **The walk-forward DSR is 0.0** across 324 configurations. Two of three test
  folds lose money.
- **The defining thresholds are unstable.** `g_rsi_min` and `f_rsi_min` agree in
  only a third of folds. The "60" is not a discovered constant; it is a number
  that fits whichever window you looked at.
- It never beats buy-and-hold on return, on any universe.

The consistent pattern across every test is that **the risk machinery is doing
the work and the GFS condition is not**: the ATR stop is the only parameter
stable across folds, the sector gate is the biggest drawdown lever, the regime
gate helps, and ranking — the one place the "stock picking" would show up — is
indistinguishable from random.

Defensible summary: *a reasonable risk-managed swing framework wearing a
multi-timeframe RSI costume, where the costume is the least useful part.* The
70–80% win rates claimed in public GFS backtests do not appear anywhere in this
study under leak-free accounting; the highest win rate observed was 62.5%, and
only with a scale-out exit the original strategy does not specify.

### If you pursue this anyway

The ablations point at a better strategy than the one described. Treat these as
**hypotheses generated in-sample**, not results:

- Replace the RSI-65 target with `scale_out_and_trail` (ExpR 0.84 vs 0.27, win
  rate 62.5%) — it was the best exit on every universe tested.
- Use `risk_based_sizing` (best CAGR on both Nifty 500 and `nse_all`).
- Keep the ATR stop; discard the 3–5% fixed stop outright.
- Keep the sector and regime gates — they are the strongest components measured.
- Keep G+F for drawdown control if you like, but stop believing it selects
  winners, and do not tune its threshold.
- Drop the candidate ranking, or replace it with something that beats random.
- Test on the *live* HTF mode, since that is what you will actually trade.

Every one of those is a change *away* from the strategy as taught.

---

## The conviction study — and a partial reversal of the verdict above

Everything above was run with the strategy as taught: a 2×ATR stop, an RSI-65
exit, a 60-day time stop, and no filter on *where in its own range* the stock was
when it dipped. Under those settings the conclusion stands.

Two changes overturn it. Both were found by `conviction.py`, which simulates
every GFS signal as a standalone trade — ~1,030 gated signals instead of the
~240 the portfolio has room for — and splits the sample chronologically so rules
picked on the early years are scored on the later ones.

```bash
python -m backtesting.gfs.run_conviction --start 2013-01-01 --end 2026-08-21 --grid
```

### Finding 1: headroom is the only entry filter that replicated

Twenty-four features were screened by quintile (120 implicit comparisons, and
6,329 more for two-feature conjunctions — the script prints both counts, because
the best of that many looks good by chance). Almost all of them failed:
`sector_rs`, `breadth_pct` and `atr_pct` all looked excellent in-sample and
*inverted* out-of-sample. The best two-feature rule hit 76.6% on train and fell
to 59.5% on test, with a bootstrap CI of 34.9–74.6% — a fitted rule, not a
discovery.

One thing replicated, monotonically, on **both** halves:

| `headroom_pct ≥` | train n | train win | test n | test win | test ExpR |
|---|---|---|---|---|---|
| 0 | 507 | 45.0% | 524 | 49.8% | +0.356 |
| 10 | 452 | 48.2% | 475 | 49.5% | +0.363 |
| 15 | 287 | 52.6% | 339 | 51.3% | +0.433 |
| 20 | 172 | 56.4% | 200 | 57.5% | +0.653 |
| 25 | 95 | 61.1% | 121 | 60.3% | +0.726 |
| 30 | 40 | 62.5% | 64 | 64.1% | +0.884 |

`headroom_pct` is the distance from the entry close to the resistance level the
exit targets. The reason it works is mechanical rather than statistical, which is
why it survived: **the exit is defined at resistance, so a dip with the prior
swing high 3% overhead cannot pay for its own stop.** No amount of higher-
timeframe strength fixes a trade with nowhere to go. It is now a config knob,
`min_headroom_pct`, applied in `apply_conditions`.

### Finding 2: the win rate was never a property of the signal

The `--grid` sweep holds the entry population fixed and varies only the exit
geometry:

| win rate (%) | exit RSI 55 | 60 | 65 | 70 |
|---|---|---|---|---|
| stop 1.0×ATR | 35.3 | 31.6 | 27.7 | 26.3 |
| 2.0×ATR | 57.9 | 53.6 | 47.4 | 44.6 |
| 3.0×ATR | 71.1 | 69.2 | 62.8 | 56.7 |
| 4.0×ATR | 73.8 | **74.6** | 71.1 | 64.7 |

Win rate moves from 26% to 75% **without a single change to which stocks are
bought**, while expectancy stays in a band of 0.07–0.39 R with no relationship to
it. Any GFS win rate quoted without its stop width is uninterpretable, and the
public 70–80% claims are entirely reachable this way while making money in a
completely different manner than advertised.

### The 3–5% stop is the single most damaging rule in the brief

Requiring a 3–5% stop was the explicit risk instruction. The excursion data says
it is what was destroying the strategy:

- Median MAE of eventual **winners**: **−5.02%**
- Winners that first fell more than 3%: **68.5%**
- Winners that first fell more than 5%: **50.6%**

A 5% stop liquidates half the winners before they work. This is not a marginal
effect — the ATR stability sweep shows tightening the stop makes *every* metric
worse, including drawdown, which is the opposite of what a tight stop is for:

| `atr_stop_mult` | trades | win rate | ExpR | CAGR | MaxDD | Sharpe |
|---|---|---|---|---|---|---|
| 2.0 | 279 | 49.8% | +0.141 | +6.98% | −23.4% | 0.57 |
| 2.5 | 256 | 57.8% | +0.152 | +9.11% | −20.6% | 0.69 |
| 3.0 | 240 | 66.7% | +0.212 | +13.34% | −17.2% | 0.93 |
| **3.5** | **230** | **70.4%** | **+0.199** | **+14.16%** | **−17.5%** | **0.98** |
| 4.0 | 222 | 72.5% | +0.178 | +14.14% | −21.4% | 0.98 |
| 4.5 | 217 | 73.3% | +0.160 | +14.22% | −23.6% | 0.97 |
| 5.0 | 212 | 75.0% | +0.149 | +13.41% | −28.3% | 0.92 |

3.0–4.5 is a **plateau**, not a spike, which is what separates this from the
tuned parameters that failed walk-forward earlier.

### The configuration that survives

```bash
python -m backtesting.gfs.run_backtest \
  --start 2013-01-01 --end 2026-08-21 --universe nifty500 \
  --max-holding-days 0 --min-headroom-pct 10 \
  --atr-mult 3.5 --exit-rsi 60 \
  --max-positions 4 --max-position-pct 30 --monte-carlo 500
```

```
CAGR +14.16%  vs benchmark +10.80%   (excess +3.36%)
MaxDD -17.47% vs benchmark -38.44%   Sharpe 0.98
Trades 230 | Win 70.43% | PF 1.91 | ExpR +0.199 (+3.54%/trade)
Exits: rsi_target n=169 (73.5%, +208% of P&L) | stop n=61 (26.5%, -108%)
Random-entry Monte Carlo: 98.6th percentile
Forward return 63d: +1.59% edge, t = 3.08
```

Three separate things changed, and all three mattered:

1. **No time stop** (`--max-holding-days 0`). Improved every metric on its own.
2. **The headroom filter.** With it, the 63-day forward-return edge goes from
   +0.50% (t = 1.06, noise) to +1.59% (t = 3.08). This is the first time in the
   entire study that the *signal itself* — measured without any portfolio
   construction — has shown a statistically significant edge.
3. **A stop wide enough to survive the dip being bought.**

Capital had to be redeployed as well: filtering cut exposure from 29% to 16%, and
CAGR initially *fell* despite better trades because the money sat idle. Four
positions at 30% each restores it.

### What this does and does not overturn

Overturned: the claim that no filter helps, and that 70–80% win rates are
unreachable under leak-free accounting. Both were wrong. The strategy beats the
index on return *and* halves the drawdown, and its signal now clears a
significance test it previously failed.

Not overturned:

- **Payoff ratio is 0.87** — the average loss (−11.18%) is larger than the
  average win (+9.72%). Break-even win rate is ~53%. The current 70% leaves
  margin, but this configuration *depends* on staying above ~53%, which is a
  more fragile position than a high-payoff system.
- **`capacity` is now the top rejection reason** (1,427 signals dropped). Four
  concentrated positions is the mechanism that converts trade quality into CAGR,
  and it is also what makes the equity curve lumpy — 2014 (+46.8%), 2021, 2023
  and 2024 (+42.2%) carry the entire record, while 2016, 2018 and 2025 are
  negative.
- **Index-inclusion bias is unmeasured here.** All of the above is Nifty 500
  present-day constituents. Rerun on `nse_all` before trusting the level.
- **`min_headroom_pct = 10` is the CAGR optimum but not a plateau** — 15 spikes
  the drawdown to −31%. The *trade-quality* effect of headroom is monotonic and
  replicated; its *CAGR* effect is noisier because it also moves exposure. Trust
  the direction, not the decimal.
- **G and F still have not been shown to select winners.** Nothing in this study
  rehabilitated the 60/60 thresholds. The improvement came from where the stock
  sits relative to its resistance, how wide the stop is, and how long the trade
  is given — not from the Grandfather or the Father.

---

## Making it tradeable — costs, taxes and idle cash

The conviction study produced a config with a real edge. This section asks the
next question: does the edge survive contact with the tax office, and can the
strategy be made to work in years when it currently loses money?

### The finding that mattered most was not tax — it was idle cash

The single biggest correction in this section is not a filter. It is that the
strategy is only **~40% deployed**. Signals are scarce, so more than half the
capital sat in the account earning nothing for thirteen years. That default is
not neutral: the benchmark is 100% invested by construction and therefore never
pays that penalty, so a zero cash return quietly hands the comparison to
buy-and-hold.

Modelling the balance in a liquid fund at 6.5% (`--cash-yield-pct 6.5`) is the
realistic assumption for an Indian retail account, and it changes the picture
substantially:

| | idle cash at 0% | idle cash at 6.5% |
|---|---|---|
| CAGR after tax | +12.65% | **+15.02%** |
| Sharpe | 0.98 | **1.23** |
| Longest underwater | 570 sessions | **328 sessions** |
| 2016 | −3.32% | **+0.76%** |
| 2018 | −6.90% | −3.82% |
| 2025 | −7.37% | −3.81% |

Note what this is and is not. It does not improve a single trade, and the trade
list is byte-identical. It removes an accounting artefact that was making a
lightly-deployed strategy look worse than it is. `cash_yield_pct` defaults to
**0** so every number printed earlier in this document still reproduces.

### Taxes cost less than feared, because the trade count is low

The full Indian stack is modelled in `taxes.py`: STT, stamp duty, exchange
transaction charges, SEBI turnover fee, brokerage, and 18% GST on the
broker-side fees only — GST does not attach to STT or stamp duty. Capital gains
are computed per financial year (April–March), with the STCG rate switching from
15% to 20% on 23 July 2024, loss set-off in the direction the law allows
(short-term losses shelter both, long-term losses only shelter long-term), and
carry-forward.

The comparison is deliberately unflattering to the strategy: buy-and-hold is
taxed **once at exit**, so its gains compound untaxed for thirteen years, while
the strategy pays tax **annually** out of the account and therefore compounds
against itself.

```
CAGR gross           +16.73%
CAGR after charges   +16.19%   (drag 0.53pp)
CAGR after tax       +14.81%   (drag 1.38pp)
Benchmark, taxed once at exit  +10.00%
```

Total drag is **1.91pp**, and the post-tax excess is **+4.81%**. The reason it
is this mild is turnover: **16 trades a year**, holding ~36 days. The concern
that fees and taxes would eat the edge turns out to be unfounded *at this trade
count* — but it is a direct function of trade count, and any change that
multiplies turnover has to clear a much higher bar.

Essentially nothing qualifies for LTCG (0.0% of trades held >1 year). Attempts
to engineer holdings past 365 days are counterproductive — see the trailing-stop
result below.

### Which dials actually work

Every variant below is the same entry population; only the dial changes.

| dial | post-tax CAGR | Sharpe | verdict |
|---|---|---|---|
| baseline (4×30%, RSI 60 exit) | +12.57% | 0.98 | reference |
| `--rank-by headroom` | +11.44% | — | **hurts** |
| `--rank-by reward_risk` | +12.36% | — | no better than composite |
| `--exit-mode scale_out` | +10.49% | 0.84 | fixes payoff, costs return |
| `--exit-mode trail` | +2.79% | — | **destroys the strategy** |
| `--cash-yield-pct 6.5` | +15.02% | 1.23 | **the big one** |
| `--min-breadth 40` (with cash yield) | +14.81% | **1.25** | buys a losing year |

Three of these deserve comment.

**Ranking is still ≈ random.** Capacity is the top rejection reason (1,427
signals dropped), so choosing *which* scarce slot to fill ought to matter.
It does not. `RANK_HEADROOM` — the feature that survived the conviction study as
an entry *filter* — actively hurts as a *ranking* key. A variable can be
informative about whether to trade at all and uninformative about which of two
qualifying trades is better; these are different questions and the answer to one
does not transfer.

**`scale_out` fixes the payoff ratio but not the return.** It lifts the payoff
ratio from 0.87 to **1.39** and doubles expectancy (0.199 → 0.430 R) with a
74.2% win rate. It still earns less, because booking half the position early
leaves even more capital idle in a strategy that is already under-deployed. This
is a genuine risk-preference choice — less dependence on the win rate, lower
return — not a free improvement.

**Pure trailing exits destroy the strategy** (+2.79%, 38.8% win rate, −40%
drawdown). The RSI target exit is load-bearing. This also closes off the
tax-efficiency idea of letting winners run into LTCG territory: the mechanism
that would extend holding periods is the same one that removes the edge.

### Concentration, not diversification, is what converts quality into return

| slots × size | post-tax CAGR | ExpR | Sharpe | avg exposure |
|---|---|---|---|---|
| 3 × 35% | +12.67% | 0.183 | 0.88 | 45.6% |
| **4 × 30%** | **+12.57%** | 0.199 | 0.98 | 41.7% |
| 5 × 25% | +10.29% | 0.176 | 0.90 | 37.3% |
| 6 × 20% | +10.35% | 0.193 | 0.98 | 33.6% |
| 8 × 15% | +9.29% | **0.221** | **1.05** | 27.7% |

Read the two right-hand columns against the left. Spreading wider makes every
*trade statistic* better — expectancy and Sharpe are best at 8×15 — and makes
the *portfolio* worse, monotonically, because exposure collapses from 45.6% to
27.7%. There are not enough signals to fill eight slots, so extra slots do not
add positions, they only shrink the ones you get. 4×30 is the compromise; 3×35
earns marginally more with a worse drawdown.

### The losing years are mostly, but not entirely, fixable

Requiring 40% market breadth before opening new positions removes 2018 from the
loss column and leaves **one** negative year in fourteen (2025, −3.75%), while
improving Sharpe to 1.25 and cutting the longest underwater stretch from 328 to
272 sessions. It costs 0.21pp of CAGR.

Breadth ≥60 is the useful control: over-tightening does not keep helping, it
**creates** new losing years (2015, 2018, 2022 at −6.71%, 2025) and drops CAGR
to 11.53%. A filter that improved monotonically with strictness would be a
warning sign that it was fitted to the specific bad years; this one behaves the
way a real regime filter should.

`--sector-top-n 3` (+9.96%) and `--min-headroom-pct 15` (+12.32%, −27.6% DD)
both hurt. Not every tightening is an improvement.

### The recommended tradeable config

```bash
python -m backtesting.gfs.run_backtest \
  --start 2013-01-01 --end 2026-08-21 --universe nifty500 \
  --max-holding-days 0 --min-headroom-pct 10 --atr-mult 3.5 --exit-rsi 60 \
  --s-rsi 43 \
  --max-positions 4 --max-position-pct 30 \
  --cash-yield-pct 6.5 --min-breadth 40
```

```
CAGR gross +20.47% | after charges +19.90% | after tax +18.54%
Benchmark taxed once at exit +10.00%   ->  post-tax excess +8.54%
Max drawdown -19.67% (vs benchmark -38.44%) | Sharpe 1.30 | Sortino 1.97
Trades 279 (20.5/yr) | Win 71.68% | PF 1.98 | ExpR +0.203 | payoff 0.82
Monte Carlo: 99.0th percentile of 500 random-entry runs
Negative years: 2013 (-4.80%), 2016 (-8.44%)
Split test: H1 2013-19 excess +2.18%, H2 2019-26 excess +9.15%
```

> **Two later changes are not in that command line.** `--exit-rsi 70` (see
> "Exit target" in EXPLORATIONS.md ch. 8) raises post-tax CAGR to +21.50% and
> lifts payoff from 0.82 to 1.37, but it doubles the holding period and lost to
> exit-60 in YTD 2026 — treat 68–72 as a preference, not a settled result. And
> the **regime gate now defaults to breadth-only**, which is a default change
> rather than a flag: see the next section.

`--s-rsi 43` replaced the taught value of 40 after the split test in "Loosening
the filters" below; 43-45 is the defensible region and 43 is its midpoint, not a
tuned optimum. Without it the same config returns +14.81% post-tax with a
first-half excess of −0.04%. The dataclass default remains 40 so that every
earlier number in this document still reproduces from a bare `GFSConfig()`.

### The regime gate: breadth-only is now the default

The gate used to be two conditions ANDed: benchmark above its 200-DMA **and**
market breadth ≥ 40%. It is now `--regime-mode`, with two choices:

| mode | test | default |
|---|---|---|
| `breadth` | breadth ≥ `--min-breadth` | **yes** |
| `breadth+sma` | breadth ≥ `--min-breadth` **and** benchmark > SMA(`--regime-sma`) | the old behaviour |

`min_breadth_pct` now defaults to **40.0** rather than 0, so the gate is live out
of the box.

> **Reproducibility note.** This is a behaviour change to the bare
> `GFSConfig()` defaults — previously the gate was `benchmark > SMA200 AND
> breadth ≥ 0%`, i.e. the trend leg alone. Numbers printed elsewhere in this
> document that predate this section were produced under the old default; to
> reproduce them exactly, pass `--regime-mode breadth+sma --min-breadth 0`.

| variant | CAGR | Sharpe | DD | expo | T1 13-17 | T2 17-22 | T3 22-26 |
|---|---|---|---|---|---|---|---|
| `breadth+sma` (old default) | +21.50 | 1.31 | −23.39 | 58.1 | **−1.14** | +8.97 | +17.69 |
| **`breadth` (new default)** | +20.94 | 1.27 | −23.40 | 64.4 | **+1.19** | +10.32 | +13.78 |
| index 200-DMA only | +21.23 | 1.28 | −21.75 | 61.3 | +1.25 | +7.21 | +16.40 |
| no gate at all | +23.77 | 1.28 | −28.72 | 76.4 | +5.85 | +11.48 | +16.88 |

**The AND of both legs was the only configuration tested that loses a third.**
Breadth-only costs 0.56pp of CAGR, has an *identical* drawdown, adds 6.3pp of
exposure, and turns T1 positive.

Two things stop this from becoming "drop the gate entirely":

- **`no gate` is leverage, not edge.** It runs at 76.4% exposure. Cut back to a
  matched ~60% and it returns **+18.08%** against the gated +21.50%. On
  CAGR-per-unit-exposure the gated config is the best of everything tested
  (0.370 vs 0.311), which is the relevant metric when GFS shares a corpus with
  other strategies. It also gives back 2018 entirely (−0.2% vs +16.9%).
- **The sample starts in 2013, so there is no 2008 in it.** The 200-DMA leg's
  real value is a slow grinding bear; in 2020's V-shaped crash it *cost* money
  (+31.6% vs +47.9% ungated) by re-admitting capital too late. Dropping it is a
  bet that future crashes look more like 2020 than 2008. If you disagree, it is
  one flag: `--regime-mode breadth+sma`.

The change was motivated by live-ish evidence rather than a sweep: in 2026 the
gate was shut from March to August because the benchmark stayed below its
200-DMA, while breadth had already recovered from 26.9% to 59.7% and qualifying
setups were sitting there unbought (6 on 13 May). Full write-up in
EXPLORATIONS.md ch. 13 and 15.

### The universe check — and why the level above should not be trusted

Every number in this section so far is Nifty 500 *present-day* constituents.
Rerunning the identical config on `nse_all` (2,296 currently-listed EQ symbols)
gives a very different answer:

| | nifty500 | nse_all |
|---|---|---|
| CAGR after tax | **+14.81%** | **+9.60%** |
| Benchmark, taxed once | +10.00% | +10.00% |
| post-tax excess | **+4.81%** | **−0.40%** |
| Max drawdown | −17.06% | −28.71% |
| Sharpe | 1.25 | 0.79 |
| Trades / win rate | 219 / 70.8% | 286 / 67.1% |
| Expectancy | +0.204 R | +0.135 R |

**On the full listed universe the post-tax edge disappears.** That is the single
most important line in this document, and it outranks every optimisation above.

Two things are mixed together in that gap, and honesty requires separating them:

1. **Index-inclusion bias is real and large.** Nifty 500 membership *today* is
   partly a consequence of having performed well during the test window, so
   restricting the strategy to those names hands it a set of stocks pre-selected
   for success.
2. **But the comparison is confounded.** 100% of the `nse_all` universe has no
   industry label, so the sector-strength gate passes everything and the
   per-sector position cap never binds. The `nse_all` run is therefore not the
   same strategy with a wider universe — it is the same strategy *with two risk
   controls switched off*, which alone explains part of the worse drawdown
   (−28.7% vs −17.1%) and the 2015 (−16.96%) and 2022 (−6.01%) losses.

So the correct reading is neither "the strategy only works on the Nifty 500" nor
"the edge is fake." It is: **the +14.81% level is not established outside the
index universe, and the clean experiment has not been run.** Doing it properly
requires sector labels for the full NSE list so the funnel is identical on both
sides. Until then, treat +14.81% as an optimistic upper bound and the true
figure as somewhere between the two columns.

### What is still wrong with it

- **The payoff ratio is still 0.82.** The average loss is larger than the
  average win, so break-even sits near a 55% win rate. The config clears it at
  71.7%, but the margin is the thing to monitor: this is a system that *depends*
  on being right often. Both attempts to fix the asymmetry — `scale_out` and the
  weekly-breakdown exit — improved the payoff ratio exactly as intended and lost
  return doing it, because they traded win rate away one-for-one.
- **Returns are still lumpy.** 2014, 2021, 2023 and 2024 carry the record.
- **Roughly 2.4pp of the post-tax CAGR now comes from a liquid fund, not from
  GFS.** That is honest accounting, not a stock-picking edge, and it should not
  be reported as one.
- **One negative year in fourteen is not the same as "positive in all market
  conditions."** 2025 resists every filter tried here.
- **Every parameter above was chosen on the same 13-year window.** There is no
  out-of-sample period left. The conviction study's train/test split is the only
  genuine out-of-sample evidence in this repo, and it covers the entry filter
  only — not the stop, the exit, the sizing or the breadth gate.
- **The `nse_all` run does not confirm the level** (see above). Sector labels for
  the full NSE list are the missing piece needed to settle it.
- **Almost all of the excess return is in the second half of the record.** See
  the split test below — this is the sharpest qualification of the +4.81% figure.

### Levers not yet tested

Recorded so they are not mistaken for dead ends. Ranked by expected value.

1. **Park idle cash in the index instead of a liquid fund.** Even at maximal
   loosening the strategy never exceeded 60.8% average exposure, so *no entry
   filter can fix the cash drag* — it is structural. Holding NIFTYBEES in the
   gaps would keep the account 100% invested, let GFS positions displace index
   exposure rather than cash, and turn the reported excess into true alpha. This
   is the single biggest untested change and it would most likely rescue the
   flat 2013-2019 half.
2. ~~**RSI period — never swept, at all.**~~ **Swept.** 7 → +20.12%, 9 → +16.55%,
   **14 → +21.50%**, 21 → +10.15%. The default is also the peak, so there is no
   fitting concern — the one sweep that could only have produced bad news, and
   didn't. See EXPLORATIONS.md ch. 12.
3. ~~**Risk-based sizing.**~~ **Tested — it is a leverage dial, not a selector.**
   `--risk-per-trade-pct` moves return and drawdown together in fixed proportion
   because it moves *exposure*; at matched exposure it does not beat equal
   weight. Legitimate as a risk control, not reportable as an edge.
   See EXPLORATIONS.md ch. 10.
4. ~~**Re-entry after a stop while G and F are still intact.**~~ **Tested and
   closed.** It was never blocked — the engine only skips symbols *currently
   held*. The diagnostic found the Father leg is what prevents it: the day after
   a stop, weekly RSI averages 46.4 and only **1.5%** of stopped names still
   qualify, while monthly RSI averages 66.4. Adding hysteresis to the Father leg
   lost on every metric. See EXPLORATIONS.md ch. 14.
5. **Entry-side trend-intactness filter** — price above its 50-DMA while daily
   RSI is depressed. This is the weekly-breakdown idea moved to the entry, where
   a false positive costs an opportunity instead of a realised loss.

## Loosening the filters — what more permissiveness actually buys

The question this section answers: *are the filters throwing away trades that
would have helped?* Everything below is on the 13.6-year window, post-tax,
`nifty500`, changing one dial at a time from the recommended config.

### First, a noise floor

`--sector-top-n 11` and `--sector-top-n 12` differ by **two trades out of 279**
and by **0.71pp of post-tax CAGR**. That calibrates everything else here: on a
sample of this size and this skew, differences below roughly 1pp are not
evidence of anything. Several plausible-looking results in the tables below sit
inside that band and are reported only so they are not re-tested later.

### Not all filters do the same job

Loosening splits cleanly into two behaviours, and conflating them is the trap.

| dial loosened | exposure | ExpR (edge per trade) | Sharpe | reading |
|---|---|---|---|---|
| `--sector-top-n` 3 → 12 | 28.5% → 50.8% | 0.186 → 0.221 (no trend) | 1.14 → 1.24 (flat) | pure **throttle** |
| `--s-rsi` 35 → 50 | 18.8% → 58.2% | 0.322 → 0.152 (falls) | 1.54 → 1.00 | genuine **selector** |

The sector gate does not pick better trades. Across `--sector-top-n` 3 to 12 the
per-trade expectancy and the Sharpe barely move while average exposure nearly
doubles. All it does is meter how much capital gets deployed. The daily-RSI
threshold is the opposite: it visibly changes the quality of what is bought.

That distinction matters because on the full record, loosening the sector gate
*looks* like the best idea available:

| `--sector-top-n` | post-tax CAGR | Sharpe | exposure | neg. years |
|---|---|---|---|---|
| 3 | +10.32% | 1.14 | 28.5% | 1 |
| 4 | +14.42% | 1.30 | 34.0% | 1 |
| **5 (default)** | **+14.81%** | **1.25** | **39.1%** | **1** |
| 6 | +14.41% | 1.17 | 41.7% | 2 |
| 7 | +15.20% | 1.17 | 44.5% | 3 |
| 8 | +13.33% | 1.07 | 45.9% | 2 |
| 9 | +16.48% | 1.22 | 47.6% | 3 |
| 10 | +16.61% | 1.22 | 48.2% | 3 |
| 11 | +16.55% | 1.20 | 49.1% | 3 |
| 12 | +17.26% | 1.24 | 50.8% | 1 |

It is not a spike — 9 through 12 is a genuine four-value plateau around +16.7%.
It is still wrong, for the reason in the next subsection.

### The split test, which is what settled it

Splitting the record at 2019-09-01 and requiring a setting to beat the index in
*both* halves is the strongest test available without new data. It disqualifies
the sector loosening immediately:

| config | H1 2013-19 excess | H2 2019-26 excess | H1 exposure |
|---|---|---|---|
| recommended (top 5) | −0.04% | +4.08% | 31.3% |
| `--sector-top-n 12` | **−2.96%** | +11.82% | 45.4% |
| `--sector-top-n 10` | **−2.96%** | +10.63% | 41.2% |
| `--sector-top-n 7` | −0.41% | +5.26% | 37.5% |
| `--sector-top-n 6` | −0.20% | +3.68% | 33.8% |
| `--min-headroom-pct 5` | **−2.09%** | +3.37% | 32.3% |
| `--s-rsi 35` | −1.00% | −2.11% | 14.7% |

The variants that top the full-record table are the *worst* in the first half.
They deploy more capital, and the second half contained 2020-2024. That is a
beta bet wearing the costume of an edge, and the full-record CAGR cannot tell
the two apart.

**This test also indicts the recommended config**, which is why it belongs in
this README rather than in a footnote: its H1 excess is **−0.04%**. For the
first seven years the strategy returned what the index returned. It did so at
31% average exposure with a Sharpe of 1.17 against an index that drew down 38%,
which is a defensible risk-adjusted result — but it is not the +4% excess the
headline implies, and anyone sizing this should assume the first-half behaviour
is the realistic one.

### The one loosening that survives

The daily entry threshold. `--s-rsi` 43 through 48 is positive in **both**
halves, with 40 flat in H1 and 50 breaking down:

| `--s-rsi` | H1 excess | H2 excess | full post-tax | Sharpe |
|---|---|---|---|---|
| 35 | −1.00% | −2.11% | +10.91% | 1.54 |
| 38 | — | — | +9.32% | 1.03 |
| **40 (default)** | **−0.04%** | **+4.08%** | **+14.81%** | **1.25** |
| **43** | **+2.18%** | **+9.15%** | **+18.54%** | **1.30** |
| 45 | +1.38% | +7.36% | +17.12% | 1.20 |
| 48 | +1.25% | +3.42% | +14.89% | 1.05 |
| 50 | −2.61% | +8.22% | +15.44% | 1.00 |

Three adjacent values all improving both halves is the plateau argument; the
peak at 43 on its own would not be worth acting on. Full validation of `--s-rsi 43`:

```
CAGR gross +20.47% | after charges +19.90% | after tax +18.54%
Benchmark taxed once at exit +10.00%   ->  post-tax excess +8.54%
Max drawdown -19.67% (vs benchmark -38.44%) | Sharpe 1.30 | Sortino 1.97
Trades 279 (20.5/yr) | Win 71.68% | PF 1.98 | ExpR +0.203
Monte Carlo: 99.0th percentile of 500 random-entry runs
Negative years: 2013 (-4.80%), 2016 (-8.44%)
```

Against the recommended config it buys +3.73pp of post-tax CAGR and a better
Sharpe, and costs 2.6pp of drawdown and one extra negative year. Note it moves
2025 from −3.75% to **+3.85%** while pushing 2013 and 2016 negative — the bad
years move around rather than disappearing.

The mechanism is plausible rather than mysterious: RSI 40 on a daily chart is a
rare event in a stock whose monthly and weekly RSI are both above 60, because
such a stock is by construction not falling much. Demanding 40 discards most of
the pullbacks the strategy is designed to buy. 43 is still a real dip.

**Caveat on how this was found.** The split was used to *choose* S43, so this is
weaker than a true holdout — it is a consistency check, not a clean
out-of-sample test. The honest statement is that 43-45 is a defensible region
and that the gap between +18.54% and +17.12% is close to the noise floor above.
Prefer the region to the point estimate.

### Loosenings that were tested and rejected

| dial | result | why rejected |
|---|---|---|
| `--min-headroom-pct` 5 or 0 | +13.30%, DD −20.54%, 3 neg. years | worse in both halves; the one filter with independent out-of-sample support |
| `--no-sector-filter` | +13.88%, exposure 54.8% | worse than keeping the gate at any setting |
| `--min-breadth` 20 / 30 / 35 | +15.02 / +15.22 / +15.06% | all inside the noise floor; the filter barely binds below 40 |
| `--g-rsi` 55 or 50 | +15.43 / +15.36% | inside noise; the Grandfather leg is nearly non-binding already |
| `--f-rsi` 55 or 50 | +14.89 / +15.60%, DD −25.07 / −23.20% | flat return for 6-8pp more drawdown |
| `--g-rsi 55 --f-rsi 55` | +12.94%, Sharpe 1.02 | strictly worse |
| `--trigger recross` | +6.46% | badly worse; wait-for-recross forfeits the entry price |
| `--max-per-sector 3` | +11.70%, DD −24.77% | concentration cap is doing real work at 2 |
| `--sector-lookback 126` | +12.46%, 4 neg. years | 63 sessions is the better relative-strength window |

Two of these deserve a note. `--g-rsi` barely matters because a stock with
weekly RSI above 60 almost always has monthly RSI above 60 too — the Grandfather
leg is largely redundant with the Father leg, which is worth knowing before
defending the three-timeframe story too hard. And loosening the *Father* leg
raises drawdown sharply without raising return, which is consistent with the
earlier finding that stop-loss exits are nearly always accompanied by a weekly
RSI breakdown.

### The summary answer

Loosening the entry funnel does not uncover missed opportunity. With one
exception it either dilutes the per-trade edge (`--s-rsi` above 48, `--f-rsi`,
`--min-headroom-pct`) or buys market beta that only pays in a bull half
(`--sector-top-n`). The exception, `--s-rsi 43`, is worth adopting. The larger
finding from this exercise is the split test: **the strategy's excess return is
concentrated in 2019-2026 and is approximately zero in 2013-2019**, and that is
true of the recommended config too.

## The weekly-breakdown exit — a good hypothesis that the base rates killed

The trade log made this look obvious. On nearly every stop-loss exit the weekly
RSI had collapsed mid-trade while the entry-side "Father" condition had been
intact at entry: WIPRO 67→45, ADANIENT 63→37, COLPAL 77→44, ENDURANCE 60→37.
The losses looked less like noise than like *the Father failing*. Cutting on
that should shrink the average loss and fix the 0.82 payoff ratio, which is the
config's main structural weakness.

`--exit-f-rsi N` implements it: leave when weekly RSI falls below `N`,
regardless of P&L. It is neither a stop nor a target — it fires because the
reason for holding stopped being true. It is **disabled by default (0)**.

### It did exactly what it was supposed to, and still lost

| `--exit-f-rsi` | payoff | win rate | ExpR | post-tax CAGR |
|---|---|---|---|---|
| off | 0.82 | 71.7% | +0.203 | **+18.54%** |
| 40 | 0.84 | 71.3% | +0.202 | +18.51% |
| 45 | 0.91 | 69.2% | +0.197 | +18.23% |
| 50 | 1.08 | 61.2% | +0.139 | +13.44% |
| 55 | **1.50** | 49.2% | +0.084 | +8.67% |

The payoff ratio improves monotonically and substantially — the mechanism is
real, and at 55 it nearly doubles. Expectancy falls the whole way. This is the
mirror image of the earlier `scale_out` result: **win rate and payoff are two
ends of one dial, and moving either end does not change the product.** The
result reproduces on the S40 base (+14.81% → +10.61%) and in both halves, so it
is not an artifact of one window.

### Why — measured, not assumed

For every closed trade, the lowest weekly RSI reached between entry and exit:

| weekly RSI floor | winners (n=200) | losers (n=79) |
|---|---|---|
| dipped below 55 | 39.0% | 82.3% |
| dipped below 50 | 18.0% | 59.5% |
| dipped below 45 | 4.5% | 20.3% |
| dipped below 40 | 0.5% | 3.8% |
| **median floor** | **56.6** | **48.9** |

**The signal is genuinely informative** — a loser is 3.3× more likely to breach
50 than a winner, and the median floors are 8 points apart. The original
observation was correct. It is the base rates that defeat it: at a 71.7% win
rate there are 200 winners against 79 losers, so a 3.3:1 likelihood ratio still
means an exit at 50 **cuts 47 losers and 36 winners — 43% friendly fire.**
Tightening to 45 improves the ratio (36% friendly fire) but only catches a fifth
of the losers, which is why it is nearly a no-op.

The damage is worse than the counts imply, because the two errors are not
symmetric. A winner cut on a weekly breakdown is cut *near its low*, forfeiting
the entire recovery that made it a winner. A loser cut on the same signal only
saves the sliver between the breakdown and the ATR stop that was going to catch
it anyway at −12.5%. So even at equal counts the rule loses money.

**Verdict: rejected.** The flag stays in the codebase, tested and defaulted off,
because the negative result is worth keeping and the dial is worth having. The
general lesson is worth more than the rule: *at a high win rate, an exit filter
needs specificity far beyond "statistically significant" to pay for itself.* Any
future exit idea should be checked against the winner/loser overlap table above
before it is backtested.

The entry-side version of this idea is untested and is not ruled out by any of
the above: requiring the pullback to be *structurally intact* at the moment of
entry (price still above its 50-DMA while daily RSI is low) filters before
capital is committed, where a false positive costs an opportunity rather than a
realised loss.

---


| file | role |
|---|---|
| `config.py` | every knob, with `validate()` |
| `indicators.py` | Wilder RSI/ATR + the leak-free HTF projection — **the trust anchor** |
| `panels.py` | vectorized causal pre-computation; `PANEL_COLUMNS` is the engine contract |
| `strategy.py` | entry qualification, stops, exits, sizing |
| `portfolio.py` | cash, positions, costs, R-multiples, MAE/MFE |
| `engine.py` | the daily loop and its ordering |
| `metrics.py` | performance, excursions, exit attribution |
| `taxes.py` | Indian statutory charges + capital gains (FY, set-off, 2024 rate change) |
| `baselines.py` | buy & hold, forward-return study, random-entry null, ablations |
| `sweep.py` | walk-forward sweep, DSR, parameter-stability curves |
| `conviction.py` | portfolio-free signal labelling, train/test feature search, stop×exit grid |
| `run_conviction.py` | CLI for the conviction study |
| `universe.py` | NSE index / all-equity loading, sector map, bias note |
| `service.py` | orchestration; caches the expensive indicator pass across variants |
| `run_backtest.py` | CLI |
| `README.md` | what the harness is and what the current config does |
| `EXPLORATIONS.md` | **the research log** — every hypothesis tried, in order, including the rejected ones |

Tests live in `tests/test_gfs_leakage.py`, `tests/test_gfs_mechanics.py`,
`tests/test_gfs_engine.py` and `tests/test_gfs_sweep.py` (73 tests), plus
`tests/test_bars.py` (28) for the shared price store. The leakage suite is the
one that matters; run it before trusting any change to `indicators.py` or
`panels.py`.

### A note on the panel cache

`build_panels` accepts a cache keyed by `base_panel_key(cfg)`. Thresholds like
`g_rsi_min` only re-evaluate a boolean, whereas RSI periods change the expensive
indicator pass — so an 11-variant ablation or a 324-configuration sweep pays for
the indicator pass once. `test_base_panel_cache_cannot_change_results` proves the
cache is a pure optimisation, because a stale cache would silently corrupt every
sweep result while every single-config test still passed.

### A note on the price store

Daily bars come from `core.bars`, a shared per-symbol store (one row per symbol
per day) in the project SQLite database. Because it is keyed by symbol and date
rather than by a hash of the whole request, changing `--start`, `--end` or
`--universe` re-uses everything already on disk and downloads only the genuinely
missing bars. Measured on this repo: a Nifty 500 run over a fresh window went
from ~10 minutes to **37 seconds**, and switching to `nifty100` to **10 seconds**,
with zero network calls in both cases.

Warm it deliberately if you prefer:

```powershell
python -m backtesting.warm_bars --universe nifty500 --start 2018-01-01
python -m backtesting.warm_bars --stats
```

Two design decisions in that module are worth knowing about, because both are
correctness matters rather than performance ones:

- **Only raw daily OHLCV is stored — never RSI, and never weekly/monthly bars.**
  Those are derived at run time. A persisted `monthly_rsi` column would carry no
  record of whether it came from a closed candle or an in-progress one, and that
  distinction is worth ~6pp of CAGR here (see `live_htf_candles` above). Keeping
  the leak-free logic in one place beats caching its output.
- **Every top-up re-fetches a short overlap and compares it.** yfinance serves
  split-adjusted prices, so a corporate action silently rewrites history; naive
  appending would splice two adjustment bases into a single series. If an
  overlapping close has moved more than 0.5%, the symbol is dropped and refetched
  in full. `test_split_adjustment_drift_triggers_a_full_refetch` covers it.
