"""Configuration for the Kronos forecasting integration.

Thin, dependency-free wrappers around environment variables plus the default
values used by the Kronos service and strategy. Mirrors the style of
:mod:`core.config` so all Kronos knobs live in one place.

Kronos is **optional**: the heavy ``torch`` dependency and the model weights are
not required to import the rest of the app. Everything here is plain data so it
can be imported without ``torch`` installed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:  # Reuse the app's .env loading if available.
    from core.config import env, env_bool
except Exception:  # pragma: no cover - standalone fallback

    def env(name: str, default: Optional[str] = None) -> Optional[str]:
        return os.getenv(name, default)

    def env_bool(name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in ("1", "true", "yes", "y", "on")


# ── Model zoo (Hugging Face) ────────────────────────────────────────────────
# CPU-friendly defaults. Kronos-small (24.7M) is the recommended starting point
# for zero-shot CPU inference; bump to Kronos-base for a bit more capacity.
DEFAULT_MODEL: str = env("KRONOS_MODEL", "NeoQuasar/Kronos-small") or "NeoQuasar/Kronos-small"
DEFAULT_TOKENIZER: str = (
    env("KRONOS_TOKENIZER", "NeoQuasar/Kronos-Tokenizer-base")
    or "NeoQuasar/Kronos-Tokenizer-base"
)

# ── Inference defaults ──────────────────────────────────────────────────────
# max_context 512 is the hard limit for small/base. Keep lookback <= this.
DEFAULT_MAX_CONTEXT: int = int(env("KRONOS_MAX_CONTEXT", "512") or 512)
DEFAULT_DEVICE: str = env("KRONOS_DEVICE", "cpu") or "cpu"
DEFAULT_LOOKBACK: int = int(env("KRONOS_LOOKBACK", "400") or 400)
DEFAULT_PRED_LEN: int = int(env("KRONOS_PRED_LEN", "10") or 10)
# Number of stochastic forecast paths to sample to build a distribution.
# More paths = better P(up)/volatility estimates but linearly more CPU time.
DEFAULT_SAMPLE_PATHS: int = int(env("KRONOS_SAMPLE_PATHS", "20") or 20)
DEFAULT_TEMPERATURE: float = float(env("KRONOS_TEMPERATURE", "1.0") or 1.0)
DEFAULT_TOP_P: float = float(env("KRONOS_TOP_P", "0.9") or 0.9)

# ── Where the Kronos model code lives ───────────────────────────────────────
# Kronos is not on PyPI: you clone https://github.com/shiyu-coder/Kronos and
# point this at the checkout so ``from model import Kronos, ...`` resolves.
# Leave unset if you have made the ``model`` package importable another way.
def _discover_repo_path() -> Optional[str]:
    """Resolve the Kronos checkout: explicit env var first, else probe common spots.

    Auto-discovery keeps the PoC working out-of-the-box after a standard clone,
    without forcing the user to export an env var in every shell.
    """
    explicit = env("KRONOS_REPO_PATH")
    if explicit:
        return explicit
    candidates = [
        os.path.join("C:\\", "tools", "Kronos"),
        os.path.join(os.path.expanduser("~"), "Kronos"),
        os.path.join(os.path.expanduser("~"), "tools", "Kronos"),
        os.path.abspath(os.path.join(os.getcwd(), "Kronos")),
        os.path.abspath(os.path.join(os.getcwd(), "..", "Kronos")),
    ]
    for path in candidates:
        if os.path.isfile(os.path.join(path, "model", "__init__.py")):
            return path
    return None


KRONOS_REPO_PATH: Optional[str] = _discover_repo_path()


@dataclass(frozen=True)
class KronosConfig:
    """Resolved settings for one forecasting run."""

    model: str = DEFAULT_MODEL
    tokenizer: str = DEFAULT_TOKENIZER
    device: str = DEFAULT_DEVICE
    max_context: int = DEFAULT_MAX_CONTEXT
    lookback: int = DEFAULT_LOOKBACK
    pred_len: int = DEFAULT_PRED_LEN
    sample_paths: int = DEFAULT_SAMPLE_PATHS
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    repo_path: Optional[str] = KRONOS_REPO_PATH

    def clamped_lookback(self) -> int:
        """Never exceed the model's context window."""
        return max(1, min(self.lookback, self.max_context))


__all__ = [
    "KronosConfig",
    "DEFAULT_MODEL",
    "DEFAULT_TOKENIZER",
    "DEFAULT_MAX_CONTEXT",
    "DEFAULT_DEVICE",
    "DEFAULT_LOOKBACK",
    "DEFAULT_PRED_LEN",
    "DEFAULT_SAMPLE_PATHS",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TOP_P",
    "KRONOS_REPO_PATH",
    "env",
    "env_bool",
]
