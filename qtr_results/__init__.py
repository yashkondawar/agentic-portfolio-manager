"""Quarterly-results momentum strategy engine.

Targets short-term (~2-3 week) price appreciation in stocks that have just
posted strong QoQ / YoY quarterly results. The public entry point is
:func:`qtr_results.engine.run`; the registered strategy wrapper lives in
``strategies/qtr_results.py``.
"""

from __future__ import annotations

__all__ = ["run"]


def run(*args, **kwargs):  # pragma: no cover - thin re-export
    from qtr_results.engine import run as _run

    return _run(*args, **kwargs)
