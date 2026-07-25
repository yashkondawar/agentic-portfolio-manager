"""Programmatic service for the 52-week breakout backtest."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from uuid import uuid4

from backtesting.swing_trading.data import PointInTimeData
from backtesting.swing_trading.metrics import compute_metrics, render_summary
from backtesting.swing_trading.watchlist import UniverseStock, load_universe

from .calendar import EarningsCalendar
from .config import DATA_CACHE_DIR, RESULTS_DIR, BreakoutConfig
from .engine import BreakoutEngine


def run_backtest(
    cfg: BreakoutConfig,
    *,
    symbols: Optional[Iterable[str]] = None,
    tag: Optional[str] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    if cfg.start_date is None or cfg.end_date is None:
        raise ValueError("Backtest start_date and end_date are required")

    clean_symbols = _normalize_symbols(symbols or [])
    universe = (
        [UniverseStock(symbol=symbol) for symbol in clean_symbols]
        if clean_symbols
        else load_universe(cfg)
    )
    if not universe:
        raise ValueError("Backtest universe is empty")

    forward_days = max(10, cfg.earnings_blackout_sessions * 3)
    market_data = PointInTimeData(DATA_CACHE_DIR)
    market_data.load_or_download(
        symbols=[item.symbol for item in universe],
        benchmark=cfg.benchmark,
        start=cfg.start_date,
        end=cfg.end_date,
        warmup_days=cfg.warmup_days,
        forward_days=forward_days,
        use_cache=cfg.use_cache,
    )
    if not market_data.frames:
        raise RuntimeError("No price data downloaded")

    earnings = EarningsCalendar(DATA_CACHE_DIR)
    if cfg.enforce_earnings_blackout:
        earnings.load_or_download(
            [item.symbol for item in universe],
            cfg.start_date,
            cfg.end_date + timedelta(days=forward_days),
            use_cache=cfg.use_cache,
        )
        if not earnings.available:
            raise RuntimeError(
                "NSE earnings calendar is unavailable; refusing to bypass "
                "the configured earnings-blackout guardrail"
            )

    engine = BreakoutEngine(cfg, market_data, universe, earnings)
    engine.run(cfg.start_date, cfg.end_date)
    metrics = compute_metrics(
        engine.daily_log,
        engine.pf.closed,
        cfg.starting_capital,
        cfg.goal_capital(),
    )
    summary = render_summary(metrics, cfg.goal_return_pct).replace(
        "SWING BACKTEST", "52-WEEK BREAKOUT BACKTEST"
    )
    trades = [_jsonable(asdict(trade)) for trade in engine.pf.closed]
    signals = [_jsonable(signal) for signal in engine.signal_log]
    open_positions = [
        _jsonable(
            {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "entry_price": round(position.entry_price, 2),
                "entry_date": position.entry_date,
                "stop_loss": round(position.stop_loss, 2),
                "target_price": round(position.target_price, 2),
                "breakout_level": round(position.breakout_level, 2),
                "trailing_active": position.trailing_active,
            }
        )
        for position in engine.pf.positions.values()
    ]

    artifacts: Dict[str, str] = {}
    if write_outputs:
        run_tag = tag or (
            f"{cfg.universe_index}_{cfg.start_date.isoformat()}_"
            f"{cfg.end_date.isoformat()}_{datetime.now():%Y%m%dT%H%M%S}_"
            f"{uuid4().hex[:8]}"
        )
        output_dir = RESULTS_DIR / run_tag
        _write_outputs(
            output_dir,
            cfg,
            metrics,
            summary,
            trades,
            engine.daily_log,
            signals,
            open_positions,
        )
        artifacts = {
            name: str(output_dir / name)
            for name in (
                "summary.txt",
                "summary.json",
                "trades.csv",
                "equity_curve.csv",
                "signals.csv",
                "open_positions.json",
            )
        }

    return {
        "summary": summary,
        "metrics": metrics,
        "equity_curve": engine.daily_log,
        "trades": trades,
        "signals": signals,
        "open_positions": open_positions,
        "universe_size": len(universe),
        "earnings_calendar_coverage": sum(
            bool(events) for events in earnings.events.values()
        ),
        "artifacts": artifacts,
    }


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for raw in symbols:
        symbol = str(raw).strip().upper().replace(".NS", "").replace(".BO", "")
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, Path)):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _write_outputs(
    output_dir: Path,
    cfg: BreakoutConfig,
    metrics: Dict[str, Any],
    summary: str,
    trades: list[dict],
    equity_curve: list[dict],
    signals: list[dict],
    open_positions: list[dict],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.txt").write_text(summary, encoding="utf-8")
    (output_dir / "summary.json").write_text(
        json.dumps(
            {"config": _jsonable(asdict(cfg)), "metrics": metrics},
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_csv(output_dir / "trades.csv", trades)
    _write_csv(output_dir / "equity_curve.csv", equity_curve)
    _write_csv(output_dir / "signals.csv", signals)
    (output_dir / "open_positions.json").write_text(
        json.dumps(open_positions, indent=2), encoding="utf-8"
    )


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
