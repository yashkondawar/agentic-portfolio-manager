# S18: fixed-book backtests and portfolio tracking

S18 is a deterministic, stacked S1 momentum book plus an S2 idle-cash sleeve.
The portfolio uses **strategy-modelled fills, not broker-synced executions**.
No S18 control places, changes or cancels broker orders.
Neither a successful historical replay nor the imported reference's historical
results establishes future profitability.

**Integration evidence (2026-10-04):** the repo-native engine golden replay
passed all **15 combo/metal-mode pairs and 30 tranches** using natively
recomputed inputs. This establishes reference parity for that tested snapshot,
not forward execution quality or future returns. Each installation still
requires a passing certificate for its current engine/data; inspect the
validation evidence from your own run rather than treating this historical
check as a permanent authorization.

## Workbench and registry

| Location | Strategy ID | Purpose |
|---|---|---|
| Discover → S18 Portfolio | `s18_daily` | Saved portfolio above daily controls; current/latest run below |
| Backtest Lab → S18 Backtest | `s18_backtest` | One fixed combo/mode, selected period and initial capital |
| Backtest Lab → S18 Golden Replay | `s18_replay` | All 15 combo/modes × A/B against DB-owned golden records |
| Settings & Strategy Catalog | All three | Automatically generated parameter reference |

Default selection is **P15 / both_priority**. There is no optimization grid,
custom slot-count control, validation bypass, single-tranche mode or
reference-position seeding toggle.

### Daily portfolio layout

The top section reads the committed portfolio directly from SQLite. Merely
opening the page does not fetch prices, recalculate signals, run validation,
or update holdings. It shows the saved close date, portfolio value, cash,
invested value, realised/unrealised P&L, holdings and next-session instructions.
Active stops are included in the holdings table rather than duplicated across
separate stop tables. Tradebook and portfolio history are expandable.

While the page is open, the S18 section rereads saved results every 30 seconds.
**Refresh saved portfolio** also rereads them immediately, without running the
strategy, fetching market data or changing either book. A scheduler update is
therefore visible without submitting the daily form. The run's recorded time
and its processed market-close date are different: a weekend or pre-close run
can legitimately report the preceding session.

The **Run S18 Daily** form follows the portfolio. Keep **Save portfolio updates**
on for normal tracking. A successful saved run refreshes the top view in the
same page response; no second refresh is needed. Turning saving off makes a
preview, which appears only in the lower run section.

**Latest run** at the bottom is scoped to the selected portfolio ID, combo and
metal mode. Failed runs or previews remain visible there but cannot replace
the authoritative portfolio. Daily data-readiness JSON, replay evidence, dataset
details and assumptions are collapsed under **Diagnostics and assumptions**.
The saved daily report, including its SMA100 risk-on/risk-off status, is visible
without opening an expander. Backtest Lab retains the detailed
research/validation output.

An empty portfolio is not necessarily a failed run. S18 follows momentum; a
market correction is not itself a buy signal. Risk-off blocks S1 entries,
including priority metals. S2 can buy during risk-off, but only on its tranche's
review date and subject to the startup capacity lag and ranking rules. The
five-session delay alone does not trigger an S2 purchase on the following day.

### Fixed combinations

| Combo | S1 slots | Entry order / gate | Armed trailing stop | Floors |
|---|---:|---|---:|---|
| P5 | 5 | Momentum / x63 | 20% | Below +10% after 63 sessions |
| P10 | 10 | Momentum / x63 | 25% | Below +10% after 63 sessions |
| P15 (default) | 15 | Tiered / sc15 | 25% | Below +10% after 63 sessions |
| P20 | 20 | Tiered / sc15 | 25% | Below +10% after 63; below +20% after 126 |
| A20 (backup) | 20 | Momentum / x63 | 25% | Below +10% after 63 sessions |

- **A and B always run independently with half the initial capital each.**
  A's monthly review is the last exchange session; B's is ten sessions earlier.
  Golden replay preserves the reference's terminal-calendar exception below;
  daily uses the explicitly complete exchange calendar instead.
- Live reviews use only confirmed month-ends. A partial preview of the following
  month cannot become a synthetic month-end or introduce an extra tranche-B
  review ten sessions before the end of that preview.
- S1 buys use AL L6G1 momentum order. P15/P20 prioritize names at a 52-week
  closing high, then names within 15%. x63 means a 52-week closing high
  occurred within the last 63 sessions.
