"""
service.py
==========

Orchestration: universe -> data -> panels -> engine -> metrics -> baselines ->
artifacts.

The deliberate design choice here is that **a plain run and a validation run are
the same code path**. Ablations and the random-entry null are not a separate
"research script" you have to remember to run; they are options on the same
function, writing into the same artifact bundle. A result that has not been
challenged is not a result, and making the challenge cheap is the only reliable
way to ensure it actually happens.

Data is downloaded once and reused across every variant in a session
(:class:`PointInTimeData` is created a single time and passed down), so an
eleven-variant ablation study costs one download, not eleven.
"""

import csv
import io
import logging
from dataclasses import asdict, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from core.storage import save_artifacts

from ..swing_trading.data import PointInTimeData
from . import baselines as bl
from .config import DATA_CACHE_DIR, AblationVariant, GFSConfig
from .engine import GFSBacktestEngine
from .metrics import compute_metrics, render_summary
from . import taxes as tx
from .panels import (
    base_panel_key,
    build_panels,
    build_qualify_matrix,
    build_regime_panel,
    build_sector_panel,
    master_calendar,
)
from .universe import UniverseStock, load_universe, universe_bias_note

logger = logging.getLogger("gfs.service")


class PreparedData:
    """Downloaded prices plus everything derived from them for one config.

    Panels depend on config, but only *partly*: thresholds change booleans while
    RSI periods change the expensive indicator pass. The costly half is cached
    under :func:`base_panel_key`, so an eleven-variant ablation study - or a
    324-configuration sweep - pays for the indicator pass once, not once per
    trial. Without this the sweep is theoretically correct and practically
    unrunnable, which in the end is the same as being wrong.
    """

    def __init__(self, market: PointInTimeData, universe: List[UniverseStock]):
        self.market = market
        self.universe = universe
        self._base_key = None
        self._base_cache: Dict[str, Any] = {}

    def _cache_for(self, cfg: GFSConfig) -> Dict[str, Any]:
        key = base_panel_key(cfg)
        if key != self._base_key:
            self._base_key = key
            self._base_cache = {}
        return self._base_cache

    def panels_for(self, cfg: GFSConfig):
        panels = build_panels(self.market, self.universe, cfg, self._cache_for(cfg))
        if not panels:
            raise RuntimeError(
                "No symbol had enough history to evaluate. Increase warmup_days "
                "or widen the date range."
            )
        calendar = master_calendar(self.market.benchmark, panels)
        sector_panel = build_sector_panel(panels, calendar, cfg)
        regime_panel = build_regime_panel(self.market.benchmark, panels, calendar, cfg)
        qualify = build_qualify_matrix(panels, calendar, cfg)
        return panels, calendar, sector_panel, regime_panel, qualify


def prepare_data(
    cfg: GFSConfig, symbols: Optional[Iterable[str]] = None
) -> PreparedData:
    clean = _normalize_symbols(symbols or [])
    universe = (
        [UniverseStock(symbol=s) for s in clean] if clean else load_universe(cfg)
    )
    if not universe:
        raise ValueError("Universe is empty")

    logger.info("Loading price history for %d symbols", len(universe))
    market = PointInTimeData(DATA_CACHE_DIR)
    market.load_or_download(
        symbols=[item.symbol for item in universe],
        benchmark=cfg.benchmark,
        start=cfg.start_date,
        end=cfg.end_date,
        warmup_days=cfg.warmup_days,
        use_cache=cfg.use_cache,
    )
    if not market.frames:
        raise RuntimeError("No price data downloaded")
    return PreparedData(market, universe)


