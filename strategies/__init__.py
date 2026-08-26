"""Concrete strategies for the platform.

Importing this package registers every strategy with
:mod:`core.registry`. Each module below wraps one existing "system" behind
the common :class:`core.strategy.BaseStrategy` interface, so they can all be
listed and invoked uniformly (e.g. from the UI or ``run.py``).

Each strategy submodule self-registers (via the ``@register`` decorator) as an
import side effect. They are imported **independently** so that a single broken
strategy is logged and skipped instead of taking the whole registry down with
it — previously one failing import aborted the entire package import, which the
registry then surfaced as the misleading ``Unknown strategy '...'. Available:
(none)``.
"""

import importlib
import logging

logger = logging.getLogger(__name__)

# Order preserved from the original package so registration order is stable.
_STRATEGY_MODULES = (
    "sequential_agents",
    "parallel_agents",
    "swing_trading",
    "portfolio_analysis",
    "watchlist_curation",
    "qtr_results",
    "gfs_live",
    "swing_backtest",
)

# Maps strategy module name -> the exception that stopped it importing. Empty
# when every strategy loaded cleanly. Exposed for diagnostics (UI/tests/logs).
failed_imports: dict[str, Exception] = {}

for _name in _STRATEGY_MODULES:
    try:
        globals()[_name] = importlib.import_module(f"{__name__}.{_name}")
    except Exception as exc:  # noqa: BLE001 - isolate one bad strategy
        failed_imports[_name] = exc
        logger.exception(
            "Failed to import strategy module '%s'; it will be unavailable", _name
        )

__all__ = [name for name in _STRATEGY_MODULES if name in globals()]
