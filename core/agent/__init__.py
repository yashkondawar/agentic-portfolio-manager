"""Backend registry for the agent port.

Selection is a single environment variable::

    AI_AGENT_BACKEND = copilot_cli (default) | native | claude_code

Backends are imported lazily so that choosing one never requires the others'
dependencies to be installed — the whole point of the exercise is that a user
with only a Gemini key never has to install the Copilot CLI, and vice versa.
"""

from __future__ import annotations

import logging
from typing import Callable

from core.agent.detect import BackendChoice, detect_backend
from core.agent.mcp import SCRAPER_MCP_SERVER_NAME, scraper_mcp, scraper_server_path
from core.agent.types import (
    AgentRequest,
    AgentResult,
    AgentRunner,
    Capability,
    McpServerSpec,
    OutputSink,
    UnsupportedCapability,
)

logger = logging.getLogger("core.agent")

__all__ = [
    "AgentRequest",
    "AgentResult",
    "AgentRunner",
    "BackendChoice",
    "Capability",
    "McpServerSpec",
    "OutputSink",
    "UnsupportedCapability",
    "SCRAPER_MCP_SERVER_NAME",
    "scraper_mcp",
    "scraper_server_path",
    "detect_backend",
    "get_agent_runner",
    "available_backends",
    "run_agent",
    "DEFAULT_BACKEND",
]

DEFAULT_BACKEND = "copilot_cli"


def _load_copilot_cli() -> AgentRunner:
    from core.agent.runners.copilot_cli import CopilotCliRunner

    return CopilotCliRunner()


def _load_native() -> AgentRunner:
    from core.agent.runners.native import NativeRunner

    return NativeRunner()


def _load_claude_code() -> AgentRunner:
    from core.agent.runners.claude_code import ClaudeCodeRunner

    return ClaudeCodeRunner()


_REGISTRY: dict[str, Callable[[], AgentRunner]] = {
    "copilot_cli": _load_copilot_cli,
    "native": _load_native,
    "claude_code": _load_claude_code,
}


def available_backends() -> list[str]:
    return sorted(_REGISTRY)


def get_agent_runner(name: str | None = None) -> AgentRunner:
    """Return the configured agent backend.

    Args:
        name: Explicit backend name. Defaults to ``AI_AGENT_BACKEND``; when that
            is unset the environment is inspected (see :mod:`core.agent.detect`)
            so a user whose only credential is an API key gets a working default
            instead of a Copilot error. Detection is announced, never silent.
    """
    if name:
        chosen = name.strip()
    else:
        choice = detect_backend(DEFAULT_BACKEND)
        chosen = choice.backend
        if not choice.explicit:
            _announce(choice)

    loader = _REGISTRY.get(chosen)
    if loader is None:
        raise ValueError(
            f"Unknown agent backend {chosen!r}. "
            f"Valid options: {', '.join(available_backends())}."
        )
    return loader()


_announced = False


def _announce(choice: BackendChoice) -> None:
    """Log an auto-detected backend once per process.

    Choosing a provider on the user's behalf is only acceptable if we say so:
    an API key costs money, and a user who thinks they are on Copilot while
    actually burning Gemini quota has been badly served.
    """
    global _announced
    if _announced:
        return
    _announced = True
    level = logging.INFO if choice.resolved else logging.WARNING
    logger.log(
        level,
        "Agent backend auto-selected: %s. %s Set AI_AGENT_BACKEND to silence this.",
        choice.backend,
        choice.reason,
    )


def run_agent(
    request: AgentRequest,
    *,
    backend: str | None = None,
    on_output: OutputSink | None = None,
) -> AgentResult:
    """Run one agent turn, checking capabilities before spending any tokens.

    The capability check is the reason this wrapper exists. A backend without
    live web access must not quietly produce a swing-trade report that looks
    complete but was written with no current news in it — in a financial tool
    that is a correctness failure, not a degraded experience.
    """
    runner = get_agent_runner(backend)
    missing = request.missing_from(runner.capabilities)
    if missing:
        raise UnsupportedCapability(runner.name, missing)
    return runner.run(request, on_output=on_output)
