# GFS live strategy — usage guide

**Grandfather / Father / Son.** Buy short-term weakness inside long-term
strength: the monthly candle (G) and the weekly candle (F) must both be in an RSI
uptrend while the daily candle (S) pulls back. The premise is that two strong
higher timeframes drag the weak daily back up.

This folder is the **live runner**. The research that produced every default here
lives in [`backtesting/gfs`](../backtesting/gfs/) —
[`README.md`](../backtesting/gfs/README.md) for the harness and
[`EXPLORATIONS.md`](../backtesting/gfs/EXPLORATIONS.md) for the full record of
what was tried, what was adopted and what failed.

---

## 1. The one thing to understand first

**The live strategy is not a re-implementation of the backtest. It is the
backtest, resumed.**

`gfs/engine.py` imports `backtesting.gfs.engine.GFSBacktestEngine` and runs its
daily loop over the sessions that have elapsed since the last run. Entries,
ranking, stops, exits, the sector cap and position sizing are all executed by the
backtest's own code. There is no second copy of a rule anywhere in this package
that could drift away from what was measured.

The consequence you feel day to day:

> A signal seen at **today's close** is filled at the **next session's open** —
> never at today's close.

So a post-close run does not say "buy these now". It says *"place these orders at
tomorrow's open"*. Those orders sit in a persisted queue and are filled by the
*next* run against the open that actually printed. That timing is exactly what
the backtested numbers were produced under, and breaking it would quietly make
the live results mean something different.

`tests/test_gfs_live.py::test_resuming_in_chunks_matches_one_shot` is the proof:
it runs the engine once straight through, then runs the same window again in
seven uneven chunks with a full save/reload of the book between each, and asserts
the resulting cash, positions, stop levels, high-water marks, trade log and
equity curve are identical.

### The daily rhythm this implies

| When | Engine | You |
|---|---|---|
| Tonight, after close | Finds a signal, queues it | Read the order |
| **Tomorrow, at the open** | — | **Place it** |
| Tomorrow, after close | Replays the session, fills at the real open, moves it into Holdings | Run again |

**Do not wait for an order to appear under Holdings before buying it.** It only
lands there on the run *after* you placed it — and that run has already booked
the fill at the open you were meant to trade. Waiting puts you a session behind
the book, and every number the strategy reports from then on describes trades you
did not make.

Between those two runs the order lives only in the pending queue, so the saved
book panel shows the full order table — symbol, indicative quantity, stop, RSI
triplet — not merely a count.

---

## 2. Running it

### Nightly, from the command line

```powershell
python -m gfs.run_daily
```

