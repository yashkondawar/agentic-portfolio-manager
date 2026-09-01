"""Programmatic service for the point-in-time swing backtest."""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from uuid import uuid4

from core.storage import save_artifacts
from .config import DATA_CACHE_DIR, BacktestConfig
from .data import PointInTimeData
from .engine import BacktestEngine
from .metrics import compute_metrics, render_summary
from .watchlist import UniverseStock, load_universe

logger = logging.getLogger("backtest.service")


def run_backtest(
    cfg: BacktestConfig,
    *,
    symbols: Optional[Iterable[str]] = None,
    tag: Optional[str] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    """Run a backtest and return UI/CLI-friendly structured results."""
    if cfg.start_date is None or cfg.end_date is None:
        raise ValueError("Backtest start_date and end_date are required")
    if cfg.start_date >= cfg.end_date:
        raise ValueError("Backtest start_date must be before end_date")

    clean_symbols = _normalize_symbols(symbols or [])
    universe = (
        [UniverseStock(symbol=symbol) for symbol in clean_symbols]
        if clean_symbols
        else load_universe(cfg)
    )
    if not universe:
        raise ValueError("Backtest universe is empty")

    logger.info("Loading %d universe symbols", len(universe))
    market_data = PointInTimeData(DATA_CACHE_DIR)
    market_data.load_or_download(
        symbols=[item.symbol for item in universe],
        benchmark=cfg.benchmark,
        start=cfg.start_date,
        end=cfg.end_date,
        warmup_days=cfg.warmup_days,
        use_cache=cfg.use_cache,
    )
    if not market_data.frames:
        raise RuntimeError("No price data downloaded")

    engine = BacktestEngine(cfg, market_data, universe)
    try:
        engine.run(cfg.start_date, cfg.end_date)
    except SystemExit as exc:
        message = str(exc) or "Backtest could not run for the selected window"
        raise RuntimeError(message) from exc
    metrics = compute_metrics(
        engine.daily_log,
        engine.pf.closed,
        cfg.starting_capital,
        cfg.goal_capital(),
    )
    summary = render_summary(metrics, cfg.goal_return_pct)
    trades = [_jsonable(asdict(trade)) for trade in engine.pf.closed]
    open_positions = [
        _jsonable(
            {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "entry_price": round(position.entry_price, 2),
                "entry_date": position.entry_date,
                "stop_loss": round(position.stop_loss, 2),
                "target_price": round(position.target_price, 2),
                "setup": position.setup,
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
        artifacts = _store_outputs(
            run_tag,
            cfg,
            metrics,
            summary,
            trades,
            engine.daily_log,
            engine.watchlist_log,
            open_positions,
        )

    return {
        "summary": summary,
        "metrics": metrics,
        "equity_curve": engine.daily_log,
        "trades": trades,
        "watchlists": engine.watchlist_log,
        "open_positions": open_positions,
        "universe_size": len(universe),
        "artifacts": artifacts,
    }


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for raw in symbols:
        symbol = str(raw).strip().upper().replace(".NS", "")
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


def _store_outputs(
    run_tag: str,
    cfg: BacktestConfig,
    metrics: Dict[str, Any],
    summary: str,
    trades: list[dict],
    equity_curve: list[dict],
    watchlists: list[dict],
    open_positions: list[dict],
) -> Dict[str, str]:
    stored = {
        "summary.txt": summary,
        "summary.json": {"config": _jsonable(asdict(cfg)), "metrics": metrics},
        "trades.csv": _render_csv(
        trades,
        [
            "symbol",
            "setup",
            "quantity",
            "entry_date",
            "entry_price",
            "exit_date",
            "exit_price",
            "pnl",
            "pnl_pct",
            "holding_days",
            "exit_reason",
        ],
        ),
        "equity_curve.csv": _render_csv(
        equity_curve,
        [
            "date",
            "equity",
            "cash",
            "deployed",
            "open_positions",
            "watchlist_size",
        ],
        ),
        "watchlists.json": watchlists,
        "open_positions.json": open_positions,
    }
    _, references = save_artifacts(
        "swing_backtest",
        run_tag,
        stored,
        metadata={"config": _jsonable(asdict(cfg)), "metrics": metrics},
        content_types={
            "summary.txt": "text/plain",
            "trades.csv": "text/csv",
            "equity_curve.csv": "text/csv",
        },
    )
    return references


def _render_csv(rows: list[dict], fieldnames: list[str]) -> str:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()
