"""
build_dossier.py
================

CLI that produces the Excel **results dossier** for the live ``qtr_results``
strategy.

Unlike ``run_backtest.py``, which exists to compare research configurations,
this entrypoint deliberately runs ONE configuration: the one that mirrors what
the live strategy is doing right now (see ``config.live_mirror_config``). The
point of the dossier is not "which settings win?" but "what did my actual
strategy earn, after brokerage and after tax, against the market".

Examples
--------
    # Default: Nifty 500, the full window the cached fundamentals support
    python -m backtesting.qtr_results.build_dossier

    # Explicit window and output path
    python -m backtesting.qtr_results.build_dossier \
        --start 2023-07-10 --end 2026-07-08 --out reports/qtr_results.xlsx

    # Same run, but sized to a different starting capital
    python -m backtesting.qtr_results.build_dossier --capital 10000000
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from backtesting.gfs.taxes import TaxConfig
from core import bars

from .config import (
    FUND_CACHE_DIR,
    FUNDAMENTALS_SOURCES,
    PRICE_CACHE_DIR,
    live_mirror_config,
    normalize_fundamentals_source,
)
from .data import FundamentalsStore, PointInTimeData, ResultsCalendarStore, SectorStore
from .dossier import build_dossier, write_workbook
from .engine import BacktestEngine
from .metrics import compute_metrics, enrich_metrics

logger = logging.getLogger("backtest.qtr.dossier")

#: NSE code for the NIFTY 500 in the shared bar store.
NIFTY500 = "^CRSLDX"

DEFAULT_OUT = Path("backtesting/qtr_results/results/qtr_results_dossier.xlsx")

#: First quarter the strategy can actually grade. Screener.in's cached history
#: starts at the Mar-2023 quarter for most names, and the year-on-year growth
#: screen needs a year-ago comparable, so Mar-2024 (declared from late Apr 2024)
#: is the first evaluable result. Starting earlier does not test the strategy —
#: it just parks capital in cash and depresses the CAGR for a data reason.
FIRST_TRADEABLE = date(2024, 4, 1)

#: With as-filed NSE data the constraint moves back to the archive itself: the
#: index reaches Jan 2012, and the year-ago comparable pushes the first gradeable
#: result to the Mar-2013 quarter.
FIRST_TRADEABLE_STORE = date(2013, 7, 1)

#: Point-in-time mode is bounded by the membership record rather than by the
#: fundamentals: the reconstructed NIFTY 500 history is only trustworthy from
#: 2014-01-01, before which every constituent is an assumption. Starting earlier
#: would mean screening against a guessed index, which is the bias this mode
#: exists to remove.
FIRST_TRADEABLE_PIT = date(2014, 1, 1)

#: Carried into the workbook so nobody reads these numbers without the caveats.
LEAD_NOTES = (
    "Mirrors the LIVE qtr_results configuration, not the backtest defaults: risk "
    "per trade 4%, static target tiers 20/15/10%, 90-day time stop, ATR(14)x6 "
    "trailing stop, 0.20% per-side cost.",
    "The live Tier-2 LLM conviction gate has no point-in-time equivalent and is "
    "NOT represented here. These results reflect the mechanical screen only, so "
    "they neither credit nor penalise that layer.",
)

#: Used when the run screens against the index as it stands today.
BIASED_UNIVERSE_NOTES = (
    "SURVIVORSHIP BIAS is present and NOT corrected here. The universe "
    "is TODAY's NIFTY 500 projected backwards, so names that were delisted, "
    "acquired or that collapsed out of the index never appear, while names that "
    "earned their way in are present from the start. Rerun with --point-in-time "
    "to remove it. Measured on the 2014-2026 window that correction costs about "
    "1.0 percentage points of CAGR and widens the worst drawdown, so treat the "
    "numbers here as an upper bound.",
    "Benchmarks are price indices and this run credits no dividends, so the "
    "strategy curve excludes them too. The comparison is like-for-like on that "
    "point; it is net of costs and, in the first column, net of capital-gains "
    "tax, which errs slightly against the strategy.",
)

#: Swapped in for the survivorship warning above when the run is point-in-time.
PIT_NOTES = (
    "SURVIVORSHIP BIAS is REMOVED in this run. The universe is reconstructed "
    "index membership: a company is a candidate on a given day only if it was "
    "in the NIFTY 500 that day, had actually traded on the exchange by then, "
    "and ranked inside the top 900 of the whole market on trailing 6-month "
    "turnover. 951 distinct companies pass through the index over the window "
    "against 500 in it today, and the ~450 that left -- through delisting, "
    "acquisition or collapse -- are traded here and then stop, on the date they "
    "actually stopped.",
    "Prices are the NSE bhavcopy tape, which records every symbol that traded "
    "on a day including ones that no longer exist, rather than yfinance, which "
    "serves only surviving listings and truncates the failures. Splits and "
    "bonuses are back-adjusted from NSE corporate-action filings we parse "
    "ourselves, so the series is reproducible; raw exchange closes are never "
    "restated behind our back.",
    "Cash dividends are credited to the account on the ex-date rather than "
    "folded into the price. Vendor 'adjusted' series remove the ex-date drop, "
    "and because this strategy exits on an ATR trailing stop, a series without "
    "that drop quietly flatters every stop-based exit: on a like-for-like "
    "comparison 382 of 402 trades were identical and the 20 that differed were "
    "all a real trailing stop being replaced by a later, kinder time stop. "
    "Keeping the drop and paying the cash separately is the only treatment "
    "that is right in both directions. Measured payout is ~2.3-2.6% a year on "
    "deployed capital.",
    "The adjustment was validated by counting single-day falls worse than 40% "
    "across 2.4M returns: 380 raw, 11 after adjustment, none introduced. The 11 "
    "that remain are real collapses -- DHFL, YES Bank, Jet Airways, Infibeam "
    "and four microcap failures -- and are deliberately left in the data. "
    "Removing them by inference would erase genuine losses and put the upward "
    "bias straight back.",
    "Because the account now receives dividends while the NIFTY benchmarks "
    "remain price indices that exclude them, the benchmark comparison in this "
    "run favours the strategy by roughly the index yield. Read the absolute "
    "return as sound and the outperformance as flattered by about 1-1.5% a "
    "year.",
    "Two residual limits are worth naming. Index entries before press-release "
    "coverage are back-dated by the membership source, so the liquidity rank "
    "above stands in for the market-cap test NSE actually applies; it was "
    "calibrated on 2022-2025, where membership is exact, to retain >=99% of a "
    "known-correct list. And demergers cannot be restated from a filing alone, "
    "so those dates are flagged and excluded rather than guessed.",
    "One bias is removed on the universe but not yet on the fundamentals. "
    "Filings after March 2025 come from a survivor-only cache and cover ~455 "
    "companies against ~1,500 in earlier quarters, so the final stretch grades "
    "a narrower, survivor-only candidate pool. Note this does NOT mean the tail "
    "should be dropped to get a cleaner number: ending the run at 2025-03-31 "
    "RAISES CAGR from 12.7% to 15.1%, because 2024-25 was the strategy's worst "
    "stretch. The full window is the conservative claim and is the one to "
    "quote; the weaker tail coverage is a caveat on that number, not a licence "
    "to truncate it.",
    "Historical NIFTY 500 membership is derived from "
    "github.com/aditya-jha/nse-historical-membership, used under CC BY 4.0. "
    "Measured against NSE's current official list it agrees on 497 of 500 "
    "names.",
)

TAIL_NOTES = (
    "The 90-day time stop means essentially every exit is short-term, so the "
    "long-term capital-gains columns are near zero by construction rather than "
    "by accident.",
    "Costs are the live 0.20% per-side proxy, which the live config documents as "
    "covering STT and exchange charges as well as slippage. Statutory charges are "
    "not billed a second time in the tax ledger.",
    "Tax is charged against equity on 31 March of each financial year, the day the "
    "liability crystallises, rather than on the day it is actually remitted.",
)

SCREENER_NOTES = (
    "Window is capped by data, not by choice. The entry signal needs point-in-time "
    "quarterly fundamentals; the cached screener.in history reaches back only ~13 "
    "quarters, and the year-on-year screen needs a year-ago comparable on top of "
    "that. The first gradeable result is therefore the Mar-2024 quarter. Starting "
    "the run earlier only adds months of forced cash, so the window begins where "
    "the strategy can genuinely trade. Rolling_3Y and Rolling_5Y are empty as a "
    "direct consequence.",
    "Screener.in serves RESTATED figures. A company that later revised a quarter "
    "shows the revised number on the day it originally reported, which is mild "
    "lookahead bias. The NSE source (--fundamentals nse) does not have this "
    "problem.",
)

STORE_NOTES = (
    "Fundamentals come from the unified point-in-time store, which holds two "
    "sources in one table and is read as a single continuous series. Dec-2011 "
    "to Dec-2024 is AS-FILED NSE filings, parsed from the XBRL and HTML each "
    "company actually published (scraper/NSE_FUNDAMENTALS.md), so the backtest "
    "sees exactly the numbers the market saw and restatements do not leak "
    "backwards. Mar-2025 onward is screener, because NSE stops serving regular "
    "filings after ~Mar 2025 on every endpoint it exposes.",
    "That means the last ~6 quarters are RESTATED, not as-filed, and carry the "
    "mild lookahead bias that implies: a company that later revised a quarter "
    "shows the revised figure on its original reporting date. Where the two "
    "sources overlap, as-filed always wins, so the restated tail can only "
    "extend the series forward, never rewrite it.",
    "Declaration dates are NSE's real broadcast timestamps for the as-filed "
    "era and NSE's board-meeting calendar for the screener tail, not the "
    "hashed 15-45 day estimate the plain screener path falls back to. Entry "
    "timing is point-in-time accurate for ~99.8% of events.",
    "Grading is on NET PROFIT growth. As-filed EPS is quoted on the share "
    "count of the filing date, so a split reads as an earnings collapse; the "
    "adapter restates EPS onto one reference share count per symbol, which "
    "makes EPS growth identical to net-profit growth by construction and also "
    "removes any discontinuity where the two sources meet.",
    "Neither source carries a balance sheet per quarter, so the debt and ROCE "
    "quality gates read from the screener annual cache, which only reaches "
    "back to ~FY2018. Before that those two filters do not fire and the screen "
    "is looser than the live strategy.",
    "Parse coverage is not uniform. 2012-2017 recovers ~87% of filings and "
    "2019-2024 recovers 97-100%, but H2-2018 dips to 57-64% where NSE was "
    "moving from HTML attachments to XBRL. Fewer candidates in that stretch "
    "means fewer trades, not wrong ones.",
    "Results are sensitive to universe size: widening the usable universe from "
    "418 to 475 symbols moved several calendar years by 10-30pp, because the "
    "screen picks a top slice and a larger candidate pool reshuffles it. Read "
    "any single year as one draw, not as a stable estimate.",
)


def _notes_for(source: str, point_in_time: bool = False) -> tuple:
    universe = PIT_NOTES if point_in_time else BIASED_UNIVERSE_NOTES
    extra = STORE_NOTES if source == "store" else SCREENER_NOTES
    return LEAD_NOTES + universe + TAIL_NOTES + extra


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build the Excel results dossier for the live qtr_results strategy."
    )
    p.add_argument("--start", help=f"YYYY-MM-DD (default: {FIRST_TRADEABLE}, the first "
                                   "quarter the fundamentals can grade)")
    p.add_argument("--end", help="YYYY-MM-DD (default: today)")
    p.add_argument("--capital", type=float, default=500_000.0, help="Starting capital")
    p.add_argument("--universe", default="nifty500", help="Index name(s), comma-separated")
    p.add_argument("--max-symbols", type=int, default=None, help="Cap universe size")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output .xlsx path")
    p.add_argument("--no-cache", action="store_true", help="Force fresh downloads")
    p.add_argument(
        "--fundamentals", choices=FUNDAMENTALS_SOURCES, default="screener",
        help="Quarterly data source. 'store' reads the durable point-in-time "
             "store (as-filed NSE back to 2012, spliced with screener's recent "
             "tail — see scraper/NSE_FUNDAMENTALS.md); 'screener' is the "
             "~3-year live cache. 'nse' is a legacy alias for 'store'.",
    )
    p.add_argument(
        "--growth-metric", choices=("eps", "net_profit"), default=None,
        help="Line the result is graded on. Defaults to net_profit when "
             "--fundamentals=store, since as-filed EPS breaks across splits.",
    )
    p.add_argument(
        "--point-in-time", action="store_true",
        help="Remove survivorship bias: screen against reconstructed NIFTY 500 "
             "membership as it stood on each day, and price every name from the "
             "NSE tape (which keeps companies that later delisted) instead of "
             "yfinance (which does not). Requires the bhavcopy, membership and "
             "corporate-action stores.",
    )
    p.add_argument("--no-sync-benchmark", action="store_true",
                   help="Skip syncing the NIFTY 500 index into the bar store")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def _nifty500_frame(start: date, end: date, *, sync: bool):
    """The NIFTY 500 series, syncing it into the shared store on first use."""
    try:
        if sync:
            bars.sync([NIFTY500], start, end)
        return bars.read_symbol(NIFTY500, start, end)
    except Exception as exc:  # pragma: no cover - network/store failure
        logger.warning("NIFTY 500 benchmark unavailable (%s); column left blank.", exc)
        return None


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )

    end = date.fromisoformat(args.end) if args.end else date.today()
    source = normalize_fundamentals_source(args.fundamentals)
    if args.point_in_time:
        first_tradeable = FIRST_TRADEABLE_PIT
    elif source == "store":
        first_tradeable = FIRST_TRADEABLE_STORE
    else:
        first_tradeable = FIRST_TRADEABLE
    start = date.fromisoformat(args.start) if args.start else first_tradeable
    if start >= end:
        raise SystemExit("--start must be before --end")
    if start < first_tradeable:
        logger.warning(
            "Start %s precedes the first gradeable quarter (%s). The strategy will "
            "sit in cash until then, which depresses every return metric for a data "
            "reason rather than a strategy one.", start, first_tradeable,
        )

    cfg = live_mirror_config(
        starting_capital=args.capital,
        start_date=start,
        end_date=end,
        universe_index=args.universe,
        max_symbols=args.max_symbols,
        use_cache=not args.no_cache,
    )
    cfg.fundamentals_source = source
    cfg.growth_metric = args.growth_metric or (
        "net_profit" if source == "store" else "eps"
    )
    logger.info(
        "Fundamentals: %s. Grading on %s growth.",
        cfg.fundamentals_source, cfg.growth_metric,
    )

    from backtesting.swing_trading.watchlist import load_universe
    universe = load_universe(cfg)
    symbols = [u.symbol for u in universe]
    pit_gate = None
    pit_connection = None
    if args.point_in_time:
        from core.storage import connect as _connect
        from scraper.index_membership import (
            membership_intervals, resolve_index_name,
        )
        from scraper.pit_universe import PitUniverse

        pit_connection = _connect()
        pit_index = resolve_index_name(pit_connection, cfg.universe_index)
        intervals = membership_intervals(
            pit_connection, index_name=pit_index
        )
        if not intervals:
            raise SystemExit(
                "--point-in-time needs the membership store. Run: "
                "python -m scraper.index_membership --import"
            )
        # Every company that was EVER in the index, not just today's list.
        # The per-day gate below decides which of them was tradable when.
        symbols = sorted({row["symbol"] for row in intervals})
        pit_gate = PitUniverse(pit_connection)
        logger.info(
            "Point-in-time universe: %d symbols ever in '%s' (today's list "
            "has %d).", len(symbols), pit_index, len(universe),
        )
    if cfg.max_symbols:
        symbols = symbols[: cfg.max_symbols]
    logger.info("Universe '%s': %d symbols", cfg.universe_index, len(symbols))

    funds = FundamentalsStore(FUND_CACHE_DIR)
    nse_calendar = None
    if cfg.fundamentals_source == "store":
        nse_calendar = funds.load_from_nse(symbols)
    else:
        funds.load_or_download(symbols, use_cache=cfg.use_cache)
    if not funds.raw:
        raise SystemExit("No fundamentals available — aborting.")

    if args.point_in_time:
        from .pit_prices import MarketBarsPrices
        prices = MarketBarsPrices(PRICE_CACHE_DIR, pit_connection)
    else:
        prices = PointInTimeData(PRICE_CACHE_DIR)
    prices.load_or_download(
        symbols=funds.symbols(), benchmark=cfg.benchmark,
        start=start, end=end, warmup_days=cfg.warmup_days, use_cache=cfg.use_cache,
    )
    if not prices.frames:
        raise SystemExit("No price data available — aborting.")

    sectors = SectorStore(FUND_CACHE_DIR)
    sectors.load_or_download(funds.symbols(), use_cache=cfg.use_cache)

    calendar = ResultsCalendarStore(FUND_CACHE_DIR)
    if nse_calendar is not None:
        calendar.load_from_mapping(nse_calendar)
    else:
        calendar.load_or_download(funds.symbols(), use_cache=cfg.use_cache)
    have, total = calendar.coverage()
    logger.info("Real result dates resolved for %d / %d symbols.", have, total)

    pit_dividends = None
    if args.point_in_time:
        from scraper.corporate_actions import load_dividends
        pit_dividends = load_dividends(pit_connection, funds.symbols())
        logger.info(
            "Dividends: %d symbols with cash payouts credited on ex-date.",
            len(pit_dividends),
        )

    engine = BacktestEngine(
        cfg, prices, funds, sectors=sectors, calendar=calendar,
        universe=pit_gate, dividends=pit_dividends,
    )
    engine.run(start, end)

    metrics = compute_metrics(
        engine.daily_log, engine.pf.closed, cfg.starting_capital, cfg.goal_capital()
    )
    metrics = enrich_metrics(metrics, engine.daily_log, num_trials=cfg.num_trials)

    sheets = build_dossier(
        cfg, engine, prices,
        metrics=metrics,
        tax_cfg=TaxConfig(),
        nifty500=_nifty500_frame(start, end, sync=not args.no_sync_benchmark),
        notes=_notes_for(cfg.fundamentals_source, args.point_in_time),
    )
    out = write_workbook(
        args.out, sheets,
        titles={
            "Positions": "Closed round trips — one row per position",
            "Yearly_Returns": "Calendar-year returns (* marks a partial year)",
        },
    )

    print(f"\nDossier written to {out}")
    for name, frame in sheets.items():
        print(f"  {name:<26} {len(frame):>6} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
