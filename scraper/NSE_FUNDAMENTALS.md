# NSE historical fundamentals extractor

`scraper/nse_fundamentals.py` pulls **as-filed quarterly results straight from
NSE**, back to 2012. It exists to lift the `qtr_results` backtest out of the
~2.4-year window imposed by the screener.in cache, whose quarterly table is
capped at 13 columns.

It is a prototype: it has been validated against the screener cache, but the
full 2012-2026 backfill has not been run.

## Why NSE rather than a paid vendor

Cost is the least interesting reason.

1. **As-filed is genuinely point-in-time.** EODHD, FMP, screener.in and Prowess
   all silently backfill restatements. Over 12 years that is a large lookahead
   bias. Concrete case found during validation: BHEL's Dec-2023 quarter was
   *filed* as a ₹148.8 cr loss, and that is what the market reacted to;
   screener now shows a ₹60 cr profit. Only the filed number is tradeable.
2. **Authoritative announcement timestamps.** `broadCastDate` is the moment the
   result became public, so signals can be dated exactly. The last backtest run
   had to fall back to an *estimated* reporting lag for 2,319 of 3,925 events.
3. **`isin` is present**, which is the only reliable join key across a decade of
   ticker renames.
4. Delisted issuers' filings stay in the archive, so the survivorship problem is
   not made worse.

Access needs no Playwright and no proxies — a warmed-up `requests` session with
a `User-Agent` and `Referer` is enough, and sustains ~14 req/s.

## The two eras

NSE changed format around 2019, and the index row tells you which applies:

| Era | Field to use | Format |
| --- | --- | --- |
| 2012 - ~2018 | `resultDetailedDataLink` | HTML table, `Rs. in lakhs` |
| ~2019 - now | `xbrl` | Ind-AS XBRL, absolute rupees |

Pre-2017 rows *do* carry an `xbrl` field, but it is the placeholder
`.../corporate/xbrl/-`, which 404s. `resultDetailedDataLink` is empty from 2020
onward. Everything is normalised to **crores** to match the screener cache;
EPS is never scaled.

## Three traps this module exists to avoid

### 1. `OneD` vs `FourD` — reading the year as a quarter

A filing repeats the same tags for the quarter, the year-to-date and the prior
year. Taking the first regex match mixes a 3-month figure with a 12-month one.

The obvious fix — match the XBRL `<context>` dates against the filing's own
period — **does not work**. NSE routinely declares `FourD` (year-to-date) with
the *quarter's* start and end dates while filling it with the cumulative value.
In Coromandel's Q4 FY24 filing both contexts claim `2024-01-01 → 2024-03-31`,
yet `OneD` holds ₹3,912 cr (the quarter) and `FourD` holds ₹22,058 cr (FY24).

Worse, the `OneD` context is often **never declared at all** — it appears only
as a `contextRef` value, so date matching finds nothing to match.

So the context *id* is the signal, per the Ind-AS convention:

```
OneD   current 3 months      FourD  year to date
TwoD   preceding 3 months    FiveD  prior year to date
ThreeD same quarter LY       SixD   previous full year
```

`OneD` is preferred; date matching is only a fallback, and `FourD`/`FiveD`/
`SixD` are never used as one. Ignoring this understates nothing and overstates
revenue by up to 4x — it took sales accuracy from 18% to 89%.

### 2. Operating profit is EBITDA, not EBIT