- The always-on Nifty 500 SMA100 overlay blocks new S1 buys while risk-off,
  not exits. Monthly AL L3G2 rank above `3n` arms S1 stops; rank back within
  the band disarms them. A review alone is not a sell.
- S2 is stocks-only, skips the top 15 buy-ranked names, has no gate, floor or
  trailing stop, ignores the overlay, and trades on monthly reviews subject
  to daily funding/clear-out. Keep band is `15 + 2n`, cash-capacity lag five
  sessions, and it clears when S1 fills at least `ceil(0.8n)` slots.
- A qualifying S2 holding is promoted into S1 without a trade: preserve its
  quantity, original tax basis and peak, reset its S1 floor clock and start
  unarmed.

### Metal modes

`none` excludes metals; `both` ranks gold and silver among stocks;
`both_priority` walks eligible metals ahead of stocks. Metals still satisfy
every S1 gate, keep band, tier, overlay, floor and stop rule. They never enter
S2. A metal occupies one slot for P5/P10/P15 and two for P20/A20.

The imported dataset includes historical metal proxies, not an uninterrupted
history of executable ETF quotes: **SILVER before 2022-02-07 is a proxy**, disclosed in
`metal_history` provenance. In particular, applying the reference equity capital-gains
tax treatment to metal ETFs is a comparability convention, not a claim about
their legal taxation.

## DB-owned inputs and fresh-machine setup

S18's engine, data readers, replay, paper service and NSE collector are
repo-native. All required original runtime inputs and golden-reference data
are owned by the **shared application SQLite database**, including the complete
2012 warm-up history and the reference period ending **2026-08-31**. Dataset
versions are immutable and carry a SHA256 source manifest; a failed import is
atomic and leaves the previous active version intact.

The default Windows database is
`%LOCALAPPDATA%\AgenticPortfolioManager\portfolio.sqlite3`, outside Git.
`PORTFOLIO_DB_PATH` remains the repository-wide database-location setting.
The large historical panels and SQLite database are **not committed to Git**;
this guide and the implementation are in the project. Historical backtests,
golden comparison and historical daily data read the database, not a Downloads
folder or a reference-kit checkout. Normal forms and service calls expose no
reference-path, forward-path or data-source selector.

On a **fresh machine**, restore a backup of the application database or have an
administrator import the original source once. Cloning code cannot recreate
the historical evidence. The maintenance importer reads the supplied folder
without executing its scripts, regenerating golden references or rewriting it:

```powershell
python -m backtesting.s18.dataset import --source "C:\data\S18_Forward_Test_Kit"
```

After a successful import the source folder may be unavailable: it is **not a
runtime dependency**. To place read-only copies of the original spec and
README, all 33 golden-output assets and `dataset_manifest.json` directly in
the project, run:

```powershell
python -m backtesting.s18.dataset export-reference
```

These copies go to the Git-ignored
`reports\s18\reference\<dataset_id>` directory. Runtime inputs remain DB-owned;
neither these copies nor the original Downloads folder is needed by normal
app runs. This reference-only export is distinct from the automatic run
exports under `reports\s18\<artifact_group_id>`.

For full-dataset portability, an administrator can optionally export the
DB-owned inputs and import that export into another app database:

```powershell
python -m backtesting.s18.dataset export --destination "C:\exports\s18-dataset"
```

This dataset export is not a replacement for a full database backup containing
paper books, run history, live evidence and artifacts. Run Golden Replay in
each execution environment before paper use; restored historical certificates
do not bypass the current engine/data/runtime checks.

### Product APIs

`backtesting.s18.dataset.get_dataset(*, db_path=None)` returns the DB-owned
`Dataset`; `.status()` exposes its metadata. `db_path` is an internal/admin
database override, not a strategy input or an external reference path.
`backtesting.s18.service` provides:

- `run_replay()` with no arguments: validate all 30 reference tranches.
- `run_backtest(*, combo="P15", metal_mode="both_priority", start="2014-01-01",
  end="2026-08-31", capital=100000.0, write_dossier=True)`.
- `run_daily(*, combo="P15", metal_mode="both_priority", as_of=None,
  capital=100000.0, book_id="default", persist=True, shadow_charges=None)`.

