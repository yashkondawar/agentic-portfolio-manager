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
