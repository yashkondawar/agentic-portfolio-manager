"""Central strategy registry.

Concrete strategies register themselves (via the :func:`register` decorator)
when the :mod:`strategies` package is imported. Everything else in the app —
the unified ``run.py`` entry point and any UI — goes through here, so nothing
needs to know about individual strategy modules.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import sys
from types import ModuleType
from typing import Dict, Iterator, List, Optional, Tuple, Type

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

    Streamlit makes this worse than a plain reload: on *any* watched-file event
    its ``LocalSourcesWatcher.on_path_changed`` **deletes every watched module
    from ``sys.modules``** and reruns the script, from the watcher thread — so
    the deletion can land midway through this module's own import work. Whatever
    subset of modules is then re-executed registers against a different registry
    incarnation than the rest, which is how a *partial* registry appears.

    This desync comes in two shapes and we heal both:

    * **Empty** -- no strategy re-registered, surfacing the misleading
      ``Unknown strategy '...'. Available: (none)``.
    * **Partial** -- only some strategy modules were re-executed against the new
      registry, surfacing e.g. ``Available: swing_backtest``.

    We therefore treat "loaded" as *the registry holding every successfully
    imported strategy* (not merely non-empty), and recover the missing ones by
    scanning the reachable strategy submodules for their strategy classes and
    re-registering them directly -- no module reload, so a strategy with a heavy
    transitive import chain (e.g. ``swing_backtest`` ->
    ``backtesting.swing_trading.*``) can't fail to re-register just because its
    dependencies are momentarily in a half-reloaded state.
    """
    global _LOADED
    if _LOADED and _registry_is_complete():
        return
    try:
        import strategies  # noqa: F401  (imported for registration side effects)
    except Exception:  # pragma: no cover - defensive; allow a later retry
        # A concurrent ``del sys.modules[...]`` from the watcher thread can abort
        # an in-flight import. Drop any half-initialized package and retry once
        # before giving up, so the caller isn't handed a torn registry.
        logger.exception("Failed to import strategies package; retrying once")
        sys.modules.pop("strategies", None)
        try:
            import strategies  # noqa: F401
        except Exception:
            logger.exception("Failed to import strategies package")
            return
    if not _registry_is_complete(strategies):
        _recover_from_cached_modules(strategies)
    _LOADED = _registry_is_complete(strategies)
    if getattr(strategies, "failed_imports", None):
        logger.warning(
            "Some strategies failed to load and are unavailable: %s",
            ", ".join(sorted(strategies.failed_imports)),
        )


def _registry_is_complete(strategies_pkg=None) -> bool:
    """True when every successfully imported strategy module is registered.

    Completeness is decided by *which* modules are represented, not by how many
    entries the registry happens to hold. A count-based check (``len(_REGISTRY)
    >= expected``) can be satisfied by the wrong set: when a reloader tears the
    import state apart, ``strategies.failed_imports`` can be large while the
    registry holds a single unrelated strategy, and the count test then declares
    a one-entry registry "complete" and caches that broken state for the life of
    the process. Comparing module identities makes the check exact.

    Returns ``False`` when the ``strategies`` package hasn't been imported yet
    so the caller proceeds to import it.
    """
    pkg = strategies_pkg or sys.modules.get("strategies")
    if pkg is None:
        return False
    modules = getattr(pkg, "_STRATEGY_MODULES", ())
    failed = getattr(pkg, "failed_imports", {})
    expected = {f"{pkg.__name__}.{name}" for name in modules if name not in failed}
    registered = {getattr(cls, "__module__", None) for cls in _REGISTRY.values()}
    return expected.issubset(registered)


def _looks_like_strategy(obj, module_name: str) -> bool:
    """Duck-typed test for "this is the strategy class defined in *module_name*".

    Deliberately does **not** use ``issubclass(obj, BaseStrategy)``. When a dev
    reloader (Streamlit's watcher) re-executes ``core.strategy``, ``BaseStrategy``
    becomes a *new* class object while the strategy modules cached in
    ``sys.modules`` still subclass the *old* one. An identity-based
    ``issubclass`` check then returns ``False`` for every real strategy, recovery
    finds nothing, and the registry surfaces the misleading
    ``Available: (none)``. Matching on structure instead (a class defined in this
    module that carries a non-empty string ``id`` and callable ``run``/``spec``)
    is immune to ``BaseStrategy`` identity changes, since every consumer uses the
    strategy purely by that same duck-typed shape anyway.
    """
    return (
        inspect.isclass(obj)
        and getattr(obj, "__module__", None) == module_name
        and isinstance(getattr(obj, "id", None), str)
        and bool(getattr(obj, "id", ""))
        and callable(getattr(obj, "run", None))
        and callable(getattr(obj, "spec", None))
    )


def _strategy_module_names(strategies_pkg) -> Tuple[str, ...]:
    """Names of the strategy submodules, from the package or ``sys.modules``."""
    prefix = f"{strategies_pkg.__name__}."
    names = getattr(strategies_pkg, "_STRATEGY_MODULES", None)
    if names:
        return tuple(names)
    return tuple(
        mod_name[len(prefix):]
        for mod_name in list(sys.modules)
        if mod_name.startswith(prefix)
    )


