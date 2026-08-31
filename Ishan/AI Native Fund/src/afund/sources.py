"""Loader for config/sources.yaml — the external source registry.

Every pipeline must read its URL/config through this module rather than
hardcoding URLs. Kept separate from afund.config (settings.yaml) since the
two files serve different purposes (runtime settings vs. external source
registry).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from afund.config import REPO_ROOT

SOURCES_PATH = REPO_ROOT / "config" / "sources.yaml"


def load_sources(path: Path | None = None) -> dict[str, Any]:
    """Load config/sources.yaml as a plain dict."""
    sources_path = path or SOURCES_PATH
    with open(sources_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_source(group: str, name: str, path: Path | None = None) -> dict[str, Any]:
    """Fetch a single source entry, e.g. get_source('rss_feeds', 'cnbctv18_markets')."""
    sources = load_sources(path)
    try:
        return sources[group][name]
    except KeyError as exc:
        raise KeyError(f"No source '{name}' under group '{group}' in sources.yaml") from exc


def update_verify_status(
    group: str, name: str, status: str, new_url: str | None = None, path: Path | None = None
) -> None:
    """Update verify_status (and optionally the url) for one source entry in-place.

    Uses a targeted line-based rewrite (not a full YAML re-dump) so the
    hand-written comments and formatting in config/sources.yaml survive.
    Only the specific entry's `url:` / `verify_status:` lines are touched.
    """
    import re

    sources_path = path or SOURCES_PATH
    data = load_sources(sources_path)
    if group not in data or name not in data[group]:
        raise KeyError(f"No source '{name}' under group '{group}' in sources.yaml")

    lines = sources_path.read_text(encoding="utf-8").splitlines(keepends=True)

    # Find the block: a line matching r'^  {name}:' starts it; the block ends
    # at the next line with the same or lower indentation that also matches a
    # key pattern (i.e. next entry or next top-level group), or EOF.
    entry_header = re.compile(rf"^  {re.escape(name)}:\s*$")
    start = None
    for i, line in enumerate(lines):
        if entry_header.match(line):
            start = i
            break
    if start is None:
        raise KeyError(f"Could not locate entry block for '{name}' in {sources_path}")

    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i]
        if stripped.strip() == "":
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        if indent <= 2:  # back to top-level group or next sibling entry
            end = i
            break

    block = lines[start:end]
    new_block = []
    url_done = new_url is None
    status_done = False
    for line in block:
        if new_url is not None and re.match(r"^    url:\s*", line):
            new_block.append(f'    url: "{new_url}"\n')
            url_done = True
            continue
        if re.match(r"^    verify_status:\s*", line):
            new_block.append(f"    verify_status: {status}\n")
            status_done = True
            continue
        new_block.append(line)

    if not status_done:
        new_block.append(f"    verify_status: {status}\n")
    if new_url is not None and not url_done:
        new_block.append(f'    url: "{new_url}"\n')

    lines[start:end] = new_block
    sources_path.write_text("".join(lines), encoding="utf-8")
