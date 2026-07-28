"""Central strategy registry.

Concrete strategies register themselves (via the :func:`register` decorator)
when the :mod:`strategies` package is imported. Everything else in the app —
the unified ``run.py`` entry point and any UI — goes through here, so nothing
needs to know about individual strategy modules.
"""

from __future__ import annotations

import importlib
import logging
import sys
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
    """Import the strategies package so every strategy self-registers.

    The :mod:`strategies` package imports each strategy independently, so one
    broken strategy no longer aborts the rest.

    Hot-reload safety: Streamlit (and other dev reloaders) re-execute this
    module when its source changes, which resets ``_REGISTRY`` to empty and
    ``_LOADED`` to ``False``. The strategy submodules, however, remain cached in
    :data:`sys.modules`, so a plain ``import strategies`` is a no-op and their
    ``@register`` side effects never re-run against the fresh registry — leaving
    it permanently empty and surfacing the misleading ``Unknown strategy '...'.
    Available: (none)``. We therefore key the "already loaded" check on the
    registry actually being populated, and force-reload the cached strategy
    submodules when we detect that desync so every strategy re-registers.
    """
    global _LOADED
    if _LOADED and _REGISTRY:
        return
    try:
        import strategies  # noqa: F401  (imported for registration side effects)
    except Exception:  # pragma: no cover - defensive; allow a later retry
        logger.exception("Failed to import strategies package")
        return
    if not _REGISTRY:
        _reregister_cached_strategies(strategies)
    _LOADED = True
    if getattr(strategies, "failed_imports", None):
        logger.warning(
            "Some strategies failed to load and are unavailable: %s",
            ", ".join(sorted(strategies.failed_imports)),
        )


def _reregister_cached_strategies(strategies_pkg) -> None:
    """Reload cached ``strategies.*`` submodules so their decorators re-fire.

    Called only when ``import strategies`` left the registry empty, which means
    the submodules were already imported (cached) under a previous incarnation
    of this registry module. Reloading each re-runs its top-level ``@register``
    against the current ``_REGISTRY``.
    """
    prefix = f"{strategies_pkg.__name__}."
    names = getattr(strategies_pkg, "_STRATEGY_MODULES", None) or tuple(
        mod_name[len(prefix):]
        for mod_name in list(sys.modules)
        if mod_name.startswith(prefix)
    )
    for name in names:
        module = sys.modules.get(f"{prefix}{name}")
        if module is None:
            continue
        try:
            importlib.reload(module)
        except Exception:  # noqa: BLE001 - isolate one bad strategy
            logger.exception(
                "Failed to reload cached strategy module '%s'", name
            )


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
