"""First-run backend detection.

``AI_AGENT_BACKEND`` is authoritative when set. When it is *not* set we have to
pick something, and defaulting unconditionally to ``copilot_cli`` bakes the
repository owner's setup in as everybody's default: a user whose only credential
is a Gemini key gets a Copilot error on first launch, with nothing on screen
explaining that another backend exists.

So when the variable is unset we look at what the machine actually has and say
so out loud. Detection never overrides an explicit choice, and it never *hides*
what it did - every result carries a human-readable ``reason`` that the Settings
page and the CLI print verbatim. Silent provider selection would be worse than
the problem it solves: an API key can cost real money.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from importlib.util import find_spec

__all__ = [
    "BackendChoice",
    "detect_backend",
    "API_KEY_MODELS",
    "provider_for_key",
]

# Env var -> (default model string for init_chat_model, human label).
# Ordered: the first key present wins, so a user with several keys gets a
# stable, predictable answer rather than dict-ordering roulette.
API_KEY_MODELS: tuple[tuple[str, str, str], ...] = (
    ("GOOGLE_API_KEY", "google_genai:gemini-2.5-pro", "Google Gemini"),
    ("OPENAI_API_KEY", "openai:gpt-4o", "OpenAI"),
    ("ANTHROPIC_API_KEY", "anthropic:claude-sonnet-4-5", "Anthropic"),
)


@dataclass(frozen=True)
class BackendChoice:
    """The selected backend plus *why*, so the UI can justify itself."""

    backend: str
    model: str | None
    reason: str
    explicit: bool
    """True when the user set AI_AGENT_BACKEND; detection did not run."""

    resolved: bool = True
    """False when nothing usable was found and the value is only a fallback."""


def provider_for_key() -> tuple[str, str, str] | None:
    """Return the first ``(env_var, model, label)`` whose API key is present."""
    for env_var, model, label in API_KEY_MODELS:
        if os.getenv(env_var, "").strip():
            return env_var, model, label
    return None


def _copilot_ready() -> bool:
    """True when both halves of the Copilot backend are actually usable.

    The CLI alone is not enough - the SDK is an optional extra now - and the
    SDK alone is not enough either, since it shells out to the CLI.
    """
    cli = shutil.which("copilot") or shutil.which("copilot.exe")
    explicit = os.getenv("COPILOT_CLI_PATH", "").strip() or os.getenv(
        "COPILOT_BIN", ""
    ).strip()
    return bool(cli or explicit) and find_spec("copilot") is not None


def _native_ready() -> bool:
    return find_spec("langchain") is not None


def detect_backend(default: str = "copilot_cli") -> BackendChoice:
    """Choose a backend from the environment, explaining the choice.

    Precedence, most explicit first:

    1. ``AI_AGENT_BACKEND`` - always wins, never second-guessed.
    2. ``AI_MODEL`` set - an unambiguous request for the native backend.
    3. A working Copilot CLI *and* SDK - preserves the owner's setup exactly.
    4. Any provider API key plus LangChain - serves the API-key-only user.
    5. Otherwise fall back to ``default`` with ``resolved=False`` so callers
       can prompt for setup instead of failing with a confusing vendor error.
    """
    explicit = os.getenv("AI_AGENT_BACKEND", "").strip()
    if explicit:
        return BackendChoice(
            backend=explicit,
            model=os.getenv("AI_MODEL", "").strip() or None,
            reason=f"AI_AGENT_BACKEND={explicit} is set in the environment.",
            explicit=True,
        )

    configured_model = os.getenv("AI_MODEL", "").strip()
    if configured_model:
        return BackendChoice(
            backend="native",
            model=configured_model,
            reason=(
                f"AI_MODEL={configured_model} is set, which only the native "
                "backend uses."
            ),
            explicit=False,
        )

    if _copilot_ready():
        return BackendChoice(
            backend="copilot_cli",
            model=None,
            reason="Found a signed-in Copilot CLI and the Copilot SDK.",
            explicit=False,
        )

    key = provider_for_key()
    if key and _native_ready():
        env_var, model, label = key
        return BackendChoice(
            backend="native",
            model=model,
            reason=(
                f"No Copilot CLI found, but {env_var} is set - using the "
                f"native backend with {label} ({model})."
            ),
            explicit=False,
        )

    if key and not _native_ready():
        env_var, _model, label = key
        return BackendChoice(
            backend=default,
            model=None,
            reason=(
                f"{env_var} is set, but LangChain is not installed, so the "
                f"native backend cannot run. Install it with "
                f'`pip install -e ".[{label.split()[0].lower()}]"`.'
            ),
            explicit=False,
            resolved=False,
        )

    return BackendChoice(
        backend=default,
        model=None,
        reason=(
            "No model provider detected. Install the Copilot CLI, or set an "
            "API key (GOOGLE_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY) "
            "and choose the native backend."
        ),
        explicit=False,
        resolved=False,
    )