Daily automatically uses DB warm-up/history and the official NSE collector.
Live network access to NSE is still required for new exchange evidence:
**no external experiment-folder dependency does not mean an offline live feed**.
Missing or stale required coverage blocks the run rather than silently
advancing an incomplete book.

### Market-data and share-unit consistency

The input layer preserves session dates, stable company identity, point-in-time
Nifty 500 membership and the Nifty 500 **price index**, not a total-return index.
Effective-dated ISIN aliases must not relabel holdings, and former members
retain their histories. Splits, bonuses and applicable demergers need
consistent adjustment; dividends are not reinvested. Listed non-trading days
and actual delistings remain distinct. Gold/silver inputs are required when
the selected mode uses metals; ETFs never enter S2 or Nifty 500 membership.

The explicitly complete exchange calendar covers the requested month-end and
a subsequent exchange session, including holidays and special sessions.
The last observed price row cannot establish month-end or a tranche review.
The post-reference daily period starts **2026-09-01**. A declared non-session
`as_of` resolves to the last completed exchange session; missing required
coverage fails instead of inventing a holiday.

Verified raw-close anchors establish the imported-to-live price-unit seam;
its multiplier is not assumed to be one. Securities observed in any collected
bridge-session bhavcopy require a verified anchor even if they are absent from
today's security master or current index membership. Absence today must not
erase their earlier trading evidence or assign an unverified price scale.
The entire returned OHLC history is
back-adjusted into the share units at `as_of`. Cumulative
`provenance.price_scales[identity]` reflects split/bonus/demerger factors.
Before consuming new sessions, persisted quantities, peaks and historical
entry/exit prices are rebased **once** for a changed scale; **cost basis and
cash do not change**. Repeat runs cannot apply the same action twice.

`raw_to_book` reports the final-session raw quote conversion;
`raw_to_book_events` and `raw_to_book_anchors` give dated conversions in the
as-of share base. The historical metadata key `raw_to_kit_anchors` retains
unrebased seam evidence, not a runtime folder dependency. Demerger
normalization is a synthetic tape-price convention, **not delivery of a
demerged company's shares** or a broker execution adapter.

**Displayed quantities and prices versus model units**

Live NSE books and normal S18 backtests use **whole exchange shares**.
Golden Replay and the legacy reference-period daily simulation retain the original
fractional model for compatibility; they are not the investable backtest. A live buy
uses the actual opening quote, not the adjusted research price, and rounds quantity
down after costs. Share value is quantity times price; cash debited includes the
model cost. S18's existing buy-cost convention is retained: 0.02% of cash outlay,
so cash required is share value divided by 0.9998. Unused money stays in cash.
A budget that cannot cover one share produces a recorded skipped buy, not a
fractional position. Tranche allocations, ranks, review dates and S1/S2 priority
are unchanged.

Next-session BUY instructions show **estimated integer quantity**, reference close,
share value, model cost and cash required. These estimates run the same allocation
logic at closing prices, including queued exits and annual tax funding; actual
orders are resized at the next open. Reference quotes cannot anticipate overnight
price changes or unobserved corporate actions. SELL instructions show the held
whole-share count. None of these instructions submits a broker order.

When `provenance.raw_to_book[identity]` is available, daily results convert
displayed `qty`, `close`, `peak` and `stop` into current-share/raw-quote
equivalents. With that conversion factor, `model_price = raw_price * factor`
and `qty_current = model_qty * factor`; displayed close/peak/stop therefore
divide their model values by the factor. The result retains `model_qty`,
`model_close`, `model_peak` and `model_stop` alongside the converted fields.
This is a display/export conversion, not a mutation of the internal book.

Live fills retain their integer executed share quantity and raw execution price
alongside model quantities/prices. Dated conversions ensure that catch-up runs
round in the share units actually traded on each session, not today's split-adjusted
units. Full exits and partial tax-funded sales also use whole shares; tax sales
round up, release proportional cost basis and retain any excess proceeds as cash.
Verified split/bonus fractions are separated from tradable whole shares and
**modeled as cash-in-lieu at the first available opening quote on or after the
ex-date**, in both backtest and live paper books. For example, a 112.5-share
entitlement leaves 112 tradable shares and a modeled cash payment for 0.5 shares.
This is an explicit approximation, not a verified payment amount or payment date.
No market fill or trading fee is created. Proportional existing model cost basis
is released into the usual gain/tax pools; actual bonus-share tax treatment can
differ. April settlement gains belong to the new tax year.

