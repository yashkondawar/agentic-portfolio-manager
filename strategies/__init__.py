"""Concrete strategies for the platform.

Importing this package registers every strategy with
:mod:`core.registry`. Each module below wraps one existing "system" behind
the common :class:`core.strategy.BaseStrategy` interface, so they can all be
listed and invoked uniformly (e.g. from the UI or ``run.py``).
"""

# Importing each module triggers the @register decorator side effect.
from . import sequential_agents  # noqa: F401
from . import parallel_agents  # noqa: F401
from . import swing_trading  # noqa: F401
from . import portfolio_analysis  # noqa: F401
from . import watchlist_curation  # noqa: F401
from . import qtr_results  # noqa: F401

__all__ = [
    "sequential_agents",
    "parallel_agents",
    "swing_trading",
    "portfolio_analysis",
    "watchlist_curation",
    "qtr_results",
]
