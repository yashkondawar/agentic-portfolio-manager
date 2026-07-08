"""Core backbone for the agentic stock research system.

This package holds the shared infrastructure that ties every "system"
(sequential agents, parallel agents, swing trading, portfolio analysis,
watchlist curation) together behind a single, uniform interface:

    from core import registry
    specs   = registry.list_specs()          # -> UI can render options
    result  = registry.run_strategy(id, {})  # -> uniform StrategyResult

The concrete strategies live in the top-level ``strategies`` package and
self-register on import.
"""

from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)

__all__ = [
    "BaseStrategy",
    "ParamSpec",
    "ParamType",
    "StrategyCategory",
    "StrategyResult",
]