Until an opening quote is available, the fraction is a separate non-tradable
receivable marked in NAV, not spendable cash. Pending entitlements persist across
runs and rebases; order previews do not credit them using yesterday's close.
The UI, CSVs and dossier show pending entitlements and modeled settlements apart
from whole-share holdings and fills. Unexplained fractional quantities and held
demergers still require reconciliation rather than silent rounding or fictitious
child-share delivery.

Exported orders carry `paper_only=true` and label live quantities as **whole
exchange shares**. Older fractional books retain their original labels.
Historical reference-only results without a
conversion factor instead label their quantities **adjusted model units**; they are not
silently presented as current exchange shares.

Internal books and replay logs remain in model units, which can be fractional
even when the equivalent exchange-share count is an integer. Reference fill tables
retain the **adjusted model units** label; live fill tables use **whole shares at
execution**. Do not compare quantities across different share bases.
None of these outputs is a broker order or execution confirmation. In
particular, the demerger synthetic-price convention does not represent actual
delivery of child-company shares.

Changing live sizing is an explicit book migration, not a display-only rounding.
The guarded `run_daily(..., migrate_cash_only=True)` path accepts only the known
pre-whole-share engine fingerprint, at the book's saved date, with both tranches
still entirely in initial cash and no positions, fills, realised gains or taxes.
It preserves the inception, cash, equity history, capacity history and queued
selections; saves the former artifact-group reference; and regenerates instructions
without advancing a session. Preview with `persist=False` before saving. A filled
legacy book or an unrecognized engine version requires separate review/new book,
never silent conversion. Replay validation is still required in each runner's
Python environment.

**Strict historical backtest and sizing comparison**

The normal S18 Backtest reads raw NSE OHLC from `market_bars`, joined by dated
ISIN chains, alongside the imported adjusted panel. It verifies a common price
scale across OHLC, then uses one scale per corporate-action interval to prevent
rounding noise in the imported panel from creating false fractional entitlements.
Raw quote and action hashes are retained in the result provenance. On a non-trading
day only the known share-unit scale is carried forward, not a tradable price.
Separate same-day split and bonus factors are multiplied once, matching live
ingestion. Historical combined-action labels are normalized; duplicate or
overlapping actions are not accepted as extra share allotments.

The same `Book.step` handles the historical and forward books: whole-share sizing,
costs, tax-funded integer sales, S1/S2 priority, five-zero startup capacity history
and complete-calendar reviews. A requested backtest starts in cash at its first
session's close, with no forced initial review or preceding-session purchase.
Final-session decisions remain queued, not executed outside the window.
Historical ETFs use actual exchange availability; the pre-listing silver proxy
is removed from both executable prices and indicator warm-up. Historical
constituent membership remains inherited from the imported PIT dataset.

Unresolved demergers, unexplained fractional quantities and unexplained changes
in price units stop the run. Verified split/bonus cash-in-lieu uses the disclosed
opening-price approximation above; no child-company shares are invented.
The run is marked **failed/incomplete**, with the blocking date, identity and
reason. The failed session is excluded from all published state. A matched
fractional diagnostic and the whole-share result are then compared only over the
successfully processed prefix. `metrics` stays empty for a stopped request;
`partial_metrics`, comparison dates, CSVs and dossier disclosures label the
limited period. A small prefix difference is not evidence that the full requested
history would be unaffected. The sizing comparison also reports modeled settlement
counts, cash credited and any still-pending entitlement value.

The input layer supplies `session_calendar`, `calendar_complete_through` and
`history_fingerprints` for complete-calendar and historical-consistency checks.
`canonical_indices` reserves the imported stock IDs and **both metal IDs
in every mode**, then appends new companies in listing-date/ISIN order.
`canonical_identities` is that append-only global identity list. The actual
engine matrix remains stocks-first, enabled-metals-last; `engine_indices`
maps identities to those columns. Persist and reconcile stable identities,
not mode-dependent matrix gids, so new IPOs cannot relabel existing holdings.
The complete exchange calendar is exposed in historical and forward
provenance, rather than inferred from the final observed row.

**Provenance and resume consistency**

`stock_signals` and `metal_signals` identify `recomputed`, `cached` or
`disabled` inputs. `content_hash` covers the imported source content; forward
evidence has separate `extension_content_hash` and `extension_files`.
`session_calendar` includes known exchange sessions from DB warm-up through
the declared future calendar; `calendar_complete_through` is its last covered
calendar date.

