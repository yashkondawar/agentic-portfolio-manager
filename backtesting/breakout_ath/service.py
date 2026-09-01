"""Run the ATH breakout backtest and persist its artefacts.

This is the seam the CLI, the UI and the tests all go through, so a run is
reproducible from a single :class:`AthBreakoutConfig`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import pandas as pd

from . import dossier
from .config import RESULTS_DIR, AthBreakoutConfig
from .data import load_prices
from .engine import AthBreakoutEngine
from .metrics import summarise

logger = logging.getLogger(__name__)


def run_backtest(
    cfg: Optional[AthBreakoutConfig] = None,
    *,
    download: bool = False,
    write_dossier: bool = True,
    results_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run the sleeve end to end and return its headline results.

    ``download`` refreshes prices from yfinance first; leave it off to run
    against the cached bar store, which is what the tests do.
    """
    cfg = cfg or AthBreakoutConfig()
    cfg.validate()

    prices = load_prices(cfg, download=download)
    engine = AthBreakoutEngine(cfg, prices).run()
    metrics = summarise(cfg, engine)

    out = Path(results_dir or RESULTS_DIR)
    out.mkdir(parents=True, exist_ok=True)

    payload = {
        "config": _jsonable(asdict(cfg)),
        "metrics": _jsonable(metrics),
        "generated_at": date.today().isoformat(),
    }
    (out / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    _write_csv(out / "trades.csv", engine.pf.fills)
    _write_csv(out / "positions.csv", engine.pf.closed)

    workbook: Optional[Path] = None
    if write_dossier:
        sheets = dossier.build(cfg, engine, metrics=metrics)
        workbook = dossier.write(sheets, out / "dossier.xlsx")

    logger.info(
        "ATH backtest complete: %d fills, %d round trips, final equity %.0f",
        len(engine.pf.fills),
        len(engine.pf.closed),
        metrics.get("final_value", 0.0),
    )
    return {
        "config": cfg,
        "engine": engine,
        "metrics": metrics,
        "results_dir": out,
        "dossier": workbook,
    }


def _write_csv(path: Path, rows: Sequence[Any]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    frame = pd.DataFrame(
        [asdict(r) if hasattr(r, "__dataclass_fields__") else dict(r) for r in rows]
    )
    frame.to_csv(path, index=False)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return str(value)
    return value
