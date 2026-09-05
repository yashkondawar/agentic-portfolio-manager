"""Agent runner for the quarterly-results strategy.

All harness plumbing (subprocess/streaming/MCP wiring) now lives in
``core.agent``, so this module is just prompt hand-off. The backend is chosen
by ``AI_AGENT_BACKEND``.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.agent import AgentRequest, Capability, run_agent, scraper_mcp

logger = logging.getLogger("qtr_results.copilot")

__all__ = ["run_copilot"]

_QTR_HANDOFF = (
    "Read the file `{path}` in its entirety using your "
    "file-read tool. It contains your role, context and a request. Follow it "
    "exactly and respond with ONLY the final Markdown report, which MUST end "
    "with the required ```json``` block. Do not echo the prompt or narrate "
    "what you are doing."
)


def run_copilot(
    prompt_text: str,
    *,
    web_grounding: bool = True,
    scraper_tools: bool = True,
    model: Optional[str] = None,
) -> str:
    """Run the quarterly-results prompt on the configured backend."""
    mcp_servers: dict = {}
    if scraper_tools:
        try:
            mcp_servers = scraper_mcp()
        except FileNotFoundError as e:
            logger.warning("Skipping scraper tools: %s", e)

    request = AgentRequest(
        prompt=prompt_text,
        label="qtr",
        handoff_instruction=_QTR_HANDOFF,
        mcp_servers=mcp_servers,
        requires=frozenset({Capability.WEB_SEARCH}) if web_grounding else frozenset(),
        model=model,
    )
    logger.info("Quarterly-results run — %d prompt bytes", len(prompt_text))
    return run_agent(request).text