`history_fingerprints` maps forward ISO sessions to SHA256 evidence digests,
versioned as **`s18-raw-day-v1`**. They cover canonical raw OHLC/previous close,
index and completeness attestations, calendar, memberships and sources,
effective ISIN/symbol maps, relevant actions and anchors. Resume compares every
saved date key. CSV row ordering and later-effective actions, aliases or
snapshot expiry do not change earlier-day hashes; historical raw corrections
do. Derived cumulative adjustment factors are deliberately excluded.

### Automatic official-NSE collection

`backtesting.s18.nse_sources` supplies strict source retrieval and immutable
evidence. `backtesting.s18.live_data.collect_market` joins it to the DB-owned
history and produces the same `PreparedMarket` contract used by paper daily.
It does not invoke the old bhavcopy fetcher's error-to-holiday fallback or
the corporate-action fetcher's error-to-empty fallback.

The source path covers final cash-market bhavcopies (EQ/BE/BZ), the Nifty 500
price-index close, official constituent observations, security/listing data,
corporate actions and the exchange calendar. Missing expected-session files,
wrong payload dates, inconsistent identities and unresolved price adjustments
stop the run. Calendar exceptions need official evidence; an HTTP failure
cannot declare a market holiday.

Forward testing deliberately retains the original **EQ/BE/BZ equity scope plus
the selected metal ETFs**, with the user-approved REIT/RR exclusion retained.
Official index members in RR (REIT) or other excluded series are listed in
readiness/provenance with reasons, not silently introduced
as a strategy change. Non-executable `DUMMY`/`DUM` index placeholders are also
disclosed and do not acquire invented share histories. The benchmark remains
the complete Nifty 500 price index, so this instrument-scope difference is visible.

The post-August price bridge is **warm-up only until paper inception**.
Today's constituent list is never projected back over September. A first
run without a dated snapshot for the latest completed session returns explicit
waiting readiness and creates no paper positions. It collects the current
observation so a subsequent genuine forward session can start the book.
After inception, every consumed decision session needs its own saved snapshot;
missed snapshots require verified recovery, not interpolation from today's list.

Live daily runs save today's constituent observation **before** loading the
historical dataset, checking the replay certificate, or fetching other market
inputs. Those later failures still fail the run and leave the portfolio
unchanged, but no longer lose an otherwise available membership observation.
The collector also captures membership before warm-up, index and calendar
checks when called directly. Historical reference-period runs remain offline.
Pre-18:00 IST captures are informational; the after-close run must fetch a
fresh same-date snapshot. A morning capture alone does not cover that close.

If an existing book is missing an earlier session's snapshot, rerunning Golden
Replay cannot recreate it. Resume only with independently dated official
evidence, or explicitly choose a **new portfolio ID** starting from cash on a
new observed session. Preserve the old book and its history; do not backdate
today's list, silently carry membership forward, or skip the missing sessions.
When choosing a new book, update both the daily-form defaults and the existing
schedule's portfolio ID so the scheduler does not keep targeting the blocked
book.

Older stocks newly entering the universe use the existing raw NSE bar store
and verified actions for a 315-session warm-up (enough for the 252-session
high throughout the x63 window). Missing established-stock history blocks
operation instead of quietly dropping that constituent. Missing quotes in a
complete bhavcopy mean non-trading, not an inferred delisting. Unresolved
reorganizations need review; synthetic demerger normalization still does not
deliver actual child shares.

As explicitly selected for this paper test, **voluntary buybacks and rights
offers are not participated in**: no tender, subscription, new units, cash
credit or price adjustment is invented. The market-price movement stays in
the model and the notices appear in readiness/provenance. Other unresolved
mandatory reorganizations still require review. Dividends retain the original
no-cash-credit, no-price-adjustment convention.

The daily result retains ingestion readiness and provenance under
**Diagnostics and assumptions**; actionable waiting/failure messages remain visible.
Raw downloads and dated observations persist in the application's local
SQLite store, separately from model books and artifacts.

