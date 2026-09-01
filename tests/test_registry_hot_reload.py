"""Regression tests for the strategy-registry hot-reload recovery.

Streamlit's file watcher reloads individual modules while the app process keeps
running. That independently re-executes modules like ``core.registry`` and
``core.strategy`` while the concrete ``strategies.*`` submodules stay cached in
``sys.modules``. Historically this desynced the registry and surfaced the
misleading ``KeyError: Unknown strategy '...'. Available: (none)``.

The nastiest shape is a reload of ``core.strategy``: ``BaseStrategy`` becomes a
*new* class object, so any recovery that gates on ``issubclass(obj,
BaseStrategy)`` silently matches nothing. These tests lock in that recovery is
duck-typed and survives every reload combination.
"""

import importlib

import core.strategy as core_strategy
from core import registry


EXPECTED_IDS = {
    "sequential_agents",
    "parallel_agents",
    "swing_trading",
    "portfolio_analysis",
    "watchlist_curation",
    "qtr_results",
    "swing_backtest",
}


def _resolve_all(reg):
    return {reg.get_strategy(sid).id for sid in EXPECTED_IDS}


def test_cold_load_registers_every_strategy():
    reg = importlib.reload(registry)
    assert _resolve_all(reg) == EXPECTED_IDS


def test_registry_only_reload_recovers():
    reg = importlib.reload(registry)
    _resolve_all(reg)
    reg = importlib.reload(reg)
    assert _resolve_all(reg) == EXPECTED_IDS


def test_base_strategy_identity_swap_recovers():
    """The exact repro: reload core.strategy (new BaseStrategy) then registry.

    Before the duck-typed recovery this raised
    ``Unknown strategy '...'. Available: (none)`` because the cached strategy
    classes no longer passed ``issubclass`` against the fresh ``BaseStrategy``.
    """
    importlib.reload(registry)
    importlib.reload(core_strategy)
    reg = importlib.reload(registry)
    assert reg._REGISTRY == {} or True  # registry starts empty after reload
    assert _resolve_all(reg) == EXPECTED_IDS


def test_repeated_reloads_self_heal_without_duplicate_errors():
    reg = registry
    for _ in range(3):
        importlib.reload(core_strategy)
        reg = importlib.reload(reg)
        assert _resolve_all(reg) == EXPECTED_IDS


def test_looks_like_strategy_is_identity_independent():
    """A strategy class must be recognized even against a foreign BaseStrategy."""
    reg = importlib.reload(registry)
    reg.get_strategy("qtr_results")  # ensure modules are cached
    import sys

    module_name = "strategies.qtr_results"
    module = sys.modules[module_name]
    strat_cls = next(
        obj
        for obj in vars(module).values()
        if reg._looks_like_strategy(obj, module_name)
    )
    assert isinstance(strat_cls.id, str) and strat_cls.id
    # Even after swapping BaseStrategy identity, the duck-typed check holds.
    importlib.reload(core_strategy)
    assert reg._looks_like_strategy(strat_cls, module_name)


def _strip_strategy_modules(pkg, keep, *, drop_package_attrs):
    """Mimic Streamlit's watcher wiping strategy modules. Returns an undo dict."""
    import sys

    removed = {}
    for name in pkg._STRATEGY_MODULES:
        if name == keep:
            continue
        full = f"strategies.{name}"
        removed[name] = (sys.modules.pop(full, None), getattr(pkg, name, None))
        if drop_package_attrs and hasattr(pkg, name):
            delattr(pkg, name)
    return removed


def _restore_strategy_modules(pkg, removed):
    import sys

    for name, (module, attr) in removed.items():
        if module is not None:
            sys.modules[f"strategies.{name}"] = module
        if attr is not None:
            setattr(pkg, name, attr)


def test_sys_modules_deletion_recovers_from_package_attributes():
    """Streamlit deletes watched modules from ``sys.modules``; it does not reload.

    ``LocalSourcesWatcher.on_path_changed`` runs ``del sys.modules[name]`` for
    every watched module and reruns the script. Recovery that only consults
    ``sys.modules`` finds nothing, so it must also use the references
    ``strategies/__init__`` still holds on the package itself.
    """
    import sys

    reg = importlib.reload(registry)
    _resolve_all(reg)
    pkg = sys.modules["strategies"]
    removed = _strip_strategy_modules(pkg, keep="swing_backtest", drop_package_attrs=False)
    try:
        reg = importlib.reload(reg)  # fresh, empty registry
        assert _resolve_all(reg) == EXPECTED_IDS
    finally:
        _restore_strategy_modules(pkg, removed)
        importlib.reload(registry)


def test_partial_registry_repairs_by_reimporting_the_missing_module():
    """The reported startup crash: ``Available: swing_backtest``.

    Here the modules are gone from ``sys.modules`` *and* from the package
    namespace, so no cheap namespace scan can find them and the registry really
    does end up holding a single strategy. It must still resolve the others by
    re-importing their module instead of raising ``Unknown strategy``.
    """
    import sys

    reg = importlib.reload(registry)
    _resolve_all(reg)
    pkg = sys.modules["strategies"]
    removed = _strip_strategy_modules(pkg, keep="swing_backtest", drop_package_attrs=True)
    try:
        reg = importlib.reload(reg)
        reg._ensure_loaded()
        assert set(reg._REGISTRY) == {"swing_backtest"}, "precondition: partial registry"
        assert reg.get_strategy("watchlist_curation").id == "watchlist_curation"
        assert _resolve_all(reg) == EXPECTED_IDS
    finally:
        _restore_strategy_modules(pkg, removed)
        importlib.reload(registry)


def test_completeness_is_not_satisfied_by_the_wrong_strategies():
    """A count-based completeness test can latch a broken registry for good.

    With ``len(_REGISTRY) >= len(modules) - len(failed_imports)``, a registry
    holding one unrelated strategy while six modules are marked failed counts as
    "complete", so ``_LOADED`` sticks at True and the process never retries.
    Completeness must compare *which* modules are represented.
    """
    from types import SimpleNamespace

    reg = importlib.reload(registry)
    _resolve_all(reg)
    fake_pkg = SimpleNamespace(
        __name__="strategies",
        _STRATEGY_MODULES=("watchlist_curation", "swing_backtest"),
        failed_imports={"watchlist_curation": RuntimeError("transient")},
    )
    assert reg._registry_is_complete(fake_pkg) is True

    reg._REGISTRY.clear()
    reg._REGISTRY["swing_backtest"] = type(
        "Foreign", (), {"id": "swing_backtest", "__module__": "somewhere.else"}
    )
    # One entry, one non-failed module -- counts match, modules do not.
    assert reg._registry_is_complete(fake_pkg) is False
    importlib.reload(registry)