XBRL `Expenses` bundles depreciation and finance costs; screener's `Expenses`
row excludes both and lists them separately. Comparing directly yields an EBIT
margin, which for asset-heavy names is negative where screener shows a profit.
Delhivery Q4 FY24: `2075.5 − 2257.2 = −181.7` (wrong) versus
`2075.5 − 2257.2 + 200.4 + 27.1 = 45.8` (matches screener's 46).

Operating profit is therefore always reconstructed as
`sales − expenses + depreciation + finance costs`. This took OPM accuracy from
5% to 95%.

### 3. Banks file a different schedule

There is no sales line — the comparable top line is `Income` (interest earned +
other income) — and interest expense **is** an operating cost, so the EBITDA
add-back must not fire. Bank filings state
`OperatingProfitBeforeProvisionAndContingencies` directly; it is captured into
its own field and `QuarterlyResult.is_bank` flags the row so downstream code can
branch, as the live strategy already does.

Pre-Ind-AS bank labels also write `Net Profit(+) / Loss(-)` where later filings
write `Net Profit / (Loss)`, so labels are canonicalised (sign markers and
brackets stripped) rather than enumerated.

## Measured accuracy

630 company-quarters over Dec-2023 → Mar-2025, joined to
`fundamentals_500sym.pkl`. Match = within 2% (1.5pp for OPM).

| Field | Match |
| --- | --- |
| Net profit | 95.7% |
| OPM | 94.6% |
| Sales | 89.0% |
| EPS | 78.4% |

The residual is **definitional, not parse error**:

- **EPS.** 64 of the misses are exactly 2x/5x/10x with net profit matching
  exactly — screener retro-adjusts EPS for splits and bonuses, we report
  as-filed. The rest are share-count drift for the same reason. As-filed is
  correct point-in-time, but note that YoY EPS *growth* across a corporate
  action needs adjustment (see caveats).
- **Sales.** Concentrated in demerged or merged issuers (ABFRL, ABREL, ABDL,
  ASTERDM, COHANCE), where screener shows restated continuing-operations
  history and we show what was filed.
- **Net profit.** Mostly standalone-versus-consolidated preference, plus
  minority-interest treatment for banks.

## Usage

```python
from datetime import date
from scraper import nse_fundamentals as nf

rows = nf.collect_quarter(date(2024, 1, 1), date(2024, 3, 10))
best = nf.select_best(rows)          # one record per (symbol, quarter)
best[("TCS", "Dec 2023")].to_dict()
```

`from_date`/`to_date` filter on the **announcement** date, not the period, so a
December quarter is collected by scanning the following January-February.
`select_best` prefers consolidated filings, then the most complete record.

Requests are throttled to ~3/s (`MIN_REQUEST_INTERVAL`); NSE tolerates far more,
but a backfill is a one-off. Roughly 15% of pre-2019 archive links 404 because
the issuer was renamed or delisted; those return `None` without retrying.

## Storage: one table, two sources

Everything lands in `scraper/fundamentals_store.py`, in the app's durable
SQLite DB (`%LOCALAPPDATA%`, outside the repo), keyed `(symbol, period_end,
consolidated)`. Filings are immutable and expensive to collect, so this is a
permanent archive rather than a cache — nothing expires it.

The important property is that **every source writes the same
`QuarterlyResult` shape into the same table**, distinguished only by the
`source` column. That is what makes history appendable: NSE's as-filed archive
and screener's recent tail union into one continuous series, with no bridging
code in the backtest.

Because the sources overlap and disagree, writes are **ranked**
(`fundamentals_store.SOURCE_RANK`). As-filed (`xbrl`, `html`) always beats
restated (`screener`), enforced in the upsert's `WHERE` clause, so:

- re-importing screener can never overwrite a filing scraped from the exchange;
- import **order does not matter**, so both jobs can be scheduled independently
  without coordination.

| source | coverage | as-filed? | declaration date |
|---|---|---|---|
| `xbrl` / `html` | Dec-2011 → Dec-2024 | yes | NSE broadcast timestamp |
| `screener` | Mar-2025 → current quarter | no, restated | NSE board-meeting calendar |

### Refreshing the recent tail

NSE stops serving regular filings after ~Mar 2025 — the dated archive, the
per-symbol feed and the event calendar all agree, so this is an NSE-side gap,
not a scraping problem. Screener fills it:

```bash
uv run python -m scraper.screener_fundamentals            # import recent quarters
uv run python -m scraper.screener_fundamentals --status   # coverage by source
```

Declaration dates for those quarters come from NSE's event calendar
(`/api/event-calendar`), which is one request per month for the whole market
and *does* still serve the current quarter. Rows without one fall back to the
engine's estimated reporting lag; in practice ~98.7% of stored quarters carry a
real date.

## Backfill

`scraper/backfill_nse_fundamentals.py` walks announcement windows from 2012 to
today and writes into the same store. It is resumable at two levels —
completed windows are skipped whole, and individual URLs already fetched (or
already known to 404) are never retried — so re-running is a cheap no-op.

```bash
uv run python -m scraper.backfill_nse_fundamentals --status          # coverage report
uv run python -m scraper.backfill_nse_fundamentals --from 2012-01-01 # run/resume
```

### Coverage as collected

| | |
|---|---|
| Quarters | 19,975 |
| Symbols | 490 |
| Range | Dec-2011 → Jun-2026 |
| With a real declaration date | 19,717 (98.7%) |
| As-filed / restated | 17,369 / 2,606 |

Field completeness on the as-filed portion: net profit 99.9%, EPS 99.5%, sales
97.2%, operating profit 97.1%. Parse rate by era: 2012-2017 ~87%, **H2-2018
57-64%**, 2019 ~93%, 2020-2024 97-100%. The 2018 dip is the HTML→XBRL
transition, where both link fields are unreliable; it costs candidates in that
stretch, not correctness.

The full run takes ~45 minutes at the default ~8 req/s. Plain `requests` is
enough — no Playwright, no proxies, and no blocks over a sustained 45 minutes.

## Caveats and open work

- **The recent tail is restated, not as-filed.** Quarters from Mar-2025 carry
  screener's revised figures on their original reporting dates, which is mild
  lookahead bias. Everything before that is genuinely point-in-time.
- **Annual data is not covered.** The strategy also needs Borrowings, Equity
  Capital, Reserves and ROCE. The screener cache already reaches Mar-2018 for
  these (Mar-2015 on the live site), so this is a smaller gap — but it is a gap,
  and before FY2018 the debt and ROCE gates do not fire at all.
- **Survivorship bias is a separate problem.** This gives point-in-time
  *fundamentals*; it does not give point-in-time *index membership*. That needs
  historical constituents (e.g. niftyhistory.in). Over a 13-year window this is
  now the single largest distortion in any backtest built on this data.
- Pre-2016 label coverage is verified against a small sample. Label drift is the
  most likely source of failures when extending below 2016.

### Resolved

- ~~Not yet backfilled~~ — done, see above.
- ~~Where to store 12 years of results~~ — one ranked, source-tagged table.
- ~~EPS across corporate actions~~ — `backtesting/qtr_results/nse_source.py`
  recovers the implied share count from each filing (`net_profit / eps`, both
  from the same document), takes the median of the last 12 as one reference
  count per symbol, and restates the series on it. This makes EPS growth
  identical to net-profit growth, keeps `price / EPS` internally consistent,
  and — because EPS becomes a function of net profit and one constant — erases
  any discontinuity where as-filed and split-adjusted sources meet. It cannot
  leak, because growth rates and P/E are invariant to the constant.

## Tests

`tests/test_nse_fundamentals.py` runs fully offline against four real filings in
`tests/fixtures/nse/`, chosen to pin each trap above: Coromandel Q4 FY24 (the
`OneD`/`FourD` collision), Delhivery Q4 FY24 (EBITDA add-back), HDFC Bank
Q3 FY14 (bank schedule, label punctuation) and TCS Q3 FY14 (lakh conversion).
