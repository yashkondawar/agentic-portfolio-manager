"""Persisting agent-backend settings chosen in the UI.

The Settings page previously wrote to ``os.environ`` only, so every choice was
lost when the app restarted — fine for the repository owner, whose defaults
already worked, and useless for anyone who had to configure a provider before
they could run anything at all.

Writes go to ``.env`` (git-ignored) via ``dotenv.set_key``, which updates keys
in place and leaves surrounding comments intact, and to ``os.environ`` so the
change takes effect without a restart.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import set_key

__all__ = ["env_file", "persist_settings", "MANAGED_KEYS"]

# Keys the Settings page owns. Anything not listed here is never touched, so
# hand-edited .env entries survive a save.
MANAGED_KEYS = (
    "AI_AGENT_BACKEND",
    "AI_MODEL",
    "AI_MAX_TURNS",
    "COPILOT_MODEL",
    "WEB_GROUNDING",
    "USE_FREE_SCRAPER",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


def env_file() -> Path:
    """Return the repository ``.env`` path, creating an empty file if needed.

    ``set_key`` cannot write to a file that does not exist, and a fresh clone
    has only ``example.env``.
    """
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.exists():
        path.write_text(
            "# Created by the Settings page. See example.env for all options.\n",
            encoding="utf-8",
        )
    return path


def persist_settings(values: dict[str, str | None]) -> Path:
    """Write ``values`` to ``.env`` and the live process environment.

    A ``None`` or empty value clears the variable from the process without
    removing it from the file, so a user who blanks a field is not silently
    left with the previous value still active.

    Raises:
        ValueError: if a key outside :data:`MANAGED_KEYS` is supplied. This is
            deliberate: a settings form should never be able to write arbitrary
            environment variables into a file that holds credentials.
    """
    unknown = sorted(set(values) - set(MANAGED_KEYS))
    if unknown:
        raise ValueError(f"Refusing to persist unmanaged keys: {', '.join(unknown)}")

    path = env_file()
    for key, raw in values.items():
        value = (raw or "").strip()
        if value:
            set_key(str(path), key, value, quote_mode="never")
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
    return path
