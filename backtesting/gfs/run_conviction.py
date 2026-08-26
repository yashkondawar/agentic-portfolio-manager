"""
run_conviction.py
=================

CLI for the GFS conviction study.

    python -m backtesting.gfs.run_conviction --start 2018-01-01 --end 2026-08-21

What it does, in order:

1. Builds a portfolio-free table of every GFS signal with features known at
   signal time and the realised outcome under the engine's own fill and exit
   rules, with no time stop.
2. Splits it chronologically, ranks features on the TRAIN half only, then
   reports those same rules on the TEST half. The number of comparisons made is
   printed, because the best of a hundred looks is impressive by chance alone.
3. Sweeps stop width against exit threshold, so the win-rate/expectancy
   trade-off is explicit.

Nothing here changes the strategy. It produces evidence for or against a filter;
applying one is a separate, deliberate step.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from . import conviction as cv
from .config import GFSConfig
from .service import prepare_data

logger = logging.getLogger("gfs.run_conviction")


def _parse_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gfs-conviction",
        description="Find which GFS signals are worth taking.",
    )
    p.add_argument("--start", type=_parse_date, required=True)
    p.add_argument("--end", type=_parse_date, required=True)
    p.add_argument("--universe", default="nifty500")
    p.add_argument("--g-rsi-min", type=float, default=60.0)
    p.add_argument("--f-rsi-min", type=float, default=60.0)
    p.add_argument("--s-rsi-entry", type=float, default=40.0)
    p.add_argument("--exit-rsi", type=float, default=65.0)
    p.add_argument("--atr-stop-mult", type=float, default=2.0)
    p.add_argument("--train-frac", type=float, default=0.6)
    p.add_argument("--no-gates", action="store_true",
                   help="Include signals the regime/sector gates would reject.")
    p.add_argument("--grid", action="store_true",
                   help="Also sweep stop width x exit RSI (slow).")
    p.add_argument("--min-headroom", type=float, default=None,
                   help="Apply a headroom filter inside the stop/exit grid.")
    p.add_argument("--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)

    cfg = GFSConfig(
        start_date=args.start,
        end_date=args.end,
        universe_index=args.universe,
        g_rsi_min=args.g_rsi_min,
        f_rsi_min=args.f_rsi_min,
        s_rsi_entry=args.s_rsi_entry,
        exit_rsi=args.exit_rsi,
        atr_stop_mult=args.atr_stop_mult,
        max_holding_days=0,  # the user's requirement: no time-based exit
    )
    cfg.validate()

    prepared = prepare_data(cfg)
    panels, calendar, sector_panel, regime_panel, qualify = prepared.panels_for(cfg)

    table = cv.build_signal_table(
        panels, qualify, sector_panel, regime_panel, cfg,
        respect_gates=not args.no_gates,
    )
    if table.empty:
        print("No signals found.")
        return 1

    _print_overall(table, cfg)
    _print_exit_mix(table)
    train, test = cv.split_by_date(table, args.train_frac)
    _print_feature_search(train, test)
    _print_threshold_scans(train, test)
    _print_pair_search(train, test)
    if args.grid:
        _print_grid(panels, qualify, sector_panel, regime_panel, cfg, args.min_headroom)
    return 0


def _rule(header: str) -> None:
    print()
    print("=" * 78)
    print(f" {header}")
    print("=" * 78)


def _fmt(stats: dict) -> str:
    return (
        f"n={stats['n']:>5}  win={stats['win_rate']:5.1f}%  "
        f"ExpR={stats['exp_r']:+.3f}  PF={stats['profit_factor']:.2f}  "
        f"avgWin={stats['avg_win_r']:+.2f}R  avgLoss={stats['avg_loss_r']:+.2f}R  "
        f"days={stats['avg_days']:.0f}"
    )


def _print_overall(table: pd.DataFrame, cfg: GFSConfig) -> None:
    _rule("ALL GFS SIGNALS - portfolio-free, no time stop")
    print(f" G>={cfg.g_rsi_min:.0f}  F>={cfg.f_rsi_min:.0f}  S<={cfg.s_rsi_entry:.0f}  "
          f"exit RSI {cfg.exit_rsi:.0f} or resistance  stop {cfg.atr_stop_mult}xATR")
    print()
    print(" " + _fmt(cv.evaluate(table)))
    still_open = int(table["open_at_horizon"].sum())
    if still_open:
        print(f" ({still_open} trades never resolved within 2 years and are excluded)")


def _print_exit_mix(table: pd.DataFrame) -> None:
    _rule("HOW TRADES ACTUALLY END")
    closed = table[~table["open_at_horizon"]]
    total = len(closed)
    print(f"{'reason':<18}{'n':>7}{'share':>9}{'win%':>8}{'ExpR':>9}{'avg R':>9}")
    for reason, group in closed.groupby("reason"):
        stats = cv.evaluate(group)
        print(f"{reason:<18}{stats['n']:>7}{stats['n']/total*100:>8.1f}%"
              f"{stats['win_rate']:>7.1f}%{stats['exp_r']:>9.3f}"
              f"{group['r_multiple'].mean():>9.3f}")


def _print_feature_search(train: pd.DataFrame, test: pd.DataFrame) -> None:
    _rule("FEATURE SEARCH - ranked on TRAIN, reported on TEST")
    print(f" train: {len(train):,} signals  "
          f"{train['signal_date'].min():%Y-%m-%d} -> {train['signal_date'].max():%Y-%m-%d}")
    print(f" test : {len(test):,} signals  "
          f"{test['signal_date'].min():%Y-%m-%d} -> {test['signal_date'].max():%Y-%m-%d}")

    ranked = cv.rank_features(train, cv.FEATURE_COLUMNS)
    if ranked.empty:
        print(" No feature had enough data to rank.")
        return

    n_trials = len(ranked) * 5
    print(f"\n {len(ranked)} features x 5 buckets = {n_trials} implicit comparisons.")
    print(" Treat any single result below as needing to clear that bar.\n")

    base_train = cv.evaluate(train)
    base_test = cv.evaluate(test)
    print(f" BASELINE  train {base_train['win_rate']:.1f}% win / "
          f"{base_train['exp_r']:+.3f} ExpR   |   "
          f"test {base_test['win_rate']:.1f}% win / {base_test['exp_r']:+.3f} ExpR")
    print()

    header = (f"{'feature':<20}{'best bucket':<20}{'train win':>10}{'train ExpR':>12}"
              f"{'test win':>10}{'test ExpR':>12}{'test n':>8}  mono")
    print(header)
    print("-" * len(header))

    for _, row in ranked.head(12).iterrows():
        feat, lo, hi = row["feature"], row["best_lo"], row["best_hi"]
        sel = test[(test[feat] >= lo) & (test[feat] <= hi)]
        t = cv.evaluate(sel)
        rng = f"[{lo:.2f}, {hi:.2f}]"
        print(f"{feat:<20}{rng:<20}{row['best_win']:>9.1f}%{row['best_exp_r']:>12.3f}"
              f"{t['win_rate']:>9.1f}%{t['exp_r']:>12.3f}{t['n']:>8}"
              f"  {'yes' if row['monotonic'] else 'no'}")

    print("\n A feature is only interesting if the TEST columns hold up AND the")
    print(" response is monotonic. A high train win rate with a flat test column")
    print(" is the signature of a lucky bucket, not an edge.")


def _print_threshold_scans(train: pd.DataFrame, test: pd.DataFrame) -> None:
    _rule("ROUND-NUMBER CUTOFFS - the only kind you can actually trade")
    print(" Quintile edges are fitted to the sample. A plain threshold that works")
    print(" on both halves is a far stronger claim, and it is what goes in a config.\n")
    scans = [
        ("headroom_pct", [0, 5, 10, 15, 20, 25, 30, 40], "ge"),
        ("dist_52w_high_pct", [-5, -10, -15, -20, -25, -30], "le"),
        ("reward_risk", [0.5, 1.0, 1.5, 2.0, 2.5, 3.0], "ge"),
        ("rsi_w", [60, 65, 70, 75], "ge"),
        ("rsi_m", [60, 65, 70, 75], "ge"),
    ]
    for feature, thresholds, direction in scans:
        frame = cv.threshold_scan(train, test, feature, thresholds, direction=direction)
        arrow = ">=" if direction == "ge" else "<="
        print(f" {feature} {arrow} X")
        header = (f"{'X':>8}{'train n':>9}{'train win':>11}{'train ExpR':>12}"
                  f"{'test n':>9}{'test win':>11}{'test ExpR':>12}{'test PF':>9}")
        print(header)
        print(" " + "-" * (len(header) - 1))
        for _, r in frame.iterrows():
            print(f"{r['threshold']:>8.1f}{r['train_n']:>9.0f}{r['train_win']:>10.1f}%"
                  f"{r['train_exp_r']:>12.3f}{r['test_n']:>9.0f}{r['test_win']:>10.1f}%"
                  f"{r['test_exp_r']:>12.3f}{r['test_pf']:>9.2f}")
        print()


def _print_pair_search(train: pd.DataFrame, test: pd.DataFrame) -> None:
    _rule("TWO-FEATURE RULES - chosen on TRAIN, scored on TEST")
    pairs = cv.search_pairs(train, test, cv.FEATURE_COLUMNS)
    if pairs.empty:
        print(" No two-feature rule kept enough trades on both halves.")
        return
    print(f" {pairs.attrs.get('n_trials', 0):,} conjunctions were tried. The best of that many")
    print(" looks impressive by chance alone, so only the TEST columns count.\n")
    header = (f"{'rule':<52}{'train n':>8}{'train win':>10}"
              f"{'test n':>8}{'test win':>10}{'test ExpR':>11}")
    print(header)
    print("-" * len(header))
    for _, r in pairs.iterrows():
        label = (f"{r['feat_a']}[{r['lo_a']:.1f},{r['hi_a']:.1f}] & "
                 f"{r['feat_b']}[{r['lo_b']:.1f},{r['hi_b']:.1f}]")
        print(f"{label[:51]:<52}{r['train_n']:>8.0f}{r['train_win']:>9.1f}%"
              f"{r['test_n']:>8.0f}{r['test_win']:>9.1f}%{r['test_exp_r']:>11.3f}")

    best = pairs.iloc[0]
    rule = {best["feat_a"]: (best["lo_a"], best["hi_a"]),
            best["feat_b"]: (best["lo_b"], best["hi_b"])}
    sel = test[cv.rule_mask(test, rule)]
    lo, hi = cv.bootstrap_win_rate(sel)
    _rule("BEST TRAIN RULE, HELD TO ACCOUNT ON TEST")
    print(f" rule: {best['feat_a']} in [{best['lo_a']:.2f}, {best['hi_a']:.2f}] AND "
          f"{best['feat_b']} in [{best['lo_b']:.2f}, {best['hi_b']:.2f}]")
    print(f" test: {_fmt(cv.evaluate(sel))}")
    if np.isfinite(lo):
        print(f" 95% CI on test win rate (resampled by date): {lo:.1f}% - {hi:.1f}%")
        print(" If that interval spans the unfiltered baseline, the rule has not")
        print(" demonstrated anything.")
    breakdown = cv.yearly_breakdown(sel)
    if not breakdown.empty:
        print("\n Per year on test:")
        print(breakdown[["n", "win_rate", "exp_r"]].round(2).to_string())


def _print_grid(panels, qualify, sector_panel, regime_panel, cfg, min_headroom=None) -> None:
    _rule("STOP WIDTH x EXIT THRESHOLD - the win-rate / expectancy trade-off")
    if min_headroom is not None:
        print(f" (restricted to signals with headroom_pct >= {min_headroom:g})")
    grid = cv.stop_target_grid(
        panels, qualify, sector_panel, regime_panel, cfg,
        min_headroom_pct=min_headroom,
    )
    pivot_win = grid.pivot(index="atr_stop_mult", columns="exit_rsi", values="win_rate")
    pivot_exp = grid.pivot(index="atr_stop_mult", columns="exit_rsi", values="exp_r")
    print("\n WIN RATE (%)")
    print(pivot_win.round(1).to_string())
    print("\n EXPECTANCY (R)")
    print(pivot_exp.round(3).to_string())
    print("\n Read them together. Win rate rises to the bottom-left (wide stop,")
    print(" early exit) while expectancy usually does not - that is the trade-off.")


if __name__ == "__main__":
    raise SystemExit(main())
