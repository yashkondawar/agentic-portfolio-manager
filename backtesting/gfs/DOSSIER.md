# The GFS results dossier

`run_dossier.py` produces a single Excel workbook that answers, in one place,
"what would this strategy actually have paid me?" It is the artifact you hand
to someone who was not in the room while the strategy was built.

```powershell
python -m backtesting.gfs.run_dossier --start 2016-01-01 --capital 10000000 --out reports\gfs_dossier.xlsx
```

It takes a couple of minutes: the indicator panels are built once and then three
full backtests run over them.

## Why three columns instead of one number

Every headline metric appears three times:

| Column | What it is |
|---|---|
| **Before cost & tax** | The strategy's raw edge. Useful only for comparing rules against each other. |
| **Before tax** | Brokerage and slippage deducted. What a tax-free account would have made. |
| **Portfolio (net of cost+tax)** | Capital-gains tax debited from cash every April. **This is the real number.** |

These are three *separate engine runs*, not one run with percentages subtracted
afterwards. That distinction matters more than it sounds:

- Costs change which trades are affordable, so a costed run does not take the
  same trades as a free one.
- Tax paid in year three is capital that cannot compound in year four. Deducting
  it at the end would understate the damage.

On the current configuration the gap is 26.97% -> 22.96% CAGR: **4.01% a year
handed over in frictions**, of which tax is by far the larger share. Any research
result quoted before tax is quoting a number you will never receive.

## The reconciliation identity

The workbook is only worth trusting if the sheets agree with each other. The
binding constraint is:

```
starting capital + realised P&L - tax paid + unrealised mark = final equity
```

where realised P&L nets *both* commission legs. `tests/test_gfs_dossier.py`
asserts this to the rupee (with cash yield switched off, since interest on idle
cash is the one credit no trade row accounts for). If a future change starts
applying a cost or credit that no sheet discloses, that test fails.

A related trap, worth stating because it silently flatters results: the closing
financial year's tax bill falls due the *following* April, which is after the
backtest ends. Without a deliberate final settlement, the last year's gains get
reported in `Tax_Ledger` but never deducted from equity. In testing this was 36%
of the entire tax bill. The engine now settles on the last session. Tax on
*unrealised* gains is still correctly not charged.

## The sheets

| Sheet | Use it to answer |
|---|---|
| **Summary** | Everything at a glance, plus the exact configuration that produced it. |
| **Equity_Curve** | Daily equity, cash, deployed capital, drawdown, and four rebased reference series. |
| **Positions** | One row per round trip: entry, exit, why it exited, and the P&L split into short/long-term. |
| **Trades** | One row per *fill*. A scaled-out position is one Positions row but several Trades rows. `cash_after` lets you audit the cash book line by line. |
| **Yearly_Returns** | Calendar-year returns against three benchmarks. Measured from the prior year's close, so a partial first year does not distort. |
| **Rolling_3Y / Rolling_5Y** | The honest version of "how has it done". Windows step monthly. The worst window matters more than the average. |
| **Daily_Returns_Portfolio** | Raw daily series if you want to run your own statistics. |
| **Tax_Ledger** | Per financial year, with loss set-off and carry-forward applied. |

### Three benchmarks, not one

`NIFTY 50` and `NIFTY 500` are the obvious ones. `Universe EW` - a daily-rebalanced
equal-weight basket of every name in the universe - is the one that actually
tests the strategy.

GFS picks names out of a 500-stock universe. If that universe as a whole beat the
NIFTY 50, then beating the NIFTY 50 proves nothing about the *picking*: you would
have done as well throwing darts. `Universe EW` is that dart-throwing null
hypothesis. It is deliberately not tradeable (daily rebalancing across 500 names
is a fantasy); it is a control, not a proposal.

## Reading the metrics without fooling yourself

- **Alpha** is annualised by compounding the daily intercept, `(1+a)**252 - 1`,
  not by multiplying by 252 - which would overstate it substantially.
- **Sortino's** downside deviation divides by the *full* sample, not by the count
  of down days. Dividing by the latter rewards a series merely for having few
  losing days, which is the opposite of what the metric is for.
- **Beta near 0.45** is mostly an artifact of sitting in cash ~36% of the time,
  not of holding low-beta names. Do not read it as defensiveness.
- **Long-term gains are zero** in every financial year. Average holding is ~62
  days, so nothing ever crosses the 365-day line. GFS is taxed entirely at the
  short-term rate. This is structural, not a data problem.

## The caveat that matters most

The universe is **today's** NIFTY 500 constituents. Membership today is partly a
consequence of having performed well during the test window, and companies that
were delisted or merged are absent entirely. Every return in this workbook is
therefore an optimistic upper bound.

This is not a small effect over a ten-year window. To size it, run the same
dossier against `--universe nse_all` and compare. The reference workbook this
format was modelled on has the same limitation.

## Flags

| Flag | Default | Notes |
|---|---|---|
| `--start` / `--end` | 2016-01-01 / today | |
| `--capital` | 10,000,000 | Sizing is percentage-based, so scale barely matters except for lot rounding. |
| `--universe` | from `gfs.config` | `nifty500`, `nifty200`, `nse_all`, ... |
| `--benchmark` | `^NSEI` | |
| `--no-tax` | off | Drops the net column. Only useful for comparing against older pre-tax studies. |
| `--no-cache` | off | Forces a fresh bar fetch. |

The strategy parameters are **not** flags. `run_dossier` imports `LIVE_DEFAULTS`
and `PINNED` from `gfs/config.py` - the same module the live runner uses - so the
dossier cannot describe a configuration you are not actually trading. To change
what the dossier measures, change what you trade.
