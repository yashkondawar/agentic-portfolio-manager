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

2. **Survivorship bias.** The universe is the *current* NTM750 applied
   retrospectively. Names that delisted or fell out of the index over the 14
   years are absent, which flatters returns. A point-in-time constituent
   history would fix this; the repo's PIT store only starts in 2014 and holds
   951 symbols, so it cannot cover the 2012 start.

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