Run it **after the NSE close** (roughly 16:00 IST onwards — the bar store needs
the exchange to have published today's candle). It downloads only the bars it
does not already have, replays every session since the last run, saves the book
and prints the orders for the next open.

Exit code `0` on success, `1` on failure. A failed run never writes the book, so
a crash cannot leave a half-updated portfolio behind — the next run simply
replays the same sessions.

**Windows Task Scheduler**

The workbench now ships its own scheduler, which is the easier route — it keeps
`gfs_live` and `qtr_results` on their own cadences and writes both to the run
history so the UI shows them:

```powershell
uv run python -m core.scheduler install-task
```

That registers a logon task plus a 30-minute watchdog, and falls back to a
Startup-folder entry when creating scheduled tasks needs administrator rights.
See [`core/SCHEDULER.md`](../core/SCHEDULER.md) for the details.

To drive `python -m gfs.run_daily` directly from Task Scheduler instead:

| Field       | Value                                    |
| ----------- | ---------------------------------------- |
| Program     | `C:\path\to\python.exe`                   |
| Arguments   | `-m gfs.run_daily`                        |
| Start in    | the repository root (**required**)        |
| Trigger     | Daily, ~17:00 IST, weekdays               |

Either way the run is recorded in the workbench run history, so the GFS tab
shows it on next page load. Pass `--no-history` to skip that; `--dry-run` never
records.

Missing a day costs nothing. Miss a fortnight and the next run replays the
fortnight.

### From the UI

**Discover Ideas → GFS multi-timeframe**. The saved book renders on page load
with no network call; the form below it runs the strategy.

### Useful flags

```powershell
# See what it would do without saving anything
python -m gfs.run_daily --dry-run

# Create the book with history instead of starting flat today
python -m gfs.run_daily --bootstrap-from 2023-01-01 --capital 500000

# Re-run a past date (for reconciliation)
python -m gfs.run_daily --as-of 2026-05-14 --dry-run
```

---

## 3. Starting the book

The first run creates the book. You have two choices:

| Choice | What happens |
| --- | --- |
| **Start flat** (default) | The book opens today with your capital in cash and no positions. Clean, but it has no track record and you will wait for the first signal. |
| **Backfill** (`--bootstrap-from`) | The strategy is replayed from that date. You inherit the positions it would already be holding, a real equity curve and a tradebook. |

Backfilling is *not* cheating — it is the same causal engine over real history —
but the positions it hands you were entered at historical prices you did not
actually pay. Treat a backfilled book as a paper track record, not as a
statement of your broker account.

Capital is used **once**, when the book is created. Changing `--capital` later
does not re-capitalise an existing book. To start over: `--reset-book` (this
deletes the cash, positions and tradebook, and there is no undo).

---

## 4. The levers

Defaults below are the researched configuration. The "why" column is the short
version; `EXPLORATIONS.md` has the evidence.

### Entry

| Lever | Default | Why |
| --- | --- | --- |
| `g_rsi_min` — monthly RSI ≥ | 60 | The strategy as taught. |
| `f_rsi_min` — weekly RSI ≥ | 60 | The strategy as taught. |
| `s_rsi_entry` — daily RSI ≤ | **43** | 40 is an arbitrary round number. 43 buys meaningfully more signals with no measurable degradation in edge — and signal scarcity is this strategy's main practical problem. |
| `min_headroom_pct` | **10** | Refuse a dip with less than 10% of room before the resistance the exit targets. A signal with no headroom has no room to pay for its own stop. **This is the only entry filter that survived an out-of-sample test** — every other "conviction" filter tried was curve fit. |

It is a **level** test, not a cross: the daily RSI has to *be* at or below the
threshold, it does not have to cross down through it.

### Exits

| Lever | Default | Why |
| --- | --- | --- |
| `exit_rsi` | **70** | Exit when daily RSI reaches this. See the caveat below. |
| `shadow_exit_rsi` | **60** | Reported, never traded. See §6. |
| `atr_stop_mult` | **3.5** | 3.5× ATR(14), ratcheting up, never down. |
| time stop | **off, permanently** | Per your instruction: exits come from RSI and price only. Not exposed as a parameter — `build_config` pins it to 0 even if something tries to set it. |

**On the stop.** The strategy as taught prescribes a 3–5% fixed stop. That was
tested and **rejected**: a stop that tight sits inside the normal noise of an NSE
midcap and liquidated roughly half the trades that would eventually have won. A
3.5× ATR stop is wider in percentage terms but is measured in the stock's own
volatility. The plateau runs 3.0–4.5 — anywhere in there is defensible; outside
it degrades.

**On the exit threshold — the honest caveat.** Over the full 13.6-year record,
exit-70 returned ~21.5% CAGR against exit-60's ~18.5%, and lifted the payoff
ratio from 0.82 to 1.37. But exit-70 **lost to exit-60 by 4.8pp in YTD 2026** and
holds positions roughly twice as long (66 days vs 33). The research could not
separate them out of sample. 68–72 is defensible; treat this as a preference, not
a settled result. That is exactly why the shadow report exists.

### Gates (the top-down funnel, made mechanical)

| Lever | Default | Why |
| --- | --- | --- |
| `regime_mode` | **`breadth`** | The helicopter view. `breadth` = trade only when enough of the universe is above its own 200-DMA. `breadth+sma` additionally requires the index itself above its 200-DMA — it cost signals and added nothing breadth had not already said. |
| `min_breadth_pct` | **40** | Below 40% of the universe above its 200-DMA, the gate shuts and no new entries are taken. Open positions are still managed normally. |
| `sector_top_n` | **5** | The aerial view. Only trade names in the 5 strongest sectors by 63-session relative strength. |
| `max_per_sector` | **2** | Concentration cap among open positions. Unlabelled sectors are never capped (see §7). |

The qualitative half of the top-down method — global markets, news, sentiment —
is deliberately **not** implemented. It cannot be backtested, so including it
would mean shipping a live strategy whose numbers no longer correspond to
anything measured. Breadth and sector relative strength are the mechanical
proxies that can be.

### Sizing

| Lever | Default | Why |
| --- | --- | --- |
| `max_positions` | **4** | Not 8. Concentration is where the payoff comes from; spreading the same capital over 8 names diluted the winners without materially reducing drawdown. |
| `max_position_pct` | **30** | Per-name ceiling as a share of equity. |
| `cash_yield_pct` | **6.5** | This book is only ~40–60% deployed. Assuming the idle balance earns nothing is not neutral — it is a large silent penalty that the always-invested benchmark never pays. A liquid fund is the realistic case. |
| `commission_pct` / `slippage_bps` | 0.05% / 15 bps | Per side, applied to every fill. |

### Pinned — not exposed, on purpose

`htf_mode=closed`, `entry_trigger=dip`, `exit_mode=rsi`, `stop_mode=atr`,
`sizing_mode=equal`, `rank_by=composite`, RSI period 14 on all three timeframes,
`max_holding_days=0`, indicator exits delayed to the next open.

`htf_mode` deserves a word. `closed` means the weekly and monthly RSI only ever
use **completed** candles — mid-month, the strategy reads last month's closed
monthly candle, not the unfinished one your chart is drawing. `live` (using the
partial candle) is what a chart shows you, and it roughly **halved** returns in
testing. Every published number was produced under `closed`, so `closed` is what
runs live. If you eyeball a chart and disagree with a signal, this is usually
why.

---

## 5. Reading the output

**Stale-data banner** — if it appears, read nothing else until you have fixed it.
See §5a.

**Book** — equity, cash, deployed and exposure. Exposure of 40–60% is normal; see
§7.

**Market regime banner** — green means new entries are allowed; red means the
breadth gate is shut and nothing new will be bought today. Open positions are
still managed either way.

**Orders for the next open** — the only actionable section.

- *Buy* rows show the reference price (the close that produced the signal), the
  stop, and the G/F/S RSI triplet. **Quantities are indicative**: the engine
  re-derives the stop and the size from the actual opening print, so an overnight
  gap changes the size rather than silently changing the risk you were sized for.
- *Sell* rows carry a reason: `rsi_target`, `resistance`, `stop` or
  `trailing_stop`.

**Filled since the last run** — what the replay executed against real opens since
you last ran it. This is the reconciliation view: it is what the model believes
your account did.

**Holdings** — entry and current price, unrealised %, the current (ratcheted)
stop, days held, and the live G/F/S RSI triplet.

**Top-down funnel** — universe → names with enough history → names meeting the
GFS condition → regime open → strong sector → queued. When you get no signals,
this tells you which stage ate them.

**Watchlist expander** — every name that met the mechanical GFS condition today
and why each did or did not become an order (`sector_weak`, `sector_cap`,
`portfolio_full`, `ranked_out`, `regime_closed`, `already_held`). These labels
are *descriptive*: the engine had already decided; this explains the decision
after the fact.

**Track record** — win rate, payoff, expectancy in R, average hold, max drawdown.
CAGR is **withheld until the book has 90 days of history**, because annualising a
good fortnight produces a meaningless number.

---

## 5a. The stale-data guard

The most dangerous failure this system can have is not a wrong signal — it is a
**right signal computed from old prices**, because nothing about it looks wrong.

That has already happened once. A parsing bug in the shared bar store meant the
benchmark index silently stopped updating while all 500 constituents stayed
current. The benchmark defines the master calendar, so the whole strategy froze
four sessions in the past, produced no signals, and reported an as-of date of the
previous Friday without a single error.

So every run now compares the newest session it can see against today:

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
 STALE PRICE DATA - DO NOT ACT ON THE ORDERS BELOW
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
 Newest session available is 2026-08-21, 2 weekdays behind 2026-08-25.
```

**Thresholds.** Zero or one weekday behind is normal — weekends and holidays cost
nothing, and one weekday absorbs the usual case of the data vendor not having
published tonight's close yet. **Two or more weekdays is treated as a fault.**

**Why it warns rather than refuses.** The replay itself is still correct: those
sessions really did happen, and the pending orders will fill at the right
historical opens once the data catches up. The book self-corrects. The hazard is
entirely human — reading "place these at the next open" and placing them at a
price several sessions later. So the banner targets the person, not the engine.

**What to do.** Refresh the bar store and re-run:

```powershell
python -c "from core import bars; from datetime import date, timedelta; bars.sync(['^NSEI'], date.today()-timedelta(days=60), date.today(), force=True)"
python -m gfs.run_daily
```

If it persists, the vendor is down or the symbol has changed. Do not trade the
output.

The saved-book panel in the UI carries the same warning, so a book you have not
updated for a week announces itself when you open the tab rather than when you
act on it.

---

## 6. The shadow exit

The exit-60 vs exit-70 question is genuinely unresolved. Rather than pick one and
pretend, the book **trades** `exit_rsi` and **reports** `shadow_exit_rsi`.

Each run flags which open positions the alternative threshold would already be
selling. Nothing acts on it — no order, no P&L, no effect on the book. Over a few
months of live running you accumulate real evidence about which rule you would
rather have been following, on your universe, in this regime. Set
`--shadow-exit-rsi 0` to switch the report off.

---

## 7. What this will and will not do

Read this before deciding the strategy is broken.

**It sits in cash a lot.** Average exposure over the full backtest was roughly
40–60%. Between the breadth gate, the sector gate, the headroom filter and a
4-position cap, there are long stretches with nothing to buy. That is the
strategy working as designed, not a failure. If your money must never be idle,
run GFS alongside other strategies rather than loosening its gates.

**Signals are scarce.** Days with zero qualifying names are routine. A week with
no orders is unremarkable.

**It has had losing years.** One negative year in fourteen in the backtest.
Drawdowns in the 20% region are normal.

**The sample contains no 2008.** The record starts after the global financial
crisis. The breadth gate has never been tested against a true systemic collapse.

**Index-inclusion bias is present.** The universe is *today's* nifty500. Membership
today is partly a consequence of performance during the test window, and delisted
or merged companies are absent entirely. Every backtested return is therefore an
optimistic upper bound. The run output prints this caveat every time.

**Use `nifty500`.** `nse_all` carries no industry labels, which silently disables
both the sector gate and the per-sector cap — two of the four gates. The strategy
was not validated in that configuration.

**The book is paper.** It sizes positions against its own persisted cash, marks
them at the model's fill prices, and knows nothing about your broker account. It
is a decision engine and a track record, not a statement.

**Taxes are not deducted from the live book.** The research modelled Indian STT,
stamp duty and capital-gains treatment (`backtesting/gfs/taxes.py`) and the
adopted configuration was chosen to survive them, but the live book reports
gross-of-tax P&L. Budget for short-term capital gains on a strategy whose average
hold is well under a year.

---

## 8. Files

| File | What it is |
| --- | --- |
| `engine.py` | The live runner: resume the book, replay the missed sessions, build the report. |
| `state.py` | The persisted book — cash, positions, tradebook, equity curve and the pending order queues. Stored in the `documents` table under the `gfs` namespace. |
| `config.py` | Maps UI/CLI parameters onto the backtest's `GFSConfig`, and pins the fields that are not negotiable. |
| `run_daily.py` | The `python -m gfs.run_daily` entrypoint. |
| `USAGE.md` | This file. |
| `../strategies/gfs_live.py` | The registered strategy wrapper the UI renders a form from. |
| `../tests/test_gfs_live.py` | Fidelity tests, including the chunked-resume parity proof. |

Nothing is stored outside the application database, so backing up the DB backs up
the book.
