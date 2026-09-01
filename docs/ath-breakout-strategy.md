# ATH Breakout Sleeve

A trail-only momentum sleeve reconstructed from a 14-year backtest dossier
(`dossier_N28_SL16_ATH15.xlsx`). No generating source was available, so every
rule below was recovered by fitting the workbook's own numbers and then
verified arithmetically against it.

Code lives in `backtesting/breakout_ath/`. The live daily runner is registered
as the `breakout_ath_daily` strategy.

---

## 1. The strategy

> 52-week-high breakout | trail-only | mom_3m ranking | N=28, stop=16%,
> within 15% of lifetime high, 25 bps + tax

### Universe

The **Nifty Total Market 750**, taken from NSE's published constituent list
(`ind_niftytotalmarket_list.csv`). The same file supplies each name's industry
label.

This is the *current* constituent list applied across all history, so the
sleeve carries survivorship bias. See §5.

### Entry

A stock is bought when **both** conditions hold on the same close:

1. **Breakout** — today's close exceeds *every* close of the prior 252
   sessions.
2. **Proximity to the lifetime high** — today's close is at least **85%** of
   the highest close the stock has ever printed.

Rule 2 is what separates this from a plain 52-week-high screen. A stock can
make a one-year high while still far below an old peak; those are recoveries
into overhead supply, and the band excludes them.

Both legs use **closes only** — no intraday highs. This was tested explicitly:
a close/close formulation covers 848 of the dossier's 858 entries, whereas
substituting intraday highs into either leg drops coverage to 373 and 809
respectively.

### Ranking and slots

The book holds up to **28** positions. When more names qualify than there are
free slots, candidates are ordered by **3-month momentum** (63-session return)
and the strongest fill the slots.

There is no per-day entry cap: the dossier opened 9 positions on day one and 7
on day two. The book runs close to full — a mean of 25.6 of 28 slots, with
mean cash of 4.4%.

### Position sizing

Each slot gets an equal share of equity, **re-struck quarterly**:

```
budget = equity / 28          (recomputed each quarter, capped by cash)
cost   = 25 bps x budget
value  = budget - cost
qty    = value / price        (fractional shares)
cash  -= budget               (the full budget, not just the value)
```

Verified against the dossier's first session to the rupee: budget
357,142.857, cost 892.857143, value 356,250.0, cash after the first fill
9,642,857.14, and end-of-day equity 9,991,964.

### Exit

**One exit rule. There is no profit target and no time exit.**

```
anchor = highest close since entry     (initialised at the entry price)
stop   = anchor x 0.84                 (16% below the anchor)
exit when close < stop
```

The anchor ratchets up and never down. The fill is taken **at the breaking
close**, not at the stop level — so a gap costs more than 16%. The reference
book contains exactly that: THANGAMAYL exited at −20.55%.

This was confirmed directly against the dossier's own `anchor` and
`stop_level` columns over 400 sampled exits:

| Test | Result |
|---|---|
| `anchor` == running max **close** | **393 / 400** |
| `anchor` == running max **high** | 0 / 400 |
| `stop_level` == `anchor x 0.84` | **400 / 400** |

The 7 anchor mismatches are all within 0.6% and all dividend payers —
adjustment drift, not a different rule.

Exit reasons in the reference book: 829 `TRAIL_SL` and 2 `CORPORATE_ACTION`
(a holding that stops printing prices). Nothing else.

### Costs and tax

- **25 bps per side**, charged on entry and exit.
- **STCG 20%** flat across the whole history — note this is *not* the
  15%-then-20% split India actually applied; the dossier uses 20% throughout.
- **LTCG 12.5%**, with **no annual exemption** — the sleeve is one part of a
  larger book, so the exemption is assumed consumed elsewhere.
- Short-term losses set off against long-term gains; unabsorbed short-term
  losses carry forward. Financial years run April–March, and the short/long
  split is at `hold_days > 365` calendar days.

Every row of the dossier's Tax_Ledger reproduces to the rupee under these
rules.

---

## 2. Data sources

| What | Source |
|---|---|
| Universe + industry labels | NSE `ind_niftytotalmarket_list.csv` (752 rows) |
| Prices | yfinance **adjusted** closes, cached in a local SQLite bar store |
| Benchmark | `^NSEI` (NIFTY 50) |
| Broad index | `^CRSLDX` (NIFTY 500) |

Price provenance was verified: 246 of 250 sampled dossier entry prices match
the repo's bar store within 1 basis point, with a median relative difference of
9e-8 — pure float noise.

