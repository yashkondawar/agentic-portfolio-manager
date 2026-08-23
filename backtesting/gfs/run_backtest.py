"""
run_backtest.py
===============

CLI for the GFS backtest.

    python -m backtesting.gfs.run_backtest --start 2016-01-01 --end 2025-12-31
    python -m backtesting.gfs.run_backtest --ablations --monte-carlo 500
    python -m backtesting.gfs.run_backtest --universe nse_all      # bias check

Defaults deliberately run the *challenged* version (forward-return study on,
buy-and-hold comparison on). Add ``--ablations`` before you believe anything.
"""

import argparse
import logging
import sys
from datetime import date, datetime

from .config import (
    EXIT_RESISTANCE,
    EXIT_RSI,
    EXIT_SCALE_OUT,
    EXIT_TRAIL,
    GFSConfig,
    HTF_CLOSED,
    HTF_LIVE,
    RANK_COMPOSITE,
    RANK_DIP_DEPTH,
    RANK_HTF_STRENGTH,
    RANK_RANDOM,
    RANK_SECTOR_RS,
    SIZING_EQUAL,
    SIZING_RISK,
    STOP_ATR,
    STOP_PCT,
    STOP_SWING,
    TRIGGER_DIP,
    TRIGGER_RECROSS,
)
from .service import run_study


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gfs-backtest",
        description="Backtest the Grandfather/Father/Son multi-timeframe RSI strategy.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    win = p.add_argument_group("window and universe")
    win.add_argument("--start", type=_parse_date, default=_parse_date("2016-01-01"))
    win.add_argument("--end", type=_parse_date, default=date.today())
    win.add_argument(
        "--warmup-days",
        type=int,
        default=2600,
        help="Extra history before --start. Monthly RSI needs years, not months.",
    )
    win.add_argument(
        "--universe",
        default="nifty500",
        help="NSE index key(s), comma-separated, or 'nse_all' for the full "
        "listed universe (removes index-inclusion bias).",
    )
    win.add_argument("--universe-file", default=None)
    win.add_argument("--benchmark", default="^NSEI")
    win.add_argument("--symbols", default=None, help="Comma-separated override.")
    win.add_argument("--no-cache", action="store_true")

    core = p.add_argument_group("the GFS rule")
    core.add_argument("--htf-mode", choices=[HTF_CLOSED, HTF_LIVE], default=HTF_CLOSED)
    core.add_argument("--g-rsi", type=float, default=60.0, help="Monthly RSI floor.")
    core.add_argument("--f-rsi", type=float, default=60.0, help="Weekly RSI floor.")
    core.add_argument("--s-rsi", type=float, default=40.0, help="Daily RSI dip level.")
    core.add_argument("--rsi-period", type=int, default=14)
    core.add_argument(
        "--trigger", choices=[TRIGGER_DIP, TRIGGER_RECROSS], default=TRIGGER_DIP
    )

    gate = p.add_argument_group("top-down gates")
    gate.add_argument("--no-regime-filter", action="store_true")
    gate.add_argument("--regime-sma", type=int, default=200)
    gate.add_argument("--min-breadth", type=float, default=0.0)
    gate.add_argument("--no-sector-filter", action="store_true")
    gate.add_argument("--sector-top-n", type=int, default=5)
    gate.add_argument("--sector-lookback", type=int, default=63)

    risk = p.add_argument_group("risk and sizing")
    risk.add_argument("--capital", type=float, default=500_000.0)
    risk.add_argument("--sizing", choices=[SIZING_EQUAL, SIZING_RISK], default=SIZING_EQUAL)
    risk.add_argument("--risk-per-trade", type=float, default=2.0)
    risk.add_argument("--max-positions", type=int, default=8)
    risk.add_argument("--max-position-pct", type=float, default=15.0)
    risk.add_argument("--max-per-sector", type=int, default=2)
    risk.add_argument("--stop-mode", choices=[STOP_ATR, STOP_PCT, STOP_SWING], default=STOP_ATR)
    risk.add_argument("--atr-mult", type=float, default=2.0)
    risk.add_argument("--stop-pct", type=float, default=4.0)
    risk.add_argument("--breakeven-at-r", type=float, default=0.0)

    ex = p.add_argument_group("exits")
    ex.add_argument(
        "--exit-mode",
        choices=[EXIT_RSI, EXIT_SCALE_OUT, EXIT_TRAIL, EXIT_RESISTANCE],
        default=EXIT_RSI,
    )
    ex.add_argument("--exit-rsi", type=float, default=65.0)
    ex.add_argument("--trail-atr-mult", type=float, default=3.0)
    ex.add_argument("--max-holding-days", type=int, default=60)
    ex.add_argument(
        "--instant-indicator-exits",
        action="store_true",
        help="Fill RSI exits at the close that generated them (optimistic; for "
        "measuring the cost of the assumption only).",
    )

    rank = p.add_argument_group("ranking and costs")
    rank.add_argument(
        "--rank-by",
        choices=[RANK_COMPOSITE, RANK_SECTOR_RS, RANK_DIP_DEPTH, RANK_HTF_STRENGTH, RANK_RANDOM],
        default=RANK_COMPOSITE,
    )
    rank.add_argument("--commission-pct", type=float, default=0.05)
    rank.add_argument("--slippage-bps", type=float, default=15.0)
    rank.add_argument("--seed", type=int, default=7)

    val = p.add_argument_group("validation")
    val.add_argument(
        "--ablations",
        action="store_true",
        help="Run every single-change variant. Slower, and the only way to know "
        "which part of the strategy is real.",
    )
    val.add_argument(
        "--monte-carlo",
        type=int,
        default=0,
        metavar="N",
        help="Random-entry null with N simulated runs (500 is plenty).",
    )
    val.add_argument(
        "--sweep",
        action="store_true",
        help="Walk-forward parameter sweep: tune on each training fold, report "
        "only the untouched test folds, and deflate the Sharpe by the number "
        "of configurations tried. Expensive, and the only honest way to pick "
        "thresholds.",
    )
    val.add_argument("--train-months", type=int, default=36)
    val.add_argument("--test-months", type=int, default=12)
    val.add_argument(
        "--stability",
        metavar="PARAM",
        help="Response curve for one parameter (e.g. g_rsi_min). A broad "
        "plateau suggests a real effect; a lone spike suggests a fitted one.",
    )
    val.add_argument("--label", default="gfs")
    val.add_argument("--no-artifacts", action="store_true")
    val.add_argument("--verbose", action="store_true")
    return p


