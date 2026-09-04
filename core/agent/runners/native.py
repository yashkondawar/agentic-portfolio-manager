"""The provider-agnostic backend: any chat model with tool calling, plus MCP.

This is the only backend that needs **no vendor CLI, no subscription and no
GitHub account** — just ``pip install`` and an API key. It is therefore the
path for anyone who has only an LLM API key, and the only one that runs in a
plain container or in CI.

Model selection uses LangChain's ``init_chat_model``, so the provider is a
string::

    AI_MODEL=google_genai:gemini-2.5-pro
    AI_MODEL=openai:gpt-4o
    AI_MODEL=anthropic:claude-sonnet-4-5
    AI_MODEL=ollama:llama3.1          # fully local, no API key at all

Why a hand-written loop rather than ``langgraph.prebuilt.create_react_agent``:
this backend exists to keep the dependency footprint minimal for someone who
has nothing installed, and ``langgraph`` is not currently a dependency. The
loop below is a plain tool-calling cycle over ``langchain-core`` primitives —
the same thing the prebuilt agent does for a single-turn research task, in
about sixty lines, with retry and turn-limit behaviour we control.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Sequence

from core.agent.loop import DEFAULT_MAX_TURNS
from core.agent.loop import invoke_tool as _loop_invoke_tool
from core.agent.loop import text_of as _loop_text_of
from core.agent.types import (
    AgentRequest,
    AgentResult,
    Capability,
    OutputSink,
)

logger = logging.getLogger("core.agent.native")

__all__ = ["NativeRunner", "DEFAULT_MAX_TURNS"]

_MISSING_DEPS_HINT = (
    "The 'native' agent backend needs LangChain plus a provider package.\n"
    "  pip install -e '.[native]'          # core deps\n"
    "then ONE provider package, matching AI_MODEL:\n"
    "  pip install langchain-google-genai  # AI_MODEL=google_genai:gemini-2.5-pro\n"
    "  pip install langchain-openai        # AI_MODEL=openai:gpt-4o\n"
    "  pip install langchain-anthropic     # AI_MODEL=anthropic:claude-sonnet-4-5\n"
)


def _default_model() -> str:
    """Resolve the model string for the native backend.

    ``AI_MODEL`` wins when set. Otherwise fall back to the model implied by
    whichever API key is present: someone whose only credential is a
    ``GOOGLE_API_KEY`` has already told us which provider they can reach, and
    making them restate it as ``AI_MODEL`` is a second setup step that buys
    nothing. The inference is announced by :func:`core.agent.detect.detect_backend`,
    so it is never silent.
    """
    model = (os.getenv("AI_MODEL") or os.getenv("NATIVE_MODEL") or "").strip()
    if model:
        return model

    from core.agent.detect import provider_for_key

    inferred = provider_for_key()
    if inferred:
        return inferred[1]

    raise RuntimeError(
        "No model provider is configured. The 'native' backend needs either an "
        "API key (GOOGLE_API_KEY, OPENAI_API_KEY or ANTHROPIC_API_KEY) or an "
        "explicit AI_MODEL, e.g. AI_MODEL=google_genai:gemini-2.5-pro.\n"
        "Set one in .env, or use the Settings page in the app."
    )


class NativeRunner:
    """Runs an :class:`AgentRequest` against any tool-calling chat model.

    Note the capability set deliberately omits :attr:`Capability.WEB_SEARCH`.
    Unlike the vendor CLIs there is no built-in web tool here, so a request
    that genuinely requires live browsing is rejected up front rather than
    answered from stale model knowledge.

    In practice this matters less than it sounds: ``mcp_server.py`` exposes
    ``fetch_stock_news``, ``scrape_url`` and eight other live-data tools, and
    those work identically here because they are just MCP. To close the
    remaining gap — open-ended discovery with no known URL — register a search
    MCP server (Tavily/Brave) as one more ``McpServerSpec``; it then works on
    every backend rather than only the two with a proprietary web tool.
    """

    name = "native"
    capabilities = frozenset({Capability.MCP_TOOLS, Capability.STREAMING})

    def run(
        self,
        request: AgentRequest,
        *,
        on_output: OutputSink | None = None,
    ) -> AgentResult:
        model_id = request.model or _default_model()
        emit = on_output or (lambda chunk: (sys.stdout.write(chunk), sys.stdout.flush()))

        try:
            text = asyncio.run(self._run_async(request, model_id, emit))
        except ImportError as exc:  # pragma: no cover - depends on user install
            raise RuntimeError(f"{_MISSING_DEPS_HINT}\nOriginal error: {exc}") from exc

        return AgentResult(text=text, backend=self.name, model=model_id)

    async def _run_async(
        self,
        request: AgentRequest,
        model_id: str,
        emit: OutputSink,
    ) -> str:
        from langchain.chat_models import init_chat_model

        from core.agent.loop import run_tool_loop

        tools = await self._load_tools(request)
        # The prompt is passed inline. The Copilot CLI's write-to-file dance is
        # a command-line length workaround and has no place here.
        return await run_tool_loop(
            model=init_chat_model(model_id),
            tools=tools,
            prompt=request.prompt,
            emit=emit,
        )

    async def _load_tools(self, request: AgentRequest) -> Sequence[Any]:
        """Render our provider-neutral MCP specs into LangChain tools."""
        if not request.mcp_servers:
            return []

        from langchain_mcp_adapters.client import MultiServerMCPClient

        connections = {
            name: {
                "transport": "stdio",
                "command": spec.command,
                "args": list(spec.args),
                **({"cwd": spec.cwd} if spec.cwd else {}),
            }
            for name, spec in request.mcp_servers.items()
        }
        client = MultiServerMCPClient(connections)
        tools = await client.get_tools()
        logger.info(
            "Loaded %d MCP tool(s) from %s",
            len(tools),
            ", ".join(connections),
        )
        return tools

    # Retained as thin aliases: the implementations now live in core.agent.loop
    # so main.py's sequential stages share exactly this behaviour.
    _invoke_tool = staticmethod(_loop_invoke_tool)
    _text_of = staticmethod(_loop_text_of)