The universe fingerprint is exact: **all 436 traded names** in the dossier are
NTM750 constituents, and the industry label matches on **1689 / 1689** rows.

> **History depth matters.** The lifetime-high test needs unbounded history. An
> early run against a bar store that only reached back to 2008 produced wrong
> ratios and zero candidates. `data.py` deliberately loads from 1996.

---

## 3. Running it

```bash
# Backtest (cached prices) — writes summary.json, trades.csv, positions.csv, dossier.xlsx
python -m backtesting.breakout_ath.run_backtest

# Refresh prices first
python -m backtesting.breakout_ath.run_backtest --download

# Today's exits and entries
python -m backtesting.breakout_ath.run_backtest --daily
```

The daily runner keeps its book in
`backtesting/breakout_ath/data_cache/daily_portfolio.json`, or accepts a
caller-supplied `portfolio_state` dict.

**The live and backtest paths call the same functions in `signals.py`**, so
the two cannot drift apart. That is the whole reason entry logic is factored
into pure matrix functions rather than duplicated.

---

## 4. Reproduction results

Backtest over the dossier's own window, 2012-10-19 → 2026-08-24 (13.85 years,
3416 sessions), starting from ₹1,00,00,000.

| Metric | Reference | Reproduction | Δ |
|---|---:|---:|---:|
| Sessions | 3416 | 3416 | **exact** |
| Win rate | 49.82% | 49.50% | −0.6% |
| Mean positions open | 25.60 | 26.65 | +4.1% |
| Mean cash | 4.40% | 5.09% | +15.7% |
| Avg holding (calendar days) | 148.86 | 142.67 | −4.2% |
| Round trips | 831 | 905 | +8.9% |
| Total fills | 1689 | 1838 | +8.8% |
| Beta vs NIFTY 50 | 0.609 | 0.659 | +8.3% |
| Correlation | 0.592 | 0.578 | −2.3% |
| **CAGR before cost & tax** | **~31.98%** | **~32.02%** | **+4 bp** |
| CAGR net of cost & tax | 27.29% | 30.33% | +11.1% |
| Max drawdown | −28.72% | −32.18% | −12.0% |

**Reading this honestly:** the *gross* strategy is reproduced almost exactly —
before-cost-and-tax CAGR agrees to 4 basis points, and win rate, holding
period, position count and correlation are all within a few percent. The
config block matches field for field.

The net-CAGR gap traces almost entirely to one thing: the reproduction takes
**~9% more trades**. See §5.

The rebuilt workbook has the same nine sheets in the same order with the same
columns:
`Summary`, `Equity_Curve`, `Positions`, `Trades`, `Yearly_Returns`,
`Rolling_3Y`, `Rolling_5Y`, `Daily_Returns_Portfolio`, `Tax_Ledger`.

---

## 5. Known gaps — read before trusting this

1. **An unidentified entry discriminator.** The recovered rule is a *superset*
   of the dossier's. It covers 848 of 858 entries and misses none of them on
   day one, but on day one it proposes 15 candidates where the dossier bought
   9. All six extras are traded later in the dossier, so it is not a universe
   difference. Ruled out by testing: a per-day cap, a turnover or liquidity
   gate, a "fresh breakout" requirement, and intraday-high variants of both
   legs. One untested hypothesis is a minimum-listed-history requirement —
   three of the extras had under 700 sessions of history while all nine bought
   names had at least 1535.

   *Effect:* ~9% more trades, and a correspondingly higher turnover, tax bill
   and net CAGR. The book is ~91% full most of the time, so surplus candidates
   only bite during warm-up and when ranking competes for a single freed slot.

2. **Survivorship bias.** The headline 2012-2026 run uses the *current* NTM750
   applied retrospectively, so names that delisted or fell out of the index are
   absent. This has now been quantified — see §6 — by re-running the identical
   rules on point-in-time Nifty 500 membership from 2014. The PIT store starts
   in 2014, so it cannot cover the 2012 start, and it tracks the Nifty 500
   rather than the NTM750.

3. **Adjusted prices.** Using adjusted closes means the lifetime-high and
   trailing-stop tests run on a series that is revised backwards whenever a
   dividend or split occurs. This is mildly optimistic and is the likeliest
   source of the residual exit-timing differences.

4. **The tax treatment is a simplification** — a flat 20% STCG across all 14
   years, and no LTCG exemption. Both are deliberate choices inherited from the
   reference workbook, not the statutory schedule.

