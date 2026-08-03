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
    """Class decorator that adds a strategy to the registry.

    Reload-safe: when a dev reloader (e.g. Streamlit's file watcher) re-executes
    a strategy module, its ``@register`` fires again with a *new* class object
    that has the same ``id``, ``__module__`` and ``__qualname__`` as the one
    already registered. That is a hot-reload, not a collision, so we overwrite
    the stale entry. We only reject a genuine duplicate: two *different*
    strategies (distinct module/qualname) claiming the same ``id``.
    """
    if not getattr(cls, "id", ""):
        raise ValueError(f"Strategy {cls.__name__} must define a non-empty 'id'")
    existing = _REGISTRY.get(cls.id)
    if existing is not None and existing is not cls and not _is_reload_of(existing, cls):
        raise ValueError(f"Duplicate strategy id '{cls.id}' ({cls.__name__})")
    _REGISTRY[cls.id] = cls
    logger.debug("Registered strategy '%s' (%s)", cls.id, cls.__name__)
    return cls


def _is_reload_of(existing: Type[BaseStrategy], cls: Type[BaseStrategy]) -> bool:
    """True when ``cls`` is a reloaded version of ``existing`` (same origin)."""
    return (
        getattr(existing, "__module__", None) == getattr(cls, "__module__", None)
        and getattr(existing, "__qualname__", None) == getattr(cls, "__qualname__", None)
    )


def _ensure_loaded() -> None:
    """Import the strategies package so every strategy self-registers.

    The :mod:`strategies` package imports each strategy independently, so one
    broken strategy no longer aborts the rest.

    Hot-reload safety: Streamlit (and other dev reloaders) re-execute this
    module when its source changes, which resets ``_REGISTRY`` to empty and
    ``_LOADED`` to ``False``. The strategy submodules, however, remain cached in
    :data:`sys.modules`, so a plain ``import strategies`` is a no-op and their
    ``@register`` side effects never re-run against the fresh registry.

    This desync comes in two shapes and we heal both:

    * **Empty** -- no strategy re-registered, surfacing the misleading
      ``Unknown strategy '...'. Available: (none)``.
    * **Partial** -- Streamlit's own watcher re-executed *some* (typically just
      the last-edited) strategy module against the new registry, so only those
      re-register, surfacing e.g. ``Available: swing_backtest``.

    We therefore treat "loaded" as *the registry holding every successfully
    imported strategy* (not merely non-empty), and force-reload the cached
    strategy submodules whenever it falls short so every strategy re-registers.
    """
    global _LOADED
    if _LOADED and _registry_is_complete():
        return
    try:
        import strategies  # noqa: F401  (imported for registration side effects)
    except Exception:  # pragma: no cover - defensive; allow a later retry
        logger.exception("Failed to import strategies package")
        return
    if not _registry_is_complete(strategies):
        _reregister_cached_strategies(strategies)
    _LOADED = True
    if getattr(strategies, "failed_imports", None):
        logger.warning(
            "Some strategies failed to load and are unavailable: %s",
            ", ".join(sorted(strategies.failed_imports)),
        )


def _registry_is_complete(strategies_pkg=None) -> bool:
    """True when every successfully imported strategy module is registered.

    Each strategy submodule registers exactly one strategy, so the registry is
    complete once it holds ``(#strategy modules) - (#failed imports)`` entries.
    Returns ``False`` when the ``strategies`` package hasn't been imported yet
    so the caller proceeds to import it.
    """
    pkg = strategies_pkg or sys.modules.get("strategies")
    if pkg is None:
        return False
    modules = getattr(pkg, "_STRATEGY_MODULES", ())
    failed = getattr(pkg, "failed_imports", {})
    expected = len(modules) - len(failed)
    return len(_REGISTRY) >= expected


def _reregister_cached_strategies(strategies_pkg) -> None:
    """Reload cached ``strategies.*`` submodules so their decorators re-fire.

    Called when the registry is missing strategies that were already imported
    (cached) under a previous incarnation of this registry module -- either
    fully empty or partially populated. Reloading each re-runs its top-level
    ``@register`` against the current ``_REGISTRY``; :func:`register` is
    reload-safe, so re-registering an already-present strategy just refreshes
    it rather than raising a duplicate error.
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
