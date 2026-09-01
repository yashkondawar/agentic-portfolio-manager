"""
run_dossier.py
==============

Builds the GFS results workbook.

    python -m backtesting.gfs.run_dossier --start 2012-10-19 --capital 10000000
    python -m backtesting.gfs.run_dossier --out reports/gfs_dossier.xlsx
    python -m backtesting.gfs.run_dossier --universe nse_all      # bias check

**The defaults are the live strategy's own settings**, imported from
``gfs.config.LIVE_DEFAULTS`` rather than restated here. A dossier is only useful
if it describes the thing actually being traded, and a second copy of the
parameters is a second thing to forget to update. Overrides exist for the
handful of knobs a report legitimately varies - window, capital, universe - and
for everything else the answer is "change the live config".

Three backtests run, sharing one indicator pass:

* **before cost & tax** - zero commission, zero slippage, no tax
* **before tax**        - real execution costs, no tax
* **net of cost + tax** - real execution costs, capital-gains tax debited from
  cash each April

The third is the headline. The first two exist to show how much of the gap
between gross and net is friction rather than strategy.
"""

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from gfs.config import LIVE_DEFAULTS, PINNED, WARMUP_DAYS

from .config import GFSConfig
from .dossier import build_dossier
from .service import prepare_data
from .taxes import TaxConfig


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gfs-dossier",
        description=(
            "Build the GFS results workbook. Defaults mirror the live strategy "
            "configuration exactly."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--start", type=_parse_date, default=_parse_date("2016-01-01"))
    p.add_argument(
        "--end",
        type=_parse_date,
        default=date.today(),
        help="Inclusive last session. Defaults to today.",
    )
    p.add_argument(
        "--capital",
        type=float,
        default=10_000_000.0,
        help="Starting capital. The default matches the reference dossier "
        "(Rs 1 crore) so the two are directly comparable.",
    )
    p.add_argument(
        "--universe",
        default=LIVE_DEFAULTS["universe_index"],
        help="nifty500 (as traded) or nse_all (to size index-inclusion bias).",
    )
    p.add_argument("--benchmark", default=LIVE_DEFAULTS["benchmark"])
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output .xlsx path. Defaults to reports/gfs_dossier_<end>.xlsx.",
    )
    p.add_argument("--title", default=None, help="Override the Summary title line.")
    p.add_argument(
        "--no-tax",
        action="store_true",
        help="Skip capital-gains modelling. The net column then equals the "
        "before-tax column; useful only for a like-for-like against an "
        "existing pre-tax study.",
    )
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p


def config_from_args(args) -> GFSConfig:
    """The live configuration, with only the reporting window and size varied."""
    get = LIVE_DEFAULTS.get
    cfg = GFSConfig(
        start_date=args.start,
        end_date=args.end,
        warmup_days=WARMUP_DAYS,
        universe_index=args.universe,
        benchmark=args.benchmark,
        use_cache=not args.no_cache,
        g_rsi_min=float(get("g_rsi_min")),
        f_rsi_min=float(get("f_rsi_min")),
        s_rsi_entry=float(get("s_rsi_entry")),
        min_headroom_pct=float(get("min_headroom_pct")),
        exit_rsi=float(get("exit_rsi")),
        atr_stop_mult=float(get("atr_stop_mult")),
        regime_mode=str(get("regime_mode")),
        min_breadth_pct=float(get("min_breadth_pct")),
        sector_top_n=int(get("sector_top_n")),
        max_per_sector=int(get("max_per_sector")),
        max_positions=int(get("max_positions")),
        max_position_pct=float(get("max_position_pct")),
        starting_capital=args.capital,
        cash_yield_pct=float(get("cash_yield_pct")),
        commission_pct=float(get("commission_pct")),
        slippage_bps=float(get("slippage_bps")),
        label="gfs_dossier",
    )
    for field, value in PINNED.items():
        setattr(cfg, field, value)
    cfg.validate()
    return cfg


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = config_from_args(args)
    out = args.out or Path("reports") / f"gfs_dossier_{args.end.isoformat()}.xlsx"

    tax_cfg = TaxConfig(apply_capital_gains=not args.no_tax)
    if args.no_tax:
        tax_cfg = None

    try:
        prepared = prepare_data(cfg)
        path = build_dossier(cfg, prepared, out, tax_cfg=tax_cfg, title=args.title)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        logging.getLogger("gfs.dossier").error("%s", exc, exc_info=args.verbose)
        return 1

    print(f"\nDossier written to {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