Native daily fingerprints use `s18-nse-day-v2`: calendar dates, session status
and actual A/B review flags participate in the resume check, not the raw hash
of the calendar webpage. Republishing an unchanged calendar therefore does
not invalidate the portfolio. Raw publication evidence is still retained
separately. A real correction to a consumed session or its review decision
still blocks silent rewriting of the book. Existing v1 books need a verified
metadata migration; the engine must not simply ignore a fingerprint mismatch.

## Running the workflow

With the dataset in the app database, use the normal registry commands.
There are no reference-folder settings to enter:

```powershell
python run.py s18_replay
python run.py s18_backtest --param combo=P15 --param metal_mode=both_priority --param start=2014-01-01 --param end=2026-08-31 --param capital=100000
python run.py s18_daily --param book_id=s18-p15-forward --param capital=500000 --param persist=false
python run.py s18_daily --param book_id=s18-p15-forward --param capital=500000
```

Replay checks all 15 combo/mode combinations and both tranches: exact symbols,
entry/exit dates and reasons; rounding-tolerant prices, basis and gains;
open-book agreement; daily NAV agreement; and Sharpe difference **below 0.001**.
The service stores certificates tied to the current engine/data/runtime.
UI and scheduler Python environments retain separate certificates rather than
overwriting each other's approval. Run replay using the same interpreter and
dependencies as each daily runner; a UI replay does not certify a different
scheduler environment. A mismatch
is a failed run, not a warning to dismiss. A normal one-combo backtest does
not replace certification.

Daily refuses to advance without a current certificate. Collector-only code
updates can preserve a book after a new successful replay when its book/rule
fingerprint and original data are unchanged; rule/schema changes require review.
A new `book_id`
starts from **cash on the first requested available session**, not the 2026-08-31
reference holdings. Reusing the same group catches up each subsequent session
in sequence. Initial capital is used only at creation; it does not re-capitalize
an existing book. Use a separate identity for a genuinely independent experiment.
A new group creates a separate cash book, **not a reset of the current book**.
Daily initializes S2's lag-capacity history as `[0, 0, 0, 0, 0]`, enforcing a
real five-session startup wait rather than the legacy reference's first-row
startup behavior.

`persist=false` previews without updating the saved theoretical book.
The workbench still stores the run report/history, so “dry run” does not mean
“no local records.” The `as_of` parameter tracks today's date for an explicitly
configured schedule, but **no S18 schedule is installed or enabled by default**.

### Prepared forward-test schedule

`backtesting.s18.schedule.prepare_schedule` creates or updates a **disabled**
workbench schedule and prefills the daily form with the chosen book settings.
The requested setup is P15 / priority metals, total paper capital INR 500,000,
book ID `s18-p15-forward`, at **19:00 Asia/Kolkata every day**. Calendar validation
handles non-trading days; running every day also permits documented special
sessions. It does not retarget the existing scheduler or change other jobs.

The selected schedule remains **disabled until merge and deployment**.
After deploying this branch into the checkout used by the running scheduler,
run Golden Replay in the scheduler's Python environment, run S18 Daily once
to inspect ingestion readiness, then enable the prepared schedule in
**Automation & Schedules**. A prepared disabled row is not an active daily run.

### Model fills cannot be manually confirmed or replaced

Close decisions fill at the next available session open under the reference
rules. Armed S1 trailing stops instead test the intraday low, filling at the
lower of open and stop when triggered. Unarmed stops do nothing; S2 has none.
Pending sells can wait for an actual tradable session; a non-trading queued
buy is not silently treated as filled.

The UI has no fill editor or “confirm orders” button for S18. A broker fill
or contract note must never alter the theoretical ledger. Actual STT, stamp
duty, exchange fees, GST and DP charges belong only in **shadow cost fields**.
In particular, **never import real stop executions into model fills**.
**Slippage is untested**; model returns do not establish achievable execution.

### Attaching shadow contract-note charges

The daily form's **Advanced controls → Contract-note charges by model fill ID**
accepts `shadow_charges` JSON, default `{}`. Read IDs such as `A-1` and `B-2`
from the **Model fills and shadow charges** table or its downloadable `fills`
CSV. The mapping for each ID accepts these **nonnegative numeric amounts**:
`stt`, `stamp_duty`, `exchange_fees`, `gst`, `dp_charges`, `brokerage`, `other`.

```json
{
  "A-1": {"stt": 2.5, "stamp_duty": 0.3, "exchange_fees": 0.2, "gst": 0.1},
  "B-2": {"dp_charges": 15.0, "brokerage": 0, "other": 0}
}
```

