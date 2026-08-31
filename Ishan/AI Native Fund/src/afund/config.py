"""Lightweight settings loader for config/settings.yaml.

Kept dependency-free (stdlib + PyYAML only) so it can be imported early,
including from scripts/init_db.py before the rest of the package is needed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_ROOT / "config" / "settings.yaml"


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Load config/settings.yaml as a plain dict."""
    settings_path = path or SETTINGS_PATH
    with open(settings_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_db_path() -> Path:
    """Resolve the configured db_path relative to the repo root."""
    settings = load_settings()
    db_path = Path(settings.get("db_path", "data/afund.db"))
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    return db_path
