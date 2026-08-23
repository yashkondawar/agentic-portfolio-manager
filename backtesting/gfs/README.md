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
> rate and index-beating return. Do not quote one without the other.

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
| `conviction.py` | portfolio-free signal labelling, train/test feature search, stop×exit grid |
| `run_conviction.py` | CLI for the conviction study |
| `universe.py` | NSE index / all-equity loading, sector map, bias note |
| `service.py` | orchestration; caches the expensive indicator pass across variants |
| `run_backtest.py` | CLI |

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