def config_from_args(args) -> GFSConfig:
    return GFSConfig(
        start_date=args.start,
        end_date=args.end,
        warmup_days=args.warmup_days,
        universe_index=args.universe,
        universe_file=args.universe_file,
        benchmark=args.benchmark,
        use_cache=not args.no_cache,
        htf_mode=args.htf_mode,
        rsi_period_monthly=args.rsi_period,
        rsi_period_weekly=args.rsi_period,
        rsi_period_daily=args.rsi_period,
        g_rsi_min=args.g_rsi,
        f_rsi_min=args.f_rsi,
        s_rsi_entry=args.s_rsi,
        entry_trigger=args.trigger,
        use_regime_filter=not args.no_regime_filter,
        regime_sma=args.regime_sma,
        min_breadth_pct=args.min_breadth,
        use_sector_filter=not args.no_sector_filter,
        sector_top_n=args.sector_top_n,
        sector_rs_lookback=args.sector_lookback,
        rank_by=args.rank_by,
        max_per_sector=args.max_per_sector,
        starting_capital=args.capital,
        sizing_mode=args.sizing,
        risk_per_trade_pct=args.risk_per_trade,
        max_positions=args.max_positions,
        max_position_pct=args.max_position_pct,
        stop_mode=args.stop_mode,
        atr_stop_mult=args.atr_mult,
        fixed_stop_pct=args.stop_pct,
        move_stop_to_breakeven_at_r=args.breakeven_at_r,
        exit_mode=args.exit_mode,
        exit_rsi=args.exit_rsi,
        trail_atr_mult=args.trail_atr_mult,
        max_holding_days=args.max_holding_days,
        indicator_exit_delay=not args.instant_indicator_exits,
        commission_pct=args.commission_pct,
        slippage_bps=args.slippage_bps,
        seed=args.seed,
        label=args.label,
    )


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
    symbols = (
        [s.strip() for s in args.symbols.split(",") if s.strip()] if args.symbols else None
    )

    try:
        result = run_study(
            cfg,
            symbols=symbols,
            ablations=args.ablations,
            monte_carlo_runs=args.monte_carlo,
            sweep=args.sweep,
            train_months=args.train_months,
            test_months=args.test_months,
            stability_param=args.stability,
            write_outputs=not args.no_artifacts,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        logging.getLogger("gfs").error("Backtest failed: %s", exc, exc_info=args.verbose)
        return 1

    print()
    print(result["summary"])
    if result["artifacts"]:
        print("\nArtifacts:")
        for name, ref in result["artifacts"].items():
            print(f"  {name:<22} {ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
