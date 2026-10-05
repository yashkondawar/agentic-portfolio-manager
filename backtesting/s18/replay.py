"""Independent golden replay of all 30 S18 tranche configurations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from .book import Book, TRADE_COLUMNS
from .calendar import review_flags
from .config import COMBOS, RF_DAILY, S18Config
from .dataset import AssetReader, FolderSource, get_dataset


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    digest.update(
        f"{sys.version_info[:3]}|numpy={np.__version__}|pandas={pd.__version__}".encode()
    )
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_text(encoding="utf-8").encode("utf-8"))
    return digest.hexdigest()


def book_fingerprint() -> str:
    """Persisted books may survive collector-only changes after a new replay."""
    digest = hashlib.sha256()
    for name in (
        "book.py",
        "config.py",
        "calendar.py",
        "signals.py",
        "data.py",
        "service.py",
    ):
        digest.update(name.encode())
        digest.update(
            (Path(__file__).parent / name).read_text(encoding="utf-8").encode("utf-8")
        )
    return digest.hexdigest()


def reference_fingerprint(source: AssetReader | None = None) -> str:
    return (source or get_dataset()).fingerprint(reference=True)


def input_fingerprint(source: AssetReader | None = None) -> str:
    return (source or get_dataset()).fingerprint()


def simulate(
    market,
    config: S18Config,
    *,
    start="2014-01-01",
    end="2026-08-31",
    capital_per_tranche=1.0,
):
    start_date, end_date = np.datetime64(start, "D"), np.datetime64(end, "D")
    if start_date > end_date:
        raise ValueError("Backtest start must be on or before end")
    first = int(np.searchsorted(market.dates, start_date, side="left")) - 1
    last = int(np.searchsorted(market.dates, end_date, side="right")) - 1
    if first < 0 or first >= len(market.dates) - 1 or last <= first:
        raise ValueError(
            "Backtest requires a preceding signal session and price coverage"
        )
    if end_date > market.dates[-1]:
        raise ValueError(f"Data ends {market.dates[-1]}; cannot backtest through {end}")
    order = market.s1_order(config.tiered, config.metal_mode == "both_priority")
    books = []
    for tranche in ("A", "B"):
        reviews = review_flags(market.dates, tranche, reference=True)
        book = Book.from_cash(config, tranche, capital_per_tranche)
        for row in range(first, last + 1):
            book.step(
                market,
                row,
                review=bool(reviews[row]) or row == first,
                order=order[row],
                initial=row == first,
                decisions=row < last,
            )
        books.append(book)
    return books


def combined_curve(books, market):
    if [x["date"] for x in books[0].equity] != [x["date"] for x in books[1].equity]:
        raise ValueError("S18 tranche equity dates do not align")
    rows = []
    for a, b in zip(books[0].equity, books[1].equity):
        idx = int(np.searchsorted(market.dates, np.datetime64(a["date"])))
        rows.append(
            {
                "date": a["date"],
                "nav": a["nav"] + b["nav"],
                "tranche_a": a["nav"],
                "tranche_b": b["nav"],
                "cash": a["cash"] + b["cash"],
                "positions": a["positions"] + b["positions"],
                "s2_value": a["s2_value"] + b["s2_value"],
                "benchmark": float(market.benchmark[idx]),
                "risk_off": bool(market.risk_off[idx]),
            }
        )
    return rows


def metrics(curve) -> dict:
    frame = pd.DataFrame(curve)
    nav = frame["nav"].to_numpy(dtype=float)
    index = frame["benchmark"].to_numpy(dtype=float)
    if not np.all(np.isfinite(nav)) or np.any(nav <= 0):
        raise ValueError("Cannot calculate S18 metrics for nonpositive/nonfinite NAV")
    r = nav[1:] / nav[:-1] - 1
    rm = index[1:] / index[:-1] - 1
    days = (pd.Timestamp(frame.date.iloc[-1]) - pd.Timestamp(frame.date.iloc[0])).days
    vol = float(np.std(r)) if len(r) else 0.0
    market_var = float(np.var(rm)) if len(rm) else 0.0
    return {
        "start_date": frame.date.iloc[0],
        "end_date": frame.date.iloc[-1],
        "starting_capital": float(nav[0]),
        "final_value": float(nav[-1]),
        "cagr": float((nav[-1] / nav[0]) ** (365.25 / days) - 1) if days else None,
        "sharpe": float((r.mean() - RF_DAILY) / vol * np.sqrt(252)) if vol else None,
        "max_drawdown": float(np.min(nav / np.maximum.accumulate(nav) - 1)),
        "volatility": vol * np.sqrt(252),
        "beta": (
            float(np.mean((r - r.mean()) * (rm - rm.mean())) / market_var)
            if market_var
            else None
        ),
        "average_cash_fraction": float(np.mean(frame.cash / nav)),
        "cost_per_side": 0.0002,
    }


def trade_frame(books, market):
    return pd.DataFrame(
        [r for book in books for r in [*book.trades, *book.open_trades(market)]],
        columns=TRADE_COLUMNS,
    )


def compare_trades(actual: pd.DataFrame, expected: pd.DataFrame, label: str):
    if list(expected.columns) != TRADE_COLUMNS:
        raise ValueError(f"{label}: reference trade schema differs from S18 contract")
    if len(actual) != len(expected):
        raise ValueError(f"{label}: expected {len(expected)} trades, got {len(actual)}")
    numeric = {"entry_px", "exit_px", "cost_basis", "gain", "ret_pct"}
    for col in TRADE_COLUMNS:
        if col in numeric:
            left = actual[col].to_numpy(dtype=float)
            right = expected[col].to_numpy(dtype=float)
            # Supplied reference CSVs use %.6g (six significant digits).
            same = (
                np.isfinite(left)
                & np.isfinite(right)
                & np.isclose(left, right, rtol=5.1e-6, atol=1e-12)
            )
        else:
            same = (
                actual[col].fillna("").astype(str).to_numpy()
                == expected[col].fillna("").astype(str).to_numpy()
            )
        if not np.all(same):
            row = int(np.flatnonzero(~same)[0])
            raise ValueError(
                f"{label}: row {row + 1} {col}: expected "
                f"{expected.iloc[row][col]!r}, got {actual.iloc[row][col]!r}"
            )


def validate_kit(kit_path: Path):
    """One-time import/test validation, not the normal product entry point."""
    return validate_dataset(FolderSource(kit_path))


def validate_dataset(source: AssetReader | None = None):
    from .data import load_market

    source = source or get_dataset()
    reference_hash = reference_fingerprint(source)
    data_hash = input_fingerprint(source)
    source_hash = source_fingerprint()
    folder = "output/analysis/s18"
    expected_metrics = source.parquet(f"{folder}/s18_combos.parquet")
    expected_nav = source.array(f"{folder}/s18_nav.npy")
    nav_index = source.csv(f"{folder}/s18_nav_index.csv")
    if len(nav_index) != 15 or len(expected_metrics) != 15:
        raise ValueError("S18 reference must have exactly 15 combo/metal results")
    results, artifacts = [], {}
    for metals in (False, True):
        market = load_market(source=source, metals=metals, recompute=True)
        if (
            str(market.dates[0]) != "2013-12-31"
            or str(market.dates[-1]) != "2026-08-31"
        ):
            raise ValueError("Golden replay requires 2013-12-31 through 2026-08-31")
        if expected_nav.shape != (15, len(market.dates)):
            raise ValueError("S18 reference NAV shape does not match the panel")
        if market.risk_off[-1]:
            raise ValueError("S18 reference endpoint 2026-08-31 must be SMA100 risk-on")
        for combo in COMBOS:
            for mode in ("both", "both_priority") if metals else ("none",):
                config = S18Config(combo, mode)
                books = simulate(market, config)
                frame = trade_frame(books, market)
                tag = f"{combo}_{mode}"
                expected = source.csv(
                    f"S18_reference/{tag}_trades.csv",
                    keep_default_na=False,
                )
                compare_trades(frame, expected, f"{tag} trades")
                opened = frame[frame.reason == "open at end"].reset_index(drop=True)
                expected_open = source.csv(
                    f"S18_reference/{tag}_open_book_2026-08-31.csv",
                    keep_default_na=False,
                )
                compare_trades(opened, expected_open, f"{tag} open book")
                curve = combined_curve(books, market)
                actual_nav = np.array([r["nav"] / 2 for r in curve])
                matches = nav_index.index[
                    (nav_index.id == combo)
                    & (nav_index["mode"] == mode.replace("_", " "))
                ]
                if len(matches) != 1:
                    raise ValueError(f"{tag}: missing or duplicate reference NAV")
                target_nav = expected_nav[int(matches[0])]
                if not np.allclose(actual_nav, target_nav, rtol=1e-9, atol=1e-11):
                    worst = int(np.argmax(np.abs(actual_nav - target_nav)))
                    raise ValueError(
                        f"{tag}: NAV mismatch on {market.dates[worst]}: "
                        f"{actual_nav[worst]} vs {target_nav[worst]}"
                    )
                measured = metrics(curve)
                match = expected_metrics[
                    (expected_metrics.id == combo)
                    & (expected_metrics["mode"] == mode.replace("_", " "))
                ]
                if len(match) != 1:
                    raise ValueError(f"{tag}: missing or duplicate reference Sharpe")
                target_sharpe = float(match.iloc[0].Sharpe)
                delta = abs(measured["sharpe"] - target_sharpe)
                if delta >= 0.001:
                    raise ValueError(f"{tag}: Sharpe differs by {delta:.6f}")
                results.append(
                    {
                        "combo": combo,
                        "metal_mode": mode,
                        "tranches": 2,
                        "status": "passed",
                        "trades": len(frame),
                        "open_positions": len(opened),
                        "sharpe": measured["sharpe"],
                        "reference_sharpe": target_sharpe,
                        "sharpe_delta": delta,
                        "max_nav_error": float(np.max(np.abs(actual_nav - target_nav))),
                    }
                )
                artifacts[f"{tag}_trades.csv"] = frame.to_csv(
                    index=False, float_format="%.6g"
                )
                artifacts[f"{tag}_open_book_2026-08-31.csv"] = opened.to_csv(
                    index=False, float_format="%.6g"
                )
    if source_hash != source_fingerprint() or reference_hash != reference_fingerprint(
        source
    ):
        raise ValueError("S18 code/reference changed during replay; rerun validation")
    if data_hash != input_fingerprint(source):
        raise ValueError("S18 input data changed during replay; rerun validation")
    return {
        "status": "passed",
        "source_hash": source_hash,
        "data_hash": data_hash,
        "reference_hash": reference_hash,
        "results": results,
        "start": "2014-01-01",
        "end": "2026-08-31",
        "tranches_checked": 30,
        "reference_files_checked": 30,
    }, artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    from .service import run_replay

    result = run_replay()
    print(json.dumps(result["validation"], indent=2))


if __name__ == "__main__":
    main()
