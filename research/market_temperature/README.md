# Market Temperature

A long-horizon read on whether an equity index is unusually cheap or expensive
relative to its own history — used to decide **how fast to deploy new money**,
not to trade.

Reachable in the workbench at **Ideas & research → Market Temperature**.

## Why this exists, and what it deliberately does not do

This started as a downloaded contrarian allocation framework ("buy when everyone
else is scared"). Before putting it on screen it was reviewed and tested. It
failed as a trading strategy:

| Index | Out-of-sample edge vs a fixed stock/cash mix | Verdict |
|---|---|---|
| SENSEX | +0.44%/yr (p = 0.013) | passed |
| NIFTY 50 | −0.22%/yr (p = 0.64) | failed |
| NASDAQ | −0.80%/yr (p = 0.20) | failed |

Measured after costs and an allowance for capital-gains tax, against the honest
benchmark: holding a fixed allocation at the strategy's *own* average weight. An
edge that appears in one market and reverses in another is not something to
trade. Reproduce with:

```bash
python -m research.market_temperature.validate
```

Full working in [`VALIDATION.md`](./VALIDATION.md).

So the module is scoped to the one decision where a weak signal is still worth
having: **the pace at which new cash is deployed**. That decision has to be made
anyway and costs nothing extra, unlike churning an existing portfolio, where
turnover and tax comfortably exceed the measured edge.

The dashboard will never suggest selling an existing holding or pausing a SIP.

## How the reading is produced

```
daily closes (yfinance, cached 12h)
   └─ month-end resample
        └─ accrue assumed dividend yield  ->  approximate total-return index
             └─ 7 rules, each voting -2..+2
                  └─ weighted average (fixed denominator)  ->  composite score
                       └─ zero => Neutral;  otherwise ranked against
                          same-signed history  ->  Cool/Cold or Warm/Hot
```

### The rules

| Rule | Horizon | Fires when | Weight |
|---|---|---|---|
| 12-year flat market | 12y | \|total return\| ≤ 15% | 2.0 |
| 10-year run too hot | 10y | CAGR ≥ 20% (−1), ≥ 28% (−2) | 1.5 |
| 8-year flat market | 8y | \|total return\| ≤ 15% | 1.5 |
| 5-year return below cash | 5y | CAGR < 6.5% | 1.0 |
| 3-year drift | 3y | total return within ±10% | 1.0 |
| Parabolic move | 1–2y | best of 1y/2y return ≥ 200% | 1.5 |
| Deep active drawdown | 12m | **currently** 30–55% below the trailing peak | 1.0 |

Three of these (12-year, 8-year, parabolic) have **never fired** in the available
history. They are retained for transparency and flagged in the UI rather than
quietly dropped.

Thresholds are the framework's originals and were **not tuned** on the data.
Fitting them would produce a prettier backtest and worse future behaviour.

## Bugs fixed relative to the source framework

Each is pinned by a test in `tests/test_market_temperature.py`.

- **One-sided 3-year band.** The original tested `return <= +10%` with no lower
  bound, so a 65% crash was classified as a quiet sideways market and scored as
  "aggressive contrarian accumulation" — a falling-knife generator. Now
  two-sided.
- **Correction rule fired after recovery.** It used the maximum drawdown
  observed anywhere inside a trailing window, never comparing the current price
  to the peak, so a crash followed by a full recovery still read STRONG_BUY. Now
  measures the drawdown that is live right now.
- **Window arithmetic crashed on fractional years.** `pd.DateOffset(years=0.5)`
  raises. All windows are now day offsets.
- **Composite denominator shrank.** Rules that could not be evaluated were
  dropped from the weighted average, so the same conditions produced different
  scores depending only on how much history was loaded. Unevaluable rules now
  score zero but stay in the denominator.
- **Silent synthetic data.** The original fell back to a seeded random walk on
  any download failure, logging only a warning — and two of its shipped indices
  are delisted on Yahoo, so several published signals were pure noise. There is
  **no fallback here**; a failed load raises and the page says so.
- **A silent signal looked confident.** An earlier revision of *this* module
  ranked today's score as a percentile of all past scores. Because zero is by far
  the most common value, a completely silent signal landed in the 82nd percentile
  and was labelled "Cool — deploy faster". Zero now always maps to Neutral.

## Layout

| File | Contents |
|---|---|
| `config.py` | Markets, rule metadata, temperature bands, deployment plans |
| `signals.py` | Clean-room rule implementations and the composite |
| `data.py` | Cached index loading, total-return conversion, no fallback |
| `service.py` | Assembles the reading, bands, and forward-return evidence |
| `validate.py` | Reproducible validation run; exercises the shipped `signals.py` |
| `VALIDATION.md` | The full review and the backtest that rejected it |

UI lives in `ui/market_temperature.py`.

## Known limitations

- **Dividends are assumed, not measured.** Index-level payout history is not
  freely available, so a constant yield is accrued. This matters most for the
  long-horizon "went nowhere" rules, where a 1.3%/yr yield compounds to ~17pp
  over 12 years — wider than the rules' own ±15pp band.
- **Overlapping windows overstate the sample.** Monthly readings at a five-year
  horizon share nearly all their underlying data. The UI reports an "independent
  windows" count alongside the raw month count for this reason.
- **The framework's valuation half is missing.** The original also used index
  P/E, P/B and bond-yield comparisons. Reliable point-in-time history for those
  is not freely available, and NSE changed its P/E methodology in 2021 (standalone
  to consolidated earnings), breaking comparability across that date.
- **Index-level only.** It says nothing about individual stocks, sectors, or your
  own portfolio.

## Usage

```python
from research.market_temperature import MARKETS, compute_market_temperature

reading = compute_market_temperature(MARKETS["sensex"])
print(reading.band.label, reading.score, len(reading.active_rules))
```