The service attaches the breakdown and its total to separate model-fill
`charge_breakdown` and `actual_charges` fields. **It never changes theoretical
cash, quantity, entry/exit price, basis, stops or NAV.** `{}` makes no changes;
dry-run/persist controls still apply. These are charge annotations keyed to
existing model fills, not actual-fill imports or confirmations, and no
automated contract-note download/import is implied.

## Reference conventions and known quirks

The implementation preserves these reference behaviors transparently rather
than quietly “correcting” them and losing replay comparability:

1. Reference engine rows begin **2013-12-31**, a signal-only row, before the
   reported period beginning 2014-01-01. Reference initialization forces a
   monthly review on that first row.
2. The historical replay snapshot makes **no last-day close decisions**.
   The reference B calendar excludes the final row before shifting month-ends,
   so **August 2026's terminal month-end is not shifted ten sessions earlier**.
   Its final row remains flagged, but the reference engine suppresses decisions
   there. Golden replay preserves this terminal convention.
   Paper daily instead uses the **explicitly complete exchange-session
   calendar**, makes close decisions on its final observed session, and runs a
   monthly review there only when that calendar calls for one. It never infers
   a review just because a dataset ends; replay and daily therefore do not have
   identical terminal-calendar behavior.
3. Monthly **S2 momentum exits precede funding**, determining exit-reason
   precedence when more than one rule would apply.
4. When S1 cash is short, allocation is apportioned by **slot weight**, not
   equally per symbol; two-slot metals therefore receive their relative share.
5. Model transaction cost is **2 bps per side**. Reference tax is 20% short-term
   and 12.5% long-term, with **no exemption**, annual payment and reference
   set-off rules. Loss carry pools have **no expiry in the reference**.
   These are backtest assumptions, **not tax advice**.
6. Sharpe uses daily returns with **population standard deviation** and a
   **6.5% annual risk-free rate**, not a sample-standard-deviation substitute.
7. Historical metal proxies and the ETF equity-tax convention limit
   interpretation of the metals comparison.

## Results, downloads and persistence

S18 results use the common `StrategyResult` envelope. The report accompanies
structured `metrics`, `validation`, `holdings`, `orders`, `trades`,
`fills`, `equity_curve`, `portfolio_state`, `artifact_group_id`, `results_dir`
and `warnings` where applicable. The UI preserves tranche and sleeve columns,
shows armed names and stops separately, and provides the model curve and
validation evidence.

Download CSVs for holdings, orders, fills, trades and the curve; JSON for complete
state and validation; and the report/structured result. Persisted dossier
artifacts are loaded from **`core.storage.get_artifact`**, not interpreted as
filesystem paths. They live in the configured application SQLite database,
not an external experiment folder.

**Automatic project exports:** every replay and backtest, plus each ready
daily run with `persist=true`, exports the same DB-saved artifact group to
`reports\s18\<artifact_group_id>` and returns that directory as `results_dir`.
No output-path parameter, form or separate export command is needed. This
includes the group's XLSX, CSV, JSON and report artifacts where applicable.
`write_dossier=false` omits the backtest XLSX workbook, but the other result
artifacts are still saved and automatically exported. Daily dry runs and
not-ready runs do not create a persisted daily artifact export.

The generated project files are **Git-ignored, not committed**, and SQLite
remains the authoritative, durable store. To recreate a local copy or export
a stored group to another destination, the existing maintenance command
remains available:

```powershell
python -m core.storage list-artifacts --limit 20
python -m core.storage export <group-id> .\reports\s18\<group-id>
```

The exports are supporting copies, not the primary store. Pre-existing run
records may retain old source paths as immutable audit history; those paths
are not consulted as runtime dependencies.

Back up the application database to preserve the dataset, authoritative paper
state, live evidence, run history, dossiers and certificates. A downloaded
portfolio JSON is an inspection/backup artifact,
not a supported UI mechanism for importing manual fills or bypassing validation.

## Optional legacy maintenance/test adapter

`backtesting.s18.feed` retains an offline CSV adapter for controlled maintenance
and fixture tests. It is **not the normal product workflow**, has no daily UI
data-source selector and is not required to run the DB-owned strategies.
Its internal file schemas are an adapter contract, not files that users must
prepare for daily operation. Do not run legacy reference-generation scripts
to replace the imported golden evidence.
