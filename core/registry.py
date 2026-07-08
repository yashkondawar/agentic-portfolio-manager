"""Central strategy registry.

Concrete strategies register themselves (via the :func:`register` decorator)
when the :mod:`strategies` package is imported. Everything else in the app —
the unified ``run.py`` entry point and any UI — goes through here, so nothing
needs to know about individual strategy modules.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from core.strategy import BaseStrategy, StrategyResult

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, Type[BaseStrategy]] = {}
_LOADED = False


def register(cls: Type[BaseStrategy]) -> Type[BaseStrategy]:
    """Class decorator that adds a strategy to the registry."""
    if not getattr(cls, "id", ""):
        raise ValueError(f"Strategy {cls.__name__} must define a non-empty 'id'")
    if cls.id in _REGISTRY and _REGISTRY[cls.id] is not cls:
        raise ValueError(f"Duplicate strategy id '{cls.id}' ({cls.__name__})")
    _REGISTRY[cls.id] = cls
    logger.debug("Registered strategy '%s' (%s)", cls.id, cls.__name__)
    return cls


def _ensure_loaded() -> None:
    """Import the strategies package once so every strategy self-registers."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    # Imported for its import side effects (registration). Guarded so a single
    # broken strategy doesn't take down the whole registry.
    try:
        import strategies  # noqa: F401
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to import strategies package")


def list_strategies() -> List[Type[BaseStrategy]]:
    """Return all registered strategy classes."""
    _ensure_loaded()
    return list(_REGISTRY.values())


def list_specs() -> List[dict]:
    """Return serializable metadata + param schema for every strategy.

    This is the single call a UI needs to render all available options.
    """
    return [cls.spec() for cls in list_strategies()]


def get_strategy(strategy_id: str) -> BaseStrategy:
    """Instantiate a strategy by id."""
    _ensure_loaded()
    cls = _REGISTRY.get(strategy_id)
    if cls is None:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"Unknown strategy '{strategy_id}'. Available: {available}")
    return cls()


def run_strategy(strategy_id: str, params: Optional[dict] = None) -> StrategyResult:
    """Instantiate and run a strategy — the one call the UI/CLI invokes."""
    try:
        strategy = get_strategy(strategy_id)
        resolved = strategy.coerce_params(params)
        return strategy.run(resolved)
    except Exception as exc:  # surface as a uniform failed result
        logger.exception("Strategy '%s' failed", strategy_id)
        return StrategyResult(
            strategy_id=strategy_id,
            status="failed",
            report=f"Strategy '{strategy_id}' failed: {exc}",
            error=str(exc),
        )


__all__ = [
    "register",
    "list_strategies",
    "list_specs",
    "get_strategy",
    "run_strategy",
]
