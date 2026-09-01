"""Command line entry point for the ATH breakout sleeve.

python -m backtesting.breakout_ath.run_backtest --download
python -m backtesting.breakout_ath.run_backtest --daily
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from .config import AthBreakoutConfig
from .daily import run_daily
from .service import run_backtest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ATH breakout sleeve")
    p.add_argument(
        "--daily",
        action="store_true",
        help="run the daily workflow instead of the backtest",
    )
    p.add_argument(
        "--download", action="store_true", help="refresh prices from yfinance first"
    )
    p.add_argument("--start", type=date.fromisoformat, default=None)
    p.add_argument("--end", type=date.fromisoformat, default=None)
    p.add_argument("--capital", type=float, default=None)
    p.add_argument("--max-positions", type=int, default=None)
    p.add_argument("--sl-pct", type=float, default=None)
    p.add_argument("--ath-band", type=float, default=None)
    p.add_argument("--results-dir", type=Path, default=None)
    p.add_argument("--no-dossier", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = AthBreakoutConfig()
    for attr, value in (
        ("start_date", args.start),
        ("end_date", args.end),
        ("start_capital", args.capital),
        ("max_positions", args.max_positions),
        ("sl_pct", args.sl_pct),
        ("ath_band", args.ath_band),
    ):
        if value is not None:
            setattr(cfg, attr, value)
    cfg.validate()

    if args.daily:
        out = run_daily(cfg, download=args.download)
        print(out["report"])
        return 0

    result = run_backtest(
        cfg,
        download=args.download,
        write_dossier=not args.no_dossier,
        results_dir=args.results_dir,
    )
    m = result["metrics"]
    print(
        f"ATH breakout {m['start_date']} to {m['end_date']}  ({m['sessions']} sessions)"
    )
    print(
        f"  final value     {m['final_value']:>18,.0f}  (from {m['starting_capital']:,.0f})"
    )
    print(f"  CAGR            {m['cagr']:>18.2%}")
    print(f"  max drawdown    {m['max_drawdown']:>18.2%}")
    print(f"  sharpe          {m['sharpe']:>18.2f}")
    print(f"  round trips     {m['round_trips']:>18,}  win rate {m['win_rate']:.1%}")
    print(f"  mean positions  {m['mean_positions_open']:>18.2f}")
    print(f"  artefacts       {result['results_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