def _iter_strategy_modules(strategies_pkg) -> Iterator[Tuple[str, ModuleType]]:
    """Yield ``(full_module_name, module)`` for every reachable strategy module.

    Looks in **both** ``sys.modules`` and the ``strategies`` package's own
    attributes. That second source is what makes recovery survive Streamlit:
    its ``LocalSourcesWatcher.on_path_changed`` does not *reload* local modules,
    it **deletes every watched module from ``sys.modules``** and then reruns the
    script. Any recovery that only consults ``sys.modules`` therefore finds
    nothing for the deleted modules. ``strategies/__init__`` keeps a reference to
    each submodule it imported, so the already-constructed strategy classes are
    still reachable there even after the deletion — no re-execution needed.
    """
    prefix = f"{strategies_pkg.__name__}."
    for name in _strategy_module_names(strategies_pkg):
        full_name = f"{prefix}{name}"
        module = sys.modules.get(full_name) or getattr(strategies_pkg, name, None)
        if isinstance(module, ModuleType):
            yield full_name, module


def _register_from_module(module: ModuleType, full_name: str) -> bool:
    """Register every strategy class defined in *module*. True if any matched."""
    found = False
    for obj in vars(module).values():
        if _looks_like_strategy(obj, full_name):
            try:
                register(obj)
                found = True
            except Exception:  # noqa: BLE001 - isolate one bad strategy
                logger.exception(
                    "Failed to re-register strategy '%s' from module '%s'",
                    getattr(obj, "id", "?"),
                    full_name,
                )
    return found


def _recover_from_cached_modules(strategies_pkg) -> None:
    """Rebuild the registry by scanning reachable ``strategies.*`` namespaces.

    Called when the registry is missing strategies that were already imported
    under a previous incarnation of this registry module -- the Streamlit
    hot-reload desync, in either its empty or partial shape. Rather than
    ``importlib.reload`` each submodule (which re-executes its full import chain
    and can fail for a strategy with heavy transitive dependencies), we find the
    already-constructed strategy class sitting in each module's namespace and
    register it directly. Nothing is re-executed, so recovery cannot be broken by
    a dependency module being momentarily half-reloaded.

    Strategy classes are matched by :func:`_looks_like_strategy` (structural
    duck-typing), **not** ``issubclass``, so a reload of ``core.strategy`` that
    swaps out the ``BaseStrategy`` identity can no longer hide them.
    """
    for full_name, module in _iter_strategy_modules(strategies_pkg):
        _register_from_module(module, full_name)


def _reimport_strategy_module(strategies_pkg, name: str) -> bool:
    """Force ``strategies.<name>`` to execute so its ``@register`` fires here.

    Used only as a last resort, when no reachable module namespace contained the
    requested strategy. A module cached in ``sys.modules`` is *reloaded*, because
    a plain import of a cached module is a no-op and would never re-run the
    registration side effect against the current registry.
    """
    full_name = f"{strategies_pkg.__name__}.{name}"
    try:
        module = sys.modules.get(full_name)
        if module is None:
            importlib.import_module(full_name)
        else:
            importlib.reload(module)
        return True
    except Exception:  # noqa: BLE001 - isolate one bad strategy
        logger.exception("Failed to (re)import strategy module '%s'", full_name)
        return False


def _repair_missing(strategy_id: str) -> Optional[Type[BaseStrategy]]:
    """Targeted recovery for a strategy id that is absent from the registry.

    This is the backstop that turns the transient ``Unknown strategy '...'``
    startup crash into a non-event: whatever shape the torn import state has, we
    keep escalating until the strategy is registered or genuinely unavailable.

    1. Re-scan every reachable strategy module namespace (cheap, no execution).
    2. Re-execute the module most likely to define it -- by convention a strategy
       lives in ``strategies.<id>`` -- then any other module not yet represented.
    """
    global _LOADED
    _LOADED = False
    pkg = sys.modules.get("strategies")
    if pkg is None:
        try:
            pkg = importlib.import_module("strategies")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to import strategies package during repair")
            return None

    _recover_from_cached_modules(pkg)
    cls = _REGISTRY.get(strategy_id)
    if cls is not None:
        return cls

    registered_modules = {getattr(c, "__module__", None) for c in _REGISTRY.values()}
    prefix = f"{pkg.__name__}."
    names = _strategy_module_names(pkg)
    # The module named after the id first, then any module with nothing
    # registered from it yet.
    candidates = [name for name in names if name == strategy_id]
    candidates += [
        name
        for name in names
        if name != strategy_id and f"{prefix}{name}" not in registered_modules
    ]
    for name in candidates:
        if _reimport_strategy_module(pkg, name):
            cls = _REGISTRY.get(strategy_id)
            if cls is not None:
                logger.warning(
                    "Recovered strategy '%s' by re-importing '%s%s' after a torn "
                    "import state (dev reloader)",
                    strategy_id,
                    prefix,
                    name,
                )
                return cls
    return None


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
        # Never report a strategy as unknown on the strength of a possibly torn
        # import state -- escalate through recovery first.
        cls = _repair_missing(strategy_id)
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
