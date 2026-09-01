"""Kronos foundation-model forecasting integration.

Optional add-on: consuming the actual model requires ``torch`` + the cloned
Kronos repo (see ``kronos/README.md``). The pure signal-derivation layer
(:func:`kronos.signals.derive_signal`) has no such dependency and is safe to
import anywhere.
"""

from __future__ import annotations

from .config import KronosConfig
from .signals import KronosSignal, derive_signal, signals_to_frame

__all__ = [
    "KronosConfig",
    "KronosSignal",
    "derive_signal",
    "signals_to_frame",
]
