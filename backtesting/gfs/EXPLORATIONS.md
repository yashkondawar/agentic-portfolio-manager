# GFS — the research log

`README.md` documents **what the harness is and what the current configuration
does**. This file documents **how we got there**: every hypothesis tested, in the
order it was tested, including — especially — the ones that failed.

It exists because the failures are the more useful half. Roughly two thirds of
the ideas tried on this strategy did not work, and several of them were *good*
ideas that a reasonable person would try again in six months. Writing down only
the survivors would guarantee that.

**How to read a claim in this file.** Every number here came from the same
13.6-year window (2013-01-01 → 2026-08-21, `nifty500`, post-tax, cash at 6.5%
unless stated). That window has been looked at many times. The rule adopted
throughout is:

> A setting is accepted only if it sits on a **plateau** — neighbouring values
> also improve — and is **positive across sub-periods**. A setting is never
> accepted for topping a full-record CAGR table.

Most of the negative results below are negative *because of that rule*, not
because the number was bad.

---

## Contents

| # | Chapter | Outcome |
|---|---|---|
| 0 | [The strategy as received](#0-the-strategy-as-received) | — |
| 1 | [Does the literature support it?](#1-does-the-literature-support-it) | mixed |
| 2 | [Building a harness you can argue with](#2-building-a-harness-you-can-argue-with) | — |
| 3 | [The first honest result: no edge](#3-the-first-honest-result-no-edge) | ✗ strategy as taught |
| 4 | [The conviction study](#4-the-conviction-study-can-we-pick-winners) | ✓ headroom, ✓ wide stop, ✗ ranking |
| 5 | [Costs, taxes and idle cash](#5-costs-taxes-and-idle-cash) | ✓ cash yield |
| 6 | [Loosening the entry funnel](#6-loosening-the-entry-funnel) | ✓ `--s-rsi 43` only |
| 7 | [The weekly-breakdown exit](#7-the-weekly-breakdown-exit) | ✗ rejected |
| 8 | [Exit target: the RSI-70 question](#8-exit-target-the-rsi-70-question) | ~ unsettled |
| 9 | [The excursion study](#9-the-excursion-study-where-the-money-is-left) | ✗ killed the ratchet |
| 10 | [Risk-based sizing](#10-risk-based-sizing-is-a-leverage-dial) | ✗ not a selector |
| 11 | [Deployed capital vs. total corpus](#11-deployed-capital-vs-total-corpus) | ✓ reframing |
| 12 | [The thirds split](#12-the-thirds-split-and-the-2013-2017-hole) | ✗ found a weakness |
| 13 | [YTD 2026 and the four-month dry spell](#13-ytd-2026-and-the-four-month-dry-spell) | ✗ found a weakness |
| 14 | [Re-entry after a stop](#14-re-entry-after-a-stop) | ✗ lever is closed |
| 15 | [Decomposing the regime gate](#15-decomposing-the-regime-gate) | ✓ **breadth-only adopted** |
| — | [Scoreboard](#scoreboard) | |
| — | [What we still don't know](#what-we-still-dont-know) | |

---

## 0. The strategy as received

Stated by the user, from Indian retail trading circles:

- **G**randfather — monthly candle RSI **> 60**.
- **F**ather — weekly candle RSI **> 60**.
- Together: the stock is structurally strong.
- **S**on — daily candle RSI drops **below 40**. **This is the entry.**
- **Exit** — daily RSI recovers to 60/70, or price reaches previously identified
  resistance.
- **Risk management** — don't trade every qualifying name, allocate equally,
  don't be greedy, keep a **3–5% stop** so that "even if we lose 70% of trades,
  the 30% big winners keep us positive."
- **Top-down funnel** — global markets → Indian market → strong sector → stock.

The thesis: *a strong monthly/weekly structure will pull a temporarily weak daily
chart back up.*

Three things in that brief turned out to be wrong, and it is worth naming them
up front because chapters 3–5 are largely the story of discovering it:

1. **The 3–5% stop is the single most destructive rule in the brief.** It sits
   inside the noise of the very dip the strategy is designed to buy.
2. **The "lose 70% of trades" framing is backwards for this system.** GFS as
   built is a *high win rate, low payoff* system (win 71%, payoff 0.82), not the
   low-win-rate/big-winner system described.
3. **G and F do not select winners.** They are risk controls. Every test that
   isolated them said so.

---

## 1. Does the literature support it?

Searched before writing any code. The answer is *partly, and not for the reason
the strategy gives*.

- **Momentum** (Jegadeesh & Titman 1993) and **short-term reversal** (Jegadeesh
  1990, Lehmann 1990) are both real, heavily-replicated anomalies. GFS is a
  hand-rolled combination of the two: buy a short-term loser inside a
  medium-term winner. That combination is genuinely documented — momentum
  strategies are known to improve when you skip or fade the most recent month.
- **The specific 60/60/40 thresholds are folklore.** No source. They circulate
  as a Chartink screener.
- **Multi-timeframe RSI as such has no academic standing.** RSI is a bounded
  oscillator; "RSI > 60 on the monthly" is a coarse proxy for "12-month price
  momentum is positive," which is the actual documented effect.

So the harness was built to test a plausible mechanism with an arbitrary
parameterisation — which is precisely the situation where in-sample tuning is
most dangerous, and is why the plateau rule above exists.

---

## 2. Building a harness you can argue with

Design decisions made before any result was produced, so they could not be
chosen to flatter an outcome. Details in `README.md`; the reasoning is here.

**Leak-free higher timeframes.** The hardest correctness problem in the whole
project. On day *T* inside an unfinished month, what is "the monthly RSI"? Two
defensible answers, and they differ by half the return:

- `closed` — use only the last *completed* monthly candle. Causally clean.
- `live` — use the in-progress candle, which is what a trader actually sees.

`live` drops CAGR from 11.7% to 5.8%. **Published GFS backtests almost certainly
use `closed` without saying so, and present it as a live-tradeable result.** The
harness implements both and prints which one it used.

**Vectorised, cached panels.** Every indicator is computed once per symbol into a
`SymbolPanel`, keyed by `base_panel_key` — which contains the RSI/ATR periods and
lookbacks but *not* dates and *not* thresholds. This is why a 20-candidate ×
4-window sweep costs ~13 minutes instead of hours: one expensive pass serves
every threshold/exit/sizing/regime variant. Only changing an indicator *period*
invalidates it.

**A future-data test as a first-class test.** `test_appending_future_data_does_not_change_the_past`
appends bars after the test window and asserts the trade list is byte-identical.
This has caught real bugs.

**Null models, not just backtests.** A random-entry Monte Carlo (same universe,
same holding periods) and a portfolio-free forward-return study. The second is
the important one: it measures the *signal* with no position sizing, no gates and
no capacity limits, so it cannot be rescued by portfolio construction.

**Biases stated in the output, not the docs.** `universe_bias_note()` prints the
survivorship/index-inclusion caveat with every run so it cannot be quietly
dropped when someone pastes a result into chat.

---

## 3. The first honest result: no edge

Run as taught: 2×ATR stop, RSI-65 exit, 60-day time stop, 2018–2024.

| | Nifty 500 | Nifty 100 | NSE all |
|---|---|---|---|
| CAGR | +11.7% | +2.8% | +12.0% |
| benchmark | +12.4% | +12.4% | +12.4% |
| Monte Carlo | 99.6th ✓ | 52.4th ✗ | 80.4th ✗ |

**Every headline test failed:**

- **Forward returns were negative** at 5/10/21 days on the Nifty 500 and
  *significantly* negative on `nse_all` (−0.31% at 5d, t = −2.08; −0.45% at 10d,
  t = −2.18). Stocks meeting the GFS condition underperformed in exactly the
  window the strategy claims to profit from.
- **Deflated Sharpe Ratio 0.0** across a 324-configuration walk-forward. Two of
  three test folds lost money; one fold (+62%) carried everything.
- **The defining thresholds were unstable.** `g_rsi_min` and `f_rsi_min` picked a
  different optimum in each of three folds — 33% agreement. *A parameter with no
  stable value is not a parameter, it is noise.* The only 100%-stable parameter
  was `atr_stop_mult`, i.e. the risk control.
- **Win rate 42–47%.** Public GFS claims are 70–80%. Nothing produced that.

**The ablations then said something more interesting than "it doesn't work":**

| ablation | CAGR | MaxDD | reading |
|---|---|---|---|
| baseline | 11.7% | −14.4% | — |
| remove G+F | 12.2% | −28.3% | **G+F is a risk control, not a return generator** |
| remove the daily dip | 6.1% | −27.7% | **the dip is the load-bearing leg** |
| remove the sector gate | 14.0% | −34.4% | biggest single drawdown lever |
| random ranking | 12.6% | −15.7% | **ranking adds nothing** |
| tight % stop | 10.5% | −11.4% | win rate collapses 46.8% → 30.4% |

Verdict at this stage: *a reasonable risk-managed swing framework wearing a
multi-timeframe RSI costume, where the costume is the least useful part.*

**This section is still accurate for those settings.** It is what the next
chapter partially overturns.

---

## 4. The conviction study: can we pick winners?

The user's response to chapter 3 was the right one: *"I know this strategy works.
I want a 70–80% win rate. Find what separates the winners."*

`conviction.py` was written to answer it properly. It simulates **every** GFS
signal as a standalone trade — ~1,030 signals instead of the ~240 the portfolio
has room for — and splits chronologically so a rule chosen on early years is
scored on later ones.

### 4a. 24 features screened. 23 failed.

120 quintile comparisons plus 6,329 two-feature conjunctions. The script prints
both counts deliberately, because *the best of that many looks good by chance*.

- `sector_rs`, `breadth_pct`, `atr_pct`: **excellent in-sample, inverted
  out-of-sample.** Textbook overfitting.
- Best two-feature rule: **76.6% train → 59.5% test**, bootstrap CI 34.9–74.6%.
  A fitted rule, not a discovery.

### 4b. `headroom_pct` — the one survivor

Distance from the entry close to the resistance level the exit targets.
Monotonic on **both** halves:

| `headroom_pct ≥` | train win | test win | test ExpR |
|---|---|---|---|
| 0 | 45.0% | 49.8% | +0.356 |
| 15 | 52.6% | 51.3% | +0.433 |
| 20 | 56.4% | 57.5% | +0.653 |
| 30 | 62.5% | 64.1% | +0.884 |

It survived because the reason is **mechanical, not statistical**: the exit is
defined at resistance, so *a dip with the prior swing high 3% overhead cannot pay
for its own stop.* No amount of higher-timeframe strength fixes a trade with
nowhere to go.

This is the **only finding in the entire project with genuine out-of-sample
support.** Everything else was chosen on the full record.

### 4c. The win rate was never a property of the signal

The `--grid` sweep holds the entry population **completely fixed** and varies
only exit geometry:

| win rate (%) | exit RSI 55 | 60 | 65 | 70 |
|---|---|---|---|---|
| stop 1.0×ATR | 35.3 | 31.6 | 27.7 | 26.3 |
| 2.0×ATR | 57.9 | 53.6 | 47.4 | 44.6 |
| 3.0×ATR | 71.1 | 69.2 | 62.8 | 56.7 |
| 4.0×ATR | 73.8 | **74.6** | 71.1 | 64.7 |

**Win rate moves from 26% to 75% without changing a single stock bought**, while
expectancy stays in a 0.07–0.39 R band with no relationship to it.

Two consequences:
1. **Any GFS win rate quoted without its stop width is meaningless.** The public
   70–80% claims are reachable this way while making money in a completely
   different manner than advertised.
2. The user's 70–80% target was achievable — but not by selecting better stocks.

### 4d. The 3–5% stop was destroying the strategy

- Median MAE of eventual **winners**: **−5.02%**
- Winners that first fell >3%: **68.5%**
- Winners that first fell >5%: **50.6%**

**A 5% stop liquidates half the winners before they work.** And widening the stop
improved *drawdown* too, which is the opposite of what a stop is supposed to do —
because premature stops force re-entry at worse prices.

| `atr_stop_mult` | win rate | CAGR | MaxDD |
|---|---|---|---|
| 2.0 | 49.8% | +6.98% | −23.4% |
| 3.0 | 66.7% | +13.34% | −17.2% |
| **3.5** | **70.4%** | **+14.16%** | **−17.5%** |
| 4.0 | 72.5% | +14.14% | −21.4% |
| 4.5 | 73.3% | +14.22% | −23.6% |

3.0–4.5 is a **plateau**, which is what distinguishes it from the tuned
parameters that failed walk-forward in chapter 3.

### 4e. What actually changed the result

Three things, and the third was almost missed:

1. **No time stop.** Improved every metric alone. (The user had explicitly asked
   for no time-based exit; this confirmed it independently.)
2. **The headroom filter.** 63-day forward-return edge went from +0.50%
   (t = 1.06, noise) to **+1.59% (t = 3.08)** — the first time in the project the
   *signal itself* cleared significance.
3. **Redeploying the freed capital.** Filtering cut exposure from 29% to 16% and
   CAGR initially *fell* despite better trades, because the money sat idle. Four
   positions at 30% each restored it.

Point 3 is a recurring theme: **in a strategy this lightly deployed, any filter
that improves trade quality can still lose money.** Half the negative results in
this document are that effect.

---

## 5. Costs, taxes and idle cash

### 5a. The biggest correction was not tax

The strategy is only **~40% deployed**. Signals are scarce. The default
assumption — idle cash earns 0% — is *not neutral*: the benchmark is 100%
invested by construction and never pays that penalty. A zero cash return quietly
hands the comparison to buy-and-hold.

Modelling a liquid fund at 6.5%:

| | cash at 0% | cash at 6.5% |
|---|---|---|
| CAGR after tax | +12.65% | **+15.02%** |
| Sharpe | 0.98 | **1.23** |
| Longest underwater | 570 sessions | **328 sessions** |

It does not improve a single trade — the trade list is byte-identical. It removes
an accounting artefact. `cash_yield_pct` defaults to **0** so older numbers still
reproduce.

### 5b. Taxes cost less than feared — because turnover is low

Full Indian stack in `taxes.py`: STT, stamp duty, exchange charges, SEBI fee,
brokerage, 18% GST on broker-side fees only. Capital gains per financial year,
STCG 15% → 20% on 23 July 2024, loss set-off and carry-forward.

The comparison is deliberately unflattering: buy-and-hold is taxed **once at
exit** and compounds untaxed for 13 years; the strategy pays **annually**.

```
gross +16.73% | after charges +16.19% (−0.53pp) | after tax +14.81% (−1.38pp)
```

Total drag **1.91pp**. Mild only because turnover is ~16 trades/year at ~36 days.
**This is a direct function of trade count**, so any change that multiplies
turnover has to clear a far higher bar. Essentially nothing reaches LTCG (0.0% of
trades held > 1 year), and attempts to engineer that were counterproductive (5c).

### 5c. Exit modes tried and rejected

| dial | post-tax CAGR | verdict |
|---|---|---|
| `--exit-mode trail` | **+2.79%** | **destroys the strategy** (38.8% win, −40% DD) |
| `--exit-mode scale_out` | +10.49% | fixes payoff (0.87 → 1.39), costs return |
| `--rank-by headroom` | +11.44% | **hurts** |
| `--rank-by reward_risk` | +12.36% | no better than composite |

**Pure trailing exits destroy it.** The RSI target exit is load-bearing. This also
closed off the tax idea of letting winners run into LTCG: the mechanism that
would extend holdings is the same one that removes the edge.

**`scale_out` is the payoff/win-rate trade in its purest form** — payoff 1.39,
expectancy doubled to 0.430 R, win rate 74.2%, and *still earns less*, because
booking half a position early leaves even more capital idle in a strategy that is
already under-deployed.

**Ranking is still ≈ random**, and `RANK_HEADROOM` — the feature that survived
the conviction study as a *filter* — actively hurts as a *ranking key*. Worth
internalising: **a variable can be informative about whether to trade at all and
uninformative about which of two qualifying trades is better.** Different
questions; the answer to one does not transfer.

### 5d. Concentration, not diversification

| slots × size | CAGR | ExpR | Sharpe | exposure |
|---|---|---|---|---|
| 3 × 35% | +12.67% | 0.183 | 0.88 | 45.6% |
| **4 × 30%** | **+12.57%** | 0.199 | 0.98 | 41.7% |
| 6 × 20% | +10.35% | 0.193 | 0.98 | 33.6% |
| 8 × 15% | +9.29% | **0.221** | **1.05** | 27.7% |

Read the right columns against the left: spreading wider makes every *trade
statistic* better and the *portfolio* worse, monotonically. **There are not
enough signals to fill eight slots**, so extra slots do not add positions — they
only shrink the ones you get.

---

## 6. Loosening the entry funnel

Question: *are the filters throwing away trades that would have helped?*

### 6a. First, a noise floor

`--sector-top-n 11` vs `12` differ by **two trades out of 279** and **0.71pp of
CAGR**. That calibrates everything else: **differences below ~1pp are not
evidence.** Several results below sit inside that band and are recorded only so
they are not re-tested later.

### 6b. Throttles vs. selectors — the trap

| dial loosened | exposure | ExpR | Sharpe | reading |
|---|---|---|---|---|
| `--sector-top-n` 3 → 12 | 28.5% → 50.8% | 0.186 → 0.221 (no trend) | flat | pure **throttle** |
| `--s-rsi` 35 → 50 | 18.8% → 58.2% | 0.322 → 0.152 (falls) | 1.54 → 1.00 | genuine **selector** |

The sector gate does not pick better trades; it meters capital. The daily-RSI
threshold visibly changes what is bought. Conflating the two is how you convince
yourself a beta bet is an edge — which is exactly what happened next.

### 6c. The split test, which settled it

On the full record `--sector-top-n 9..12` looked like a genuine four-value
plateau at ~+16.7% — better than the default's +14.81%. Splitting at 2019-09-01:

| config | H1 2013-19 excess | H2 2019-26 excess | H1 exposure |
|---|---|---|---|
| recommended (top 5) | −0.04% | +4.08% | 31.3% |
| `--sector-top-n 12` | **−2.96%** | +11.82% | 45.4% |
| `--sector-top-n 10` | **−2.96%** | +10.63% | 41.2% |
| `--min-headroom-pct 5` | **−2.09%** | +3.37% | 32.3% |

**The variants that top the full-record table are the worst in the first half.**
They deploy more capital, and the second half contained 2020–2024. *That is a
beta bet wearing the costume of an edge, and full-record CAGR cannot tell them
apart.*

The same test **indicts the recommended config**: H1 excess **−0.04%**. For seven
years the strategy returned what the index returned — at 31% exposure with
Sharpe 1.17 against an index that drew down 38%, which is defensible, but it is
not the +4% the headline implies.

### 6d. The one loosening that survived: `--s-rsi 43`

| `--s-rsi` | H1 excess | H2 excess | full post-tax | Sharpe |
|---|---|---|---|---|
| 35 | −1.00% | −2.11% | +10.91% | 1.54 |
| **40 (taught)** | **−0.04%** | **+4.08%** | +14.81% | 1.25 |
| **43** | **+2.18%** | **+9.15%** | **+18.54%** | **1.30** |
| 45 | +1.38% | +7.36% | +17.12% | 1.20 |
| 48 | +1.25% | +3.42% | +14.89% | 1.05 |
| 50 | −2.61% | +8.22% | +15.44% | 1.00 |

**Three adjacent values improving both halves is the plateau argument.** The peak
at 43 alone would not have been worth acting on.

The mechanism is plausible rather than mysterious: **RSI 40 on a daily chart is a
rare event in a stock whose monthly and weekly RSI are both above 60**, because
such a stock is by construction not falling much. Demanding 40 discards most of
the pullbacks the strategy exists to buy. 43 is still a real dip.

*Caveat: the split was used to **choose** 43, so this is a consistency check, not
a clean holdout. Prefer the region 43–45 to the point estimate.*

### 6e. Loosenings rejected

| dial | result | why |
|---|---|---|
| `--min-headroom-pct` 5 / 0 | +13.30%, 3 neg. years | worse in both halves; the one filter with OOS support |
| `--no-sector-filter` | +13.88% | worse than the gate at any setting |
| `--min-breadth` 20/30/35 | +15.02/+15.22/+15.06% | inside noise; barely binds below 40 |
| `--g-rsi` 55 / 50 | +15.43/+15.36% | inside noise — **the Grandfather leg is nearly non-binding** |
| `--f-rsi` 55 / 50 | +14.89/+15.60%, DD −25.1/−23.2% | flat return for 6–8pp more drawdown |
| `--trigger recross` | +6.46% | waiting for the recross forfeits the entry price |
| `--max-per-sector 3` | +11.70%, DD −24.77% | the cap at 2 is doing real work |
| `--sector-lookback 126` | +12.46%, 4 neg. years | 63 sessions is the better RS window |

Two notes worth carrying forward. **`--g-rsi` barely matters** because a stock
with weekly RSI > 60 almost always has monthly RSI > 60 — the Grandfather is
largely *redundant* with the Father. Worth knowing before defending the
three-timeframe story too hard. And **loosening the Father raises drawdown
sharply without raising return** — consistent with stops nearly always being
accompanied by a weekly RSI breakdown, which motivated chapter 7.

---

## 7. The weekly-breakdown exit

**A good hypothesis that the base rates killed.** Written up at length because the
general lesson outlives the specific rule.

The trade log made it look obvious. On nearly every stop-loss exit the weekly RSI
had collapsed mid-trade after being intact at entry: WIPRO 67→45, ADANIENT 63→37,
COLPAL 77→44, ENDURANCE 60→37. The losses looked like *the Father failing*.
Cutting on that should shrink the average loss and fix the 0.82 payoff ratio.

`--exit-f-rsi N`: leave when weekly RSI falls below N, regardless of P&L. Neither
a stop nor a target — it fires because *the reason for holding stopped being
true*.

| `--exit-f-rsi` | payoff | win rate | ExpR | post-tax CAGR |
|---|---|---|---|---|
| off | 0.82 | 71.7% | +0.203 | **+18.54%** |
| 45 | 0.91 | 69.2% | +0.197 | +18.23% |
| 50 | 1.08 | 61.2% | +0.139 | +13.44% |
| 55 | **1.50** | 49.2% | +0.084 | +8.67% |

**It did exactly what it was designed to do and still lost.** The payoff ratio
improves monotonically — the mechanism is real — while expectancy falls the whole
way. Mirror image of `scale_out`: **win rate and payoff are two ends of one dial,
and moving either end does not change the product.**

### Why — measured, not assumed

Lowest weekly RSI reached between entry and exit:

| weekly RSI floor | winners (n=200) | losers (n=79) |
|---|---|---|
| dipped below 55 | 39.0% | 82.3% |
| dipped below 50 | 18.0% | 59.5% |
| dipped below 45 | 4.5% | 20.3% |
| **median floor** | **56.6** | **48.9** |

**The signal is genuinely informative** — a loser is 3.3× more likely to breach
50, median floors 8 points apart. The original observation was correct. **The base
rates defeat it:** at a 71.7% win rate there are 200 winners to 79 losers, so a
3.3:1 likelihood ratio still means an exit at 50 cuts **47 losers and 36 winners
— 43% friendly fire.**

And the errors are **asymmetric**. A winner cut on a weekly breakdown is cut
*near its low*, forfeiting the entire recovery that made it a winner. A loser cut
on the same signal only saves the sliver between the breakdown and the ATR stop
that was going to catch it anyway. **So even at equal counts the rule loses
money.**

> **The transferable lesson:** *at a high win rate, an exit filter needs
> specificity far beyond "statistically significant" to pay for itself.* Any
> future exit idea should be checked against a winner/loser overlap table
> **before** it is backtested.

The flag stays in the codebase, defaulted off, because the negative result is
worth keeping.

---

## 8. Exit target: the RSI-70 question

The exit level is the one parameter with support from *outside* this dataset: it
was the modal choice in the chapter-3 walk-forward sweep, with 66.7% fold
agreement — second only to the ATR multiplier.

Raising the target from 60 to 70 on the full record:

| | exit 60 | **exit 70** |
|---|---|---|
| post-tax CAGR | +18.54% | **+21.50%** |
| Sharpe / Sortino | 1.30 / 1.97 | **1.31 / 1.95** |
| Max drawdown | −19.67% | −23.39% |
| Trades | 279 | 181 (13.3/yr) |
| Win rate | 71.68% | 63.54% |
| Payoff | 0.82 | **1.37** |
| ExpR | +0.203 | **+0.428** |
| Avg hold | ~36d | **66.0d** |

This is the only change found that improves **payoff and expectancy together**,
rather than trading one for the other. It also halves the trade count, which
matters for the tax stack (5b). Thirds split: T1 −1.14, T2 +8.97, T3 +17.69.

**But it is now under a cloud, and the doubt came from live-ish data.** See
chapter 13: in YTD 2026 exit-70 **lost to exit-60 by 4.8pp**, with CUB alone a
20.9pp swing (+6.91% booked at RSI-60 vs **−13.98% stopped** at RSI-70). n=7 is
an anecdote, not evidence — but it is *exactly the predicted failure mode* of a
higher target in a falling market: the target is never reached, so the trade
rides down to the stop instead of booking a profit it had.

**Status: 68–72 is defensible on the long record; treat it as a preference, not a
settled result.** The doubling of holding period is the real risk — it is what
converts "target not reached" into "stopped out."

---

## 9. The excursion study: where the money is left

A pure EDA pass (`metrics.py` excursions), asking what the winners and losers
*look like* while open, to generate exit hypotheses.

| | winners | losers |
|---|---|---|
| capture of best move (exit ÷ MFE) | **74.2%** | — |
| ever showed a profit | — | **essentially never** |

Two findings, one useful and one that closed a door:

**Winners capture only 74.2% of their best move.** A quarter of every winner's
peak gain is handed back. That looks like an obvious inefficiency — hence the
appeal of trailing stops and breakeven ratchets.

**Losers never show a profit worth protecting.** This is the finding that
matters, and it **structurally dooms the breakeven ratchet.** The idea — "once a
trade is up 1R, move the stop to breakeven so it can't become a loser" — requires
that losers *first go up*. They don't. So the ratchet can only ever fire on
trades that were going to win anyway, where its sole effect is to stop some of
them out early.

Tested and confirmed: `move_stop_to_breakeven_at_r` is **inert** at every setting
that doesn't hurt. It changes nothing until it is tight enough to start cutting
winners, at which point it only loses. Kept in the code, defaulted off.

Combined with chapter 5c (`trail` destroys the strategy at +2.79%), this closes
the entire family of "protect the open profit" ideas. **The 25.8% given back is
the price of the RSI target exit, and every attempt to reclaim it has cost more
than it recovered.**

---

## 10. Risk-based sizing is a leverage dial

`SIZING_RISK` sizes each position by distance-to-stop rather than equally. The
appeal: it attacks the payoff ratio through *position size* instead of exit
timing — the one route chapters 5c and 7 did not try.

It looked good. Then the exposure column was read.

Varying `--risk-per-trade-pct` moves return and drawdown **together, in fixed
proportion**, because it moves *exposure*. At 6% it produced +21.50% CAGR — but
the equal-weight config produced the same thing at the same exposure. **It is a
leverage dial, not a selection mechanism.** It does not choose better trades or
size winners larger than losers; it just scales the book.

That is not useless — a leverage dial is a legitimate control — but it must not
be reported as an edge, and it should be set from risk tolerance, not from a CAGR
table.

---

## 11. Deployed capital vs. total corpus

The user pointed out something that changes the correct denominator: **"I will be
using this strategy alongside others. My money will never be idle."**

If true, reporting returns on the full corpus understates the strategy, because
it charges GFS for cash it is not using and someone else is.

| basis | return |
|---|---|
| on the total corpus | **+21.50%** CAGR |
| on capital actually at work | **+44.5%** |
| average exposure | 58.1% |

The gap is large. Two things keep it honest:

1. **Exposure is bimodal, not steady.** The strategy is not "58% invested"; it is
   near-fully invested or near-fully in cash, in long stretches. In 2026 it was
   **100% cash from 17 April onward** (chapter 13). A co-strategy has to absorb
   *lumpy* capital returns, not a smooth 42% float.
2. **Correlation with the market is 0.649 when deployed.** GFS deploys when
   breadth is good — which is when other long strategies also want capital.
   **The cash is freed when everything else wants it least.** The diversification
   benefit is worth less than the exposure number suggests.

So `+44.5%` is the right number for "is the capital well used when used" and the
wrong number for "what will my account do." Both belong in any honest report.

---

## 12. The thirds split, and the 2013–2017 hole

Splitting into three ~4.5-year periods and requiring positive *excess* in all
three. Excess CAGR vs benchmark:

| window | exit60 | exit70 | exit70+risk6 | bench |
|---|---|---|---|---|
| T1 2013-2017 | −2.91 | **−1.14** | −0.38 | 10.11 |
| T2 2017-2022 | +5.75 | +8.97 | +7.76 | 12.34 |
| T3 2022-2026 | +14.13 | +17.69 | +17.69 | 6.34 |

**T1 is negative-excess for every variant tested.** This is the same finding as
the H1/H2 split in 6c, at higher resolution, and it is the most important
qualification on every number in this document: *the strategy's excess return is
concentrated in the second half of the record.*

Note what T1 and T3 have in common in the benchmark column: T1 was a **strong**
index (+10.11%) and T3 a weak one (+6.34%). GFS is under-deployed and defensive;
it cannot keep up with a strong index. **The excess is largely a function of how
badly the index does.** That is a real property, not a flaw — but it means "beats
the index" and "makes money" are different claims here.

### The RSI period sweep

The core parameter of the entire strategy, never varied until this point:

| RSI period | post-tax CAGR |
|---|---|
| 7 | +20.12% |
| 9 | +16.55% |
| **14 (default)** | **+21.50%** |
| 21 | +10.15% |

**14 is both the peak and the untouched default**, so there is no fitting concern
here — this is the one sweep that could only have produced bad news and didn't.

---

## 13. YTD 2026 and the four-month dry spell

Data through 2026-08-21.

| | YTD | vs index | maxDD | avg exposure |
|---|---|---|---|---|
| NIFTY 500 buy & hold | **−7.19%** | — | −15.18% | — |
| exit-60 | **+6.99%** | +14.17pp | −5.57% | 21.4% |
| exit-70 | +2.23% | +9.41pp | −11.15% | 22.1% |

Beating a falling index by 9–14pp looks excellent. **Decomposing it is
sobering:** of exit-70's +2.23%, roughly **+2.0pp is liquid-fund interest** and
Jan–Apr trading added ~+0.2pp. Monthly returns May→Aug are `+0.48 / +0.53 /
+0.58 / +0.38` — that is a 6.5% annual cash yield and nothing else. **Zero
positions since 17 April.**

### Why the book was shut: the diagnostic

| month 2026 | regime open | breadth |
|---|---|---|
| Jan | 55% | — |
| Feb | 70% | — |
| Mar–Aug | **0%** | 26.9% → 49.6% → **59.7%** |

**Breadth had recovered fully by August. The benchmark's 200-DMA had not.** The
regime gate ANDed the two, so the lagging leg held the book closed for five
months while qualifying setups sat there — 6 on 13 May, 4 on 11–12 May.

Full-run rejection tally: capacity 4353, **regime_closed 1278**, sector_weak
1105, sector_cap 34.

This diagnostic is what motivated chapter 15, and it is the clearest example in
the project of *why you look at a losing stretch instead of averaging over it*.

---

## 14. Re-entry after a stop

Listed in the README as an untested lever: *"a stopped-out name is currently gone
for good even when the thesis never broke."*

### 14a. The premise was wrong — twice

Reading the code before running anything found two errors in my own framing:

1. `s_dip` is a **level** test (`rsi_d <= 43`), not a cross. There is a separate
   `s_recross` for the cross variant.
2. The engine only skips symbols **currently held** (`engine.py:296`). There is no
   cooldown, no blacklist. **Re-entry after a stop was always mechanically
   allowed.**

So the lever did not exist as described. But the data agreed something was
blocking it: 35 same-symbol consecutive pairs, 11 after a stop, and **zero
re-entries within 90 days**.

### 14b. The diagnostic — the valuable part

For each of 66 stopped trades, walk 60 sessions forward and record which
precondition is false.

| what's false the day after a stop | count | share |
|---|---|---|
| **Father leg only** (weekly RSI < 60) | 48 | **73%** |
| both G and F | 13 | 20% |
| tradable | 5 | 8% |

Across the full 60-session window: `gf_ok` false **93.0%**, F specifically
**91.9%**, `s_dip` false 59.7%, G false 52.8%.

Day-after-stop RSI levels:

| leg | mean | share still qualifying |
|---|---|---|
| monthly (G) | **66.4** | 77% ≥ 60 |
| weekly (F) | **46.4** | **1.5% ≥ 60** |
| daily (S) | **31.8** | deeply oversold |

**Re-qualified within 60 sessions: 1 of 66 (2%)**, at day 54.

Read that table again: the Grandfather still says strong, the Son is deeply
oversold — *the textbook GFS setup* — and it is refused because the Father broke.

### 14c. The latch — and why it failed

Natural fix: hysteresis. Arm at weekly RSI 60, stay eligible while it holds above
a lower floor, so a name is not disqualified by *the very dip the strategy buys*.
Implemented as `f_rsi_hold`.

| variant | CAGR | Sharpe | DD | expo | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| **strict F (base)** | **+21.50** | **1.31** | **−23.39** | 58.1 | −1.14 | +8.97 | +17.69 |
| F hold 57 | +11.97 | 0.84 | −32.28 | 61.1 | −4.86 | −1.54 | +4.25 |
| F hold 55 | +13.15 | 0.86 | −29.56 | 66.1 | −6.20 | −0.42 | +9.64 |
| F hold 52 | +15.79 | 0.96 | −30.74 | 67.9 | −4.10 | −3.14 | +11.21 |
| F hold 50 | +15.21 | 0.95 | −32.60 | 67.9 | −4.39 | −1.64 | +7.54 |
| F hold 47 | +19.98 | 1.16 | −28.23 | 68.1 | −2.96 | +3.11 | +12.49 |
| F hold 45 | +18.61 | 1.12 | −30.83 | 69.4 | +1.49 | +0.25 | +7.05 |
| F hold 40 | +18.26 | 1.09 | −27.44 | 72.8 | +0.87 | −5.96 | +12.07 |
| *plain* f-rsi 45 | +17.22 | 1.08 | −32.84 | 70.8 | +2.13 | −5.52 | +9.37 |

**Every variant loses CAGR, Sharpe and drawdown.** No plateau — 57/55/52/50 are
bad, 47 pops, 45/40 sag. That shape is noise.

The decisive argument is the last row: **`F hold 45` (+18.61) barely beats
`plain --f-rsi 45` (+17.22).** The latch mechanism adds ~1.4pp over simply
*lowering the threshold*. It is not a new idea — it is a slower way to weaken the
Father leg.

**Conclusion: the strict Father leg is load-bearing.** 2015 alone is +19.9% at
base against −5% to −14% for holds 57–50. The lever is closed. The code was
removed rather than defaulted off, because unlike `--exit-f-rsi` there is no
version of it worth having.

---

## 15. Decomposing the regime gate

**The one change adopted this round.** Motivated by chapter 13: the gate was two
conditions ANDed together, and one of them had held the book shut for five months
while the other said go.

### 15a. Every single-leg variant beats the AND on robustness

| variant | CAGR | Sharpe | DD | expo | win% | n | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|---|---|
| both legs (old default) | +21.50 | 1.31 | **−23.39** | 58.1 | 63.54 | 181 | **−1.14** | +8.97 | +17.69 |
| **breadth ≥40 only** | +20.94 | 1.27 | **−23.40** | 64.4 | 62.63 | 198 | **+1.19** | +10.32 | +13.78 |
| breadth ≥45 only | +20.32 | 1.23 | −25.08 | 62.2 | 63.30 | 188 | +0.12 | +9.61 | +13.69 |
| breadth ≥50 only | +20.06 | 1.27 | −32.71 | 57.6 | 63.64 | 176 | −0.92 | +8.32 | +14.40 |
| breadth ≥55 only | +14.91 | 1.07 | −41.71 | 54.1 | 62.50 | 152 | −2.60 | +7.43 | +3.47 |
| index 200-DMA only | +21.23 | 1.28 | **−21.75** | 61.3 | 62.30 | 191 | +1.25 | +7.21 | +16.40 |
| index 100-DMA + br40 | +22.64 | **1.42** | −40.09 | 57.2 | 64.91 | 171 | −0.64 | +12.52 | +16.38 |
| no gate at all | **+23.77** | 1.28 | −28.72 | **76.4** | 62.50 | 232 | +5.85 | +11.48 | +16.88 |

**The AND of both legs is the only configuration that loses a third.** Every
single-leg and no-gate variant is positive across all three sub-periods.

Breadth 40→45→50 is a gentle decline and 55 falls off a cliff — a plateau at the
loose end, which is the right shape for a filter that should only catch extremes.

### 15b. "No gate" is leverage, not edge

`no gate` tops the table at +23.77%. It also runs at **76.4% exposure** against
58.1%. Matching exposure by cutting position count/size separates the two:

| variant | CAGR | DD | expo | **CAGR/expo** | Calmar |
|---|---|---|---|---|---|
| **base (gated)** | +21.50 | −23.39 | 58.1 | **0.370** | **0.92** |
| breadth40 only | +20.94 | −23.40 | 64.4 | 0.325 | 0.90 |
| no gate 4×30 | +23.77 | −28.72 | 76.4 | 0.311 | 0.83 |
| no gate 4×22 | +21.88 | −25.81 | 68.1 | 0.321 | 0.85 |
| **no gate 3×25** | **+18.08** | −27.63 | **60.7** | 0.298 | 0.65 |
| breadth40 3×40 | +20.52 | −36.32 | 67.0 | 0.306 | 0.56 |

**At matched ~60% exposure the gate-free version returns +18.08% against the
gated +21.50%.** The gated config has the highest return-per-rupee of anything
tested. This matters specifically because the user runs GFS alongside other
strategies (chapter 11), so freed cash is not idle — which makes
return-per-rupee-deployed the right objective, not raw CAGR.

### 15c. The decision

**Adopted: breadth-only, default `--regime-mode breadth`, `--min-breadth 40`.**

It costs **0.56pp of CAGR** and buys:
- **identical drawdown** (−23.40 vs −23.39),
- **+6.3pp exposure** (64.4% vs 58.1%),
- and **turns T1 from −1.14 to +1.19**, so no sub-period loses.

Given the plateau rule, a config that is positive in all three thirds beats one
that is 0.56pp better overall and negative in one.

**The 200-DMA leg is kept as `--regime-mode breadth+sma`**, not deleted, because
of a caveat that must not be lost:

> **The sample starts in 2013. There is no 2008 in it.** The 200-DMA's real value
> is a slow grinding bear market, and the record contains none. In 2020's V-shaped
> crash it *cost* money (+31.6% gated vs +47.9% ungated) because it re-admitted
> capital far too late. **Removing it is a bet that future crashes look more like
> 2020 than 2008.** If you believe otherwise, switch it back on — it is one flag.

Key years for the two modes:

| | 2015 | 2018 | 2020 | 2022 | 2025 | 2026 YTD |
|---|---|---|---|---|---|---|
| both legs | +19.9 | +13.2 | +31.6 | **+40.3** | −2.4 | +2.2 |
| **breadth only** | **+28.7** | **+16.9** | **+34.1** | +30.7 | −2.4 | **+5.3** |
| no gate | +28.6 | **−0.2** | **+47.9** | **+45.7** | −5.8 | +5.7 |

Note 2018: **the no-gate column is the one that gives it back.** Some gate is
clearly necessary; the question was only which leg.

---

## 16. The after-tax number

Every figure in the chapters above is quoted **before capital-gains tax**. That
was fine for comparing rules against each other, but it is not what lands in the
account. Building the results dossier (`run_dossier.py`, see
[DOSSIER.md](DOSSIER.md)) forced the question.

Tax is charged the way it is actually levied: assessed per Indian financial year,
with short-term losses set off against gains and the remainder carried forward,
and **debited from cash each April**. That last part is the bit that cannot be
approximated by subtracting a percentage at the end - tax paid in year three is
capital that never compounds in year four.

Full NIFTY 500, 2016-01-04 → 2026-08-31, ₹1 crore, 485 names:

| | CAGR | Max DD | Sharpe | Final value |
|---|---|---|---|---|
| Before cost & tax | 26.97% | −24.5% | 1.37 | ₹12.73 cr |
| Before tax | 26.09% | −23.4% | 1.32 | ₹11.82 cr |
| **Net of cost + tax** | **22.96%** | **−26.3%** | **1.18** | **₹9.05 cr** |
| NIFTY 50 | 11.17% | −38.4% | 0.75 | ₹3.09 cr |

**Frictions cost 4.01% a year**, of which brokerage and slippage are only ₹16.9
lakh against ₹1.24 crore of tax. The edge survives comfortably, but any GFS
number quoted above this chapter is overstating the outcome by roughly four
points of CAGR.

### Why GFS is taxed badly

**Long-term gains are zero in every single financial year.** Average holding is
62 days; nothing has ever crossed the 365-day line. GFS is taxed entirely at the
short-term rate (20% post-July-2024, 15% before), and gets no benefit from the
₹1.25 lakh long-term exemption. This is structural to a mean-reversion strategy
with an RSI-70 exit, not a data artefact — and it is the single largest argument
for pairing GFS with a long-horizon strategy rather than running it alone.

### Two findings worth keeping

**Rolling five-year windows never lose to the index.** Across 68 overlapping
5-year windows, the net-of-tax portfolio beat the NIFTY 50 in *all 68*. Its worst
window still returned +17.0% CAGR; the index's worst was +8.5%. Given how much of
chapters 8-15 was spent worrying about sub-period fragility, this is the most
reassuring single statistic in the file.

**Beta of 0.45 is not defensiveness.** It is an artefact of sitting in cash 36%
of the time. Do not read it as a low-volatility characteristic of the holdings.

### A bug this chapter exists to record

The closing financial year's tax bill falls due the *following* April — after the
backtest ends. The first implementation therefore reported the last year's gains
in the ledger but never deducted them from equity. That silently inflated final
value by **36% of the entire tax bill**. The engine now forces a settlement on
the final session. It is exactly the class of error that only appears in a branch
that never runs during normal use, and `tests/test_gfs_dossier.py` now asserts
tax paid equals tax assessed.

---

## Scoreboard

### Adopted

| change | evidence | chapter |
|---|---|---|
| No time stop | improved every metric alone | 4e |
| `--min-headroom-pct 10` | **replicated out-of-sample**, mechanical reason | 4b |
| `--atr-mult 3.5` | 3.0–4.5 plateau; tight stops cut half the winners | 4d |
| 4 positions × 30% | signals too scarce to fill more slots | 5d |
| `--cash-yield-pct 6.5` | removes an accounting artefact; trade list unchanged | 5a |
| `--s-rsi 43` | 43–48 positive in both halves; plausible mechanism | 6d |
| `--exit-rsi 70` | only change to lift payoff *and* expectancy — **but see ch. 8** | 8 |
| **`--regime-mode breadth`** | no sub-period loses; same DD, more exposure | 15 |

### Rejected

| idea | why it failed | chapter |
|---|---|---|
| 3–5% fixed stop (as taught) | inside the noise; kills half the winners | 4d |
| Candidate ranking (any key) | indistinguishable from random | 3, 5c |
| Trailing exits | +2.79%; the RSI target is load-bearing | 5c |
| `scale_out` | fixes payoff, costs return; more idle capital | 5c |
| Breakeven ratchet | **structurally doomed** — losers never show a profit | 9 |
| Weekly-breakdown exit | real signal, 43% friendly fire, asymmetric errors | 7 |
| Sector-gate loosening | beta bet: −2.96% in H1 | 6c |
| Father-leg latch (`f_rsi_hold`) | no plateau; adds ~1.4pp over just lowering the threshold | 14c |
| No regime gate at all | it's leverage — loses at matched exposure | 15b |
| Risk-based sizing as a *selector* | it's a leverage dial | 10 |
| LTCG engineering | the mechanism that extends holds removes the edge | 5b |

### Kept in the code but defaulted off

`--exit-f-rsi`, `move_stop_to_breakeven_at_r`, `--exit-mode scale_out|trail`,
`--sizing risk`, `--regime-mode breadth+sma`, `--htf-mode live`. Each is a
recorded negative result that someone will otherwise re-invent.

---

## What we still don't know

Ordered by how much they should worry you.

1. **There is no holdout left.** The H1/H2 split *and* the thirds split have both
   been used to **select** settings. Neither is a holdout any more. The only
   genuine out-of-sample evidence in this repo is the conviction study's
   train/test split, and it covers the entry filter (`headroom`) only — not the
   stop, the exit, the sizing or the regime gate.
2. **The `nse_all` level is not established.** On the full listed universe the
   post-tax excess is **−0.40%**. But that comparison is confounded: **100% of
   `nse_all` has no industry label**, so the sector gate and per-sector cap
   silently switch off — it is the same strategy *with two risk controls
   disabled*, not the same strategy on a wider universe. Getting sector labels
   for the full NSE list is the single highest-value piece of unfinished work.
3. **No 2008 in the sample.** See 15c. The regime decision is the place this
   bites.
4. **Excess is concentrated in 2019–2026** and is ~0 in 2013–2019, largely
   because GFS cannot keep up with a strong index (ch. 12). Size accordingly.
5. **`--exit-rsi 70` is under a cloud** after YTD 2026 (ch. 8). A useful next
   step, proposed but not run: re-run the thirds split with T3 cut at end-2025 to
   see whether 70's advantage was ever more than the 2022–2024 window.
6. **Survivorship bias is unmeasured** in every number here. Delisted and merged
   companies are absent from every universe.
7. **Crowding.** GFS circulates as a public Chartink screener. A backtest cannot
   see the crowding that public knowledge creates.
8. **The qualitative top-down leg is not modelled** and cannot be — an LLM
   reading news always sees today. Breadth, sector RS and the index trend are
   quantifiable stand-ins. The judgement layer is validated in neither direction.

### Untested levers, ranked

1. **Park idle cash in the index rather than a liquid fund.** Even at maximal
   loosening the strategy never exceeded ~76% exposure, so **no entry filter can
   fix the cash drag — it is structural.** Holding NIFTYBEES in the gaps would
   keep the account fully invested, let GFS displace index exposure instead of
   cash, and convert the reported excess into true alpha. Most likely to rescue
   the flat 2013–2019 half. **This is the biggest single untested idea.**
2. **Entry-side trend-intactness filter** — price above its 50-DMA while daily RSI
   is depressed. This is the chapter-7 idea moved to the *entry*, where a false
   positive costs an opportunity instead of a realised loss. Not ruled out by any
   result above.
3. **Sector labels for `nse_all`** — see point 2 in the list above.
4. **Volatility-scaled breadth threshold** rather than a fixed 40%.

---

## Reproducing anything here

```bash
# The current recommended config (breadth-only regime is now the default)
python -m backtesting.gfs.run_backtest \
  --start 2013-01-01 --end 2026-08-21 --universe nifty500 \
  --max-holding-days 0 --min-headroom-pct 10 --atr-mult 3.5 \
  --s-rsi 43 --exit-rsi 70 \
  --max-positions 4 --max-position-pct 30 \
  --cash-yield-pct 6.5 --min-breadth 40

# Restore the old two-leg gate
#   ... --regime-mode breadth+sma --regime-sma 200

# The out-of-sample entry-filter study (the only real holdout evidence)
python -m backtesting.gfs.run_conviction --start 2013-01-01 --end 2026-08-21 --grid
```

Sweeps in this document were run as throwaway scripts against
`service.prepare_data` + `service.run_single`, not committed. The pattern is:

```python
prepared = prepare_data(base_cfg)              # expensive, once
for cfg in candidates:                          # cheap, reuses the panel cache
    res = run_single(cfg, prepared, with_forward_study=False, monte_carlo_runs=0)
```

The panel cache key (`panels.base_panel_key`) omits dates and thresholds, so one
`prepare_data` serves every window and every threshold/exit/sizing/regime
variant. Only changing an RSI or ATR **period** invalidates it — which is why the
RSI-period sweep in chapter 12 was the expensive one.