def run_single(
    cfg: GFSConfig,
    prepared: PreparedData,
    *,
    with_forward_study: bool = True,
    monte_carlo_runs: int = 0,
) -> Dict[str, Any]:
    """One backtest with one config. Returns metrics, trades and diagnostics."""
    cfg.validate()
    panels, calendar, sector_panel, regime_panel, qualify = prepared.panels_for(cfg)

    engine = GFSBacktestEngine(cfg, panels, sector_panel, regime_panel, qualify, calendar)
    engine.run(cfg.start_date, cfg.end_date)

    benchmark_curve = bl.buy_and_hold_curve(
        prepared.market.benchmark, engine.daily_log, cfg.starting_capital
    )
    metrics = compute_metrics(
        engine.daily_log,
        engine.pf.closed,
        cfg.starting_capital,
        benchmark_curve=benchmark_curve,
    )
    metrics["signal_frequency"] = engine.signal_frequency()
    metrics["rejections"] = dict(
        sorted(engine.rejections.items(), key=lambda kv: -kv[1])
    )
    metrics["universe_size"] = len(prepared.universe)
    metrics["panels_built"] = len(panels)

    if with_forward_study:
        metrics["forward_return_study"] = bl.forward_return_study(panels, qualify)
    if monte_carlo_runs > 0:
        metrics["random_entry_null"] = bl.random_entry_null(
            panels, engine.pf.closed, cfg, num_runs=monte_carlo_runs
        )

    return {
        "config": cfg,
        "metrics": metrics,
        "equity_curve": engine.daily_log,
        "trades": [_jsonable(asdict(t)) for t in engine.pf.closed],
        "signals": engine.signal_log,
        "benchmark_curve": benchmark_curve,
        "open_positions": [
            _jsonable(
                {
                    "symbol": p.symbol,
                    "sector": p.sector,
                    "quantity": p.quantity,
                    "entry_price": round(p.entry_price, 2),
                    "entry_date": p.entry_date,
                    "stop_loss": round(p.stop_loss, 2),
                    "target_price": round(p.target_price, 2),
                }
            )
            for p in engine.pf.positions.values()
        ],
    }


def run_ablations(
    base_cfg: GFSConfig,
    prepared: PreparedData,
    variants: Optional[List[AblationVariant]] = None,
) -> List[Dict[str, Any]]:
    """Run each single-change variant and collect a comparable row per variant."""
    variants = variants or bl.ablation_variants()
    rows: List[Dict[str, Any]] = []
    for variant in variants:
        cfg = replace(base_cfg, **variant.overrides) if variant.overrides else base_cfg
        cfg.label = f"{base_cfg.label}_{variant.name}"
        logger.info("Ablation: %s", variant.name)
        try:
            result = run_single(cfg, prepared, with_forward_study=False)
        except Exception as exc:  # noqa: BLE001 - one bad variant must not kill the study
            logger.warning("Ablation %s failed: %s", variant.name, exc)
            rows.append({"variant": variant.name, "question": variant.question, "error": str(exc)})
            continue
        m = result["metrics"]
        rows.append(
            {
                "variant": variant.name,
                "question": variant.question,
                "overrides": {k: str(v) for k, v in variant.overrides.items()},
                "total_return_pct": m.get("total_return_pct"),
                "cagr_pct": m.get("cagr_pct"),
                "max_drawdown_pct": m.get("max_drawdown_pct"),
                "sharpe": m.get("sharpe"),
                "calmar": m.get("calmar"),
                "trades": m.get("num_trades"),
                "win_rate_pct": m.get("win_rate_pct"),
                "avg_trade_pct": m.get("expectancy_pct"),
                "expectancy_r": m.get("expectancy_r"),
                "profit_factor": m.get("profit_factor"),
            }
        )
    return rows


