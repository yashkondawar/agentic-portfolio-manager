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

from core.agent.types import (
    AgentRequest,
    AgentResult,
    Capability,
    OutputSink,
)

logger = logging.getLogger("core.agent.native")

__all__ = ["NativeRunner", "DEFAULT_MAX_TURNS"]

#: Safety valve on the tool-calling loop. Research prompts here fan out over
#: ~10 scraper tools across a shortlist, so this needs headroom, but an
#: unbounded loop on a paid API is a bill nobody wants.
DEFAULT_MAX_TURNS = 25

_MISSING_DEPS_HINT = (
    "The 'native' agent backend needs LangChain plus a provider package.\n"
    "  pip install -e '.[native]'          # core deps\n"
    "then ONE provider package, matching AI_MODEL:\n"
    "  pip install langchain-google-genai  # AI_MODEL=google_genai:gemini-2.5-pro\n"
    "  pip install langchain-openai        # AI_MODEL=openai:gpt-4o\n"
    "  pip install langchain-anthropic     # AI_MODEL=anthropic:claude-sonnet-4-5\n"
)


def _default_model() -> str:
    model = (
        os.getenv("AI_MODEL")
        or os.getenv("NATIVE_MODEL")
        or ""
    ).strip()
    if not model:
        raise RuntimeError(
            "AI_MODEL is not set. The 'native' backend needs an explicit model, "
            "e.g. AI_MODEL=google_genai:gemini-2.5-pro or AI_MODEL=openai:gpt-4o.\n"
            "There is no sensible default because the model determines which "
            "API key is required."
        )
    return model


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
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            ToolMessage,
        )

        tools = await self._load_tools(request)
        model: Any = init_chat_model(model_id)
        if tools:
            model = model.bind_tools(tools)
        by_name = {t.name: t for t in tools}

        # The prompt is passed inline. The Copilot CLI's write-to-file dance is
        # a command-line length workaround and has no place here.
        messages: list[Any] = [HumanMessage(content=request.prompt)]

        max_turns = int(os.getenv("AI_MAX_TURNS", DEFAULT_MAX_TURNS))
        final = ""

        for turn in range(max_turns):
            response: AIMessage = await model.ainvoke(messages)
            messages.append(response)

            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                final = self._text_of(response)
                emit(final)
                break

            logger.info(
                "turn %d/%d: model requested %d tool call(s): %s",
                turn + 1,
                max_turns,
                len(tool_calls),
                ", ".join(c.get("name", "?") for c in tool_calls),
            )
            for call in tool_calls:
                messages.append(
                    ToolMessage(
                        content=await self._invoke_tool(by_name, call),
                        tool_call_id=call.get("id", ""),
                    )
                )
        else:
            raise RuntimeError(
                f"Native agent hit the {max_turns}-turn limit without producing a "
                f"final answer. Raise AI_MAX_TURNS if this is a genuinely large "
                f"research run."
            )

        if not final.strip():
            raise RuntimeError("Native agent returned an empty response.")
        return final

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

    @staticmethod
    async def _invoke_tool(by_name: dict[str, Any], call: dict) -> str:
        """Run one tool call, converting failures into text the model can read.

        A raised exception would abort the whole research run; handing the
        error back as a tool result lets the model route around a single dead
        scraper, which is the behaviour the vendor harnesses have.
        """
        name = call.get("name", "")
        tool = by_name.get(name)
        if tool is None:
            return f"Tool {name!r} is not available."
        try:
            result = await tool.ainvoke(call.get("args", {}))
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP tool %s failed: %s", name, exc)
            return f"Tool {name!r} failed: {exc}"
        return result if isinstance(result, str) else str(result)

    @staticmethod
    def _text_of(message: Any) -> str:
        """Flatten a chat message's content to text.

        Anthropic-style models return a list of content blocks rather than a
        string, so a bare ``str(content)`` would leak Python repr into reports.
        """
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "".join(parts)
        return str(content)
