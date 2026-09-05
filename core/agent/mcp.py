"""The scraper MCP server, described once, provider-neutrally.

Previously ``_write_scraper_mcp_config`` was copy-pasted into
``swing_trading_copilot`` and ``portfolio_copilot_analysis``, with
``watchlist_curator`` and ``qtr_results.copilot_runner`` importing one of the
copies. It also baked in the Copilot CLI's JSON config format, which meant the
tool wiring was only usable from one harness.

Here it is a plain :class:`McpServerSpec`. Each backend renders it into its own
format, so the same ten scraper tools reach Copilot, Claude Code and the native
LangChain runner without duplication.
"""

from __future__ import annotations

import sys
from pathlib import Path

from core.agent.types import McpServerSpec

__all__ = ["SCRAPER_MCP_SERVER_NAME", "scraper_mcp", "scraper_server_path"]

SCRAPER_MCP_SERVER_NAME = "indian-stock-data"


def _repo_root() -> Path:
    # core/agent/mcp.py -> core/agent -> core -> repo root
    return Path(__file__).resolve().parents[2]


def scraper_server_path() -> Path:
    """Absolute path to ``mcp_server.py``.

    Raises:
        FileNotFoundError: if the server script is missing. Callers treat this
            as "run without scraper tools" rather than a hard failure, matching
            the previous behaviour.
    """
    server_script = _repo_root() / "mcp_server.py"
    if not server_script.exists():
        raise FileNotFoundError(
            f"Scraper MCP server not found at {server_script}. "
            "Disable with --no-scraper-tools or fix the path."
        )
    return server_script


def scraper_mcp() -> dict[str, McpServerSpec]:
    """The scraper MCP server, ready to hand to any backend."""
    server_script = scraper_server_path()
    repo_root = _repo_root()
    return {
        SCRAPER_MCP_SERVER_NAME: McpServerSpec(
            command=sys.executable,
            args=[str(server_script)],
            cwd=str(repo_root),
            tools=["*"],
        )
    }