def render_ablation_table(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    header = (
        f" {'variant':<24}{'CAGR':>8}{'MaxDD':>8}{'Sharpe':>8}{'Trades':>8}"
        f"{'Win%':>7}{'Avg%':>7}{'ExpR':>7}"
    )
    lines = ["-" * 78, " ABLATION STUDY - which leg is actually load-bearing?", header]
    for row in rows:
        if "error" in row:
            lines.append(f" {row['variant']:<24}  FAILED: {row['error'][:44]}")
            continue
        lines.append(
            f" {row['variant']:<24}{_n(row['cagr_pct']):>7.1f}%{_n(row['max_drawdown_pct']):>7.1f}%"
            f"{_n(row['sharpe']):>8.2f}{int(_n(row['trades'])):>8}"
            f"{_n(row['win_rate_pct']):>6.1f}%{_n(row['avg_trade_pct']):>6.2f}%"
            f"{_n(row['expectancy_r']):>7.2f}"
        )
    lines.append(
        " Read down the column, not across: if 'no_grandfather_father' matches"
    )
    lines.append(
        " 'baseline', the monthly/weekly filter is decoration, not an edge."
    )
    return "\n".join(lines)


def _n(value) -> float:
    return 0.0 if value is None else float(value)


def _config_summary(cfg: GFSConfig) -> str:
    """The handful of settings that change what is actually being tested."""
    return "\n".join(
        [
            f" Universe   : {cfg.universe_index}   benchmark {cfg.benchmark}",
            f" GFS rule   : monthly RSI>{cfg.g_rsi_min:g}, weekly RSI>{cfg.f_rsi_min:g},"
            f" daily {cfg.entry_trigger} at {cfg.s_rsi_entry:g}"
            f"   [HTF candles: {cfg.htf_mode}]",
            f" Exit       : {cfg.exit_mode} (RSI {cfg.exit_rsi:g}),"
            f" stop {cfg.stop_mode}"
            f"{f' {cfg.atr_stop_mult:g}x ATR' if cfg.stop_mode == 'atr' else ''}"
            f"{f' {cfg.fixed_stop_pct:g}%' if cfg.stop_mode == 'pct' else ''},"
            f" time stop {cfg.max_holding_days}d",
            f" Sizing     : {cfg.sizing_mode}, max {cfg.max_positions} positions,"
            f" <={cfg.max_position_pct:g}% each, <={cfg.max_per_sector}/sector",
            f" Gates      : regime={cfg.use_regime_filter} (SMA{cfg.regime_sma},"
            f" breadth>={cfg.min_breadth_pct:g}%),"
            f" sector={cfg.use_sector_filter} (top {cfg.sector_top_n})",
            f" Costs      : {cfg.commission_pct:g}%/side + {cfg.slippage_bps:g}bps"
            f" slippage/side   |   indicator exits delayed: {cfg.indicator_exit_delay}",
        ]
    )


def run_study(
    cfg: GFSConfig,
    *,
    symbols: Optional[Iterable[str]] = None,
    ablations: bool = False,
    monte_carlo_runs: int = 0,
    sweep: bool = False,
    train_months: int = 36,
    test_months: int = 12,
    stability_param: Optional[str] = None,
    tag: Optional[str] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    """Full entry point: baseline run, optional challenges, persisted artifacts."""
    cfg.validate()
    prepared = prepare_data(cfg, symbols)
    result = run_single(cfg, prepared, monte_carlo_runs=monte_carlo_runs)

    bias = universe_bias_note(cfg, prepared.universe)
    metrics = result["metrics"]
    years = float(metrics.get("years", 0.0) or 0.0)
    tax_summary = tx.net_summary(
        result["trades"], cfg.starting_capital, years, cfg.tax
    )
    sections = [
        render_summary(
            metrics,
            cfg_summary=_config_summary(cfg),
            signal_stats=metrics.get("signal_frequency"),
            rejections=metrics.get("rejections"),
        ),
        tx.render_tax_summary(
            tax_summary,
            benchmark_gross_cagr=metrics.get("benchmark", {}).get("cagr_pct"),
            years=years,
            cfg=cfg.tax,
        ),
        bl.render_forward_study(metrics.get("forward_return_study", {})),
        bl.render_random_null(metrics.get("random_entry_null", {})),
    ]

    ablation_rows: List[Dict[str, Any]] = []
    if ablations:
        ablation_rows = run_ablations(cfg, prepared)
        sections.append(render_ablation_table(ablation_rows))

    # The sweep is imported lazily: it imports this module, and a top-level
    # import would be circular.
    sweep_report: Dict[str, Any] = {}
    stability_rows: List[Dict[str, Any]] = []
    if sweep or stability_param:
        from . import sweep as sw

        if sweep:
            sweep_report = sw.walk_forward_sweep(
                cfg,
                prepared,
                train_months=train_months,
                test_months=test_months,
            )
            sections.append(sw.render_sweep(sweep_report))
        if stability_param:
            stability_rows = sw.parameter_stability(cfg, prepared, stability_param)
            sections.append(sw.render_stability_curve(stability_rows, stability_param))

    sections.append("-" * 78)
    sections.append(_wrap(bias, 78))
    summary = "\n".join(s for s in sections if s)

    artifacts: Dict[str, str] = {}
    if write_outputs:
        run_tag = tag or (
            f"{cfg.label}_{cfg.start_date.isoformat()}_{cfg.end_date.isoformat()}"
            f"_{datetime.now():%Y%m%dT%H%M%S}_{uuid4().hex[:8]}"
        )
        artifacts = _store_outputs(
            run_tag,
            cfg,
            result,
            summary,
            ablation_rows,
            bias,
            sweep_report,
            stability_rows,
        )

    return {
        "summary": summary,
        "metrics": result["metrics"],
        "equity_curve": result["equity_curve"],
        "trades": result["trades"],
        "signals": result["signals"],
        "open_positions": result["open_positions"],
        "ablations": ablation_rows,
        "sweep": sweep_report,
        "stability": stability_rows,
        "universe_bias_note": bias,
        "artifacts": artifacts,
    }


# ── artifact plumbing ────────────────────────────────────────────────────────


def _wrap(text: str, width: int) -> str:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return "\n".join(lines)


def _normalize_symbols(symbols: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for raw in symbols:
        symbol = str(raw).strip().upper().replace(".NS", "")
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, Path)):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _render_csv(rows: List[dict], fieldnames: List[str]) -> str:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()


def _store_outputs(
    run_tag: str,
    cfg: GFSConfig,
    result: Dict[str, Any],
    summary: str,
    ablation_rows: List[Dict[str, Any]],
    bias: str,
    sweep_report: Optional[Dict[str, Any]] = None,
    stability_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:
    config_json = _jsonable(asdict(cfg))
    stored = {
        "summary.txt": summary,
        "summary.json": {
            "config": config_json,
            "metrics": result["metrics"],
            "universe_bias_note": bias,
        },
        "trades.csv": _render_csv(
            result["trades"],
            [
                "symbol",
                "sector",
                "quantity",
                "entry_date",
                "entry_price",
                "exit_date",
                "exit_price",
                "pnl",
                "pnl_pct",
                "r_multiple",
                "holding_days",
                "exit_reason",
                "mae_pct",
                "mfe_pct",
                "mae_r",
                "mfe_r",
                "entry_rsi_m",
                "entry_rsi_w",
                "entry_rsi_d",
                "partial",
            ],
        ),
        "equity_curve.csv": _render_csv(
            result["equity_curve"],
            ["date", "equity", "cash", "deployed", "open_positions", "regime_ok", "breadth_pct"],
        ),
        "signals.csv": _render_csv(
            result["signals"], ["date", "qualifying", "regime_ok", "open_positions"]
        ),
        "open_positions.json": result["open_positions"],
    }
    if ablation_rows:
        stored["ablations.json"] = ablation_rows
    if sweep_report:
        stored["sweep.json"] = _jsonable(sweep_report)
    if stability_rows:
        stored["stability.json"] = _jsonable(stability_rows)
    _, references = save_artifacts(
        "gfs_backtest",
        run_tag,
        stored,
        metadata={"config": config_json, "metrics": result["metrics"]},
        content_types={
            "summary.txt": "text/plain",
            "trades.csv": "text/csv",
            "equity_curve.csv": "text/csv",
            "signals.csv": "text/csv",
        },
    )
    return references