5. **No regime filter, no sector cap, no liquidity floor.** The sleeve will
   happily hold 28 positions into a bear market and can concentrate in one
   industry. Mean cash of 4.4% means it is effectively always fully invested.
   The 16% trailing stop is the *only* risk control.

6. **Nothing here is walk-forward validated.** The parameters (28 slots, 16%
   stop, 15% band) came from the reference workbook. They were not re-fit, but
   neither were they chosen out of sample by this repo.

---

## 6. Point-in-time run — survivorship bias quantified

The same rules, unchanged, run against **point-in-time Nifty 500 membership**
read from the repo's `index_membership` store. A name is only buyable on days
it was actually a constituent; once held it rides to its trailing stop, because
a real book does not liquidate on an index reshuffle.

```bash
python -m backtesting.breakout_ath.run_backtest \
    --start 2014-01-01 --end 2026-09-01 --capital 500000 \
    --pit-index "Nifty 500"
```

**Universe quality.** 951 symbols were ever Nifty 500 members over the window.
837 of them have price history, giving a mean of **468 investable constituents
per session** (min 432, max 499) — roughly 94% of the index. The 114 missing
names are permanently delisted (DHFL, Andhra Bank, Bhushan Steel, Cox & Kings,
Dena Bank, Amtek Auto and similar) and are unavailable from both the bar store
and yfinance, so a small residual bias remains and it points the same way.

### Result, ₹5,00,000 start, 2014-01-01 → 2026-09-01 (12.67 years)

| Metric | Net of cost + tax | Before tax | NIFTY 50 |
|---|---|---|---|
| CAGR | **23.79%** | 25.14% | 11.17% |
| Final value | ₹74.6L | ₹85.5L | ₹19.1L |
| Absolute return | 13.9x | 16.1x | 2.8x |
| Max drawdown | −29.4% | −23.2% | −38.4% |
| Volatility | 17.0% | 15.3% | 15.8% |
| Sharpe | 1.34 | 1.55 | 0.75 |
| Sortino | 1.81 | 2.13 | 1.04 |
| Alpha (annual) | 16.4% | 18.4% | — |
| Beta | 0.66 | 0.60 | 1.00 |

Trade statistics: 1,486 fills, 729 round trips, 28 still open, **50.2% win
rate**, 160-day average hold, 26.5 mean positions, 5.6% mean cash. Brokerage
₹4.37L and capital-gains tax ₹10.93L cost a combined **1.83 percentage points
of CAGR**.

### Year by year

| Year | Portfolio | NIFTY 50 | NIFTY 500 | Universe EW |
|---|---|---|---|---|
| 2014* | +105.0% | +31.4% | +37.6% | +83.0% |
| 2015 | +6.9% | −4.1% | −0.7% | +18.7% |
| 2016 | −1.4% | +3.0% | +3.8% | +11.3% |
| 2017 | +59.0% | +28.6% | +35.9% | +61.1% |
| 2018 | −18.0% | +3.2% | −3.4% | −18.5% |
| 2019 | +19.4% | +12.0% | +7.7% | −8.4% |
| 2020 | +36.5% | +14.9% | +16.7% | +38.4% |
| 2021 | +79.5% | +24.1% | +30.2% | +60.7% |
| 2022 | −7.8% | +4.3% | +3.0% | +7.3% |
| 2023 | +66.6% | +20.0% | +25.8% | +50.1% |
| 2024 | +24.8% | +8.8% | +15.2% | +26.8% |
| 2025 | −10.9% | +10.5% | +6.7% | −2.2% |
| 2026* | +6.1% | −7.7% | −2.0% | +5.3% |

\* partial year.

### How to read this

The PIT run changes **two things at once** relative to the headline figures, so
it is not a clean bias measurement:

1. It removes survivorship bias — the intended fix.
2. It narrows the universe from NTM750 (which reaches into microcaps) to the
   Nifty 500, which is a large- and mid-cap index.

Before-cost CAGR falls from ~32% on the current-membership NTM750 to 25.1% on
the PIT Nifty 500. Both effects push the same direction, and this run cannot
attribute the gap between them. **Treat ~24% net as the defensible number and
the 30% headline as optimistic.**

What survives the change is the shape of the edge: beta stays near 0.6, the
drawdown stays materially shallower than the index, and the sleeve still beats
NIFTY 50 by roughly 12 points of CAGR with a Sharpe around twice the index.
The losing years (2018, 2022, 2025) are the same ones, and they track the
equal-weight universe rather than the cap-weighted index — which is what a
breadth-driven momentum sleeve should do.

