"""A provider-neutral tool-calling loop over LangChain chat models.

Extracted from :class:`~core.agent.runners.native.NativeRunner` so it can serve
two callers with different tool sources:

* the native runner, whose tools come from stdio MCP servers, and
* :mod:`main`, whose sequential stages pass **in-process** LangChain tools.

Both need identical turn-limit, error-tolerance and content-flattening
behaviour, and duplicating that would guarantee the two drift apart.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Sequence

logger = logging.getLogger("core.agent.loop")

__all__ = ["run_tool_loop", "invoke_tool", "text_of", "DEFAULT_MAX_TURNS"]

DEFAULT_MAX_TURNS = 25


def text_of(message: Any) -> str:
    """Flatten a chat message's content to text.

    Anthropic-style models return a list of content blocks rather than a
    string, so a bare ``str(content)`` would leak a Python repr into a report.
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


async def invoke_tool(by_name: dict[str, Any], call: dict) -> str:
    """Run one tool call, converting failures into text the model can read.

    A raised exception would abort the whole research run; handing the error
    back as a tool result lets the model route around a single dead scraper,
    which is the behaviour the vendor harnesses have.
    """
    name = call.get("name", "")
    tool = by_name.get(name)
    if tool is None:
        return f"Tool {name!r} is not available."
    try:
        result = await tool.ainvoke(call.get("args", {}))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tool %s failed: %s", name, exc)
        return f"Tool {name!r} failed: {exc}"
    return result if isinstance(result, str) else str(result)


async def run_tool_loop(
    *,
    model: Any,
    tools: Sequence[Any],
    prompt: str,
    emit: Callable[[str], Any] | None = None,
    max_turns: int | None = None,
) -> str:
    """Drive ``model`` until it answers without requesting another tool.

    Args:
        model: A LangChain chat model. Bound to ``tools`` here, so callers pass
            an unbound model.
        tools: LangChain tools, from MCP or in-process — the loop cannot tell.
        prompt: The complete prompt for this turn.
        emit: Optional sink for the final text.
        max_turns: Overrides ``AI_MAX_TURNS``.

    Raises:
        RuntimeError: if the turn limit is reached with no final answer, or the
            model returns an empty response. Both are failures worth surfacing
            rather than returning an empty report.
    """
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    bound = model.bind_tools(tools) if tools else model
    by_name = {t.name: t for t in tools}
    messages: list[Any] = [HumanMessage(content=prompt)]

    limit = max_turns or int(os.getenv("AI_MAX_TURNS", DEFAULT_MAX_TURNS))
    final = ""

    for turn in range(limit):
        response: AIMessage = await bound.ainvoke(messages)
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            final = text_of(response)
            if emit:
                emit(final)
            break

        logger.info(
            "turn %d/%d: model requested %d tool call(s): %s",
            turn + 1,
            limit,
            len(tool_calls),
            ", ".join(c.get("name", "?") for c in tool_calls),
        )
        for call in tool_calls:
            messages.append(
                ToolMessage(
                    content=await invoke_tool(by_name, call),
                    tool_call_id=call.get("id", ""),
                )
            )
    else:
        raise RuntimeError(
            f"Agent hit the {limit}-turn limit without producing a final "
            f"answer. Raise AI_MAX_TURNS if this is a genuinely large "
            f"research run."
        )

    if not final.strip():
        raise RuntimeError("Agent returned an empty response.")
    return final
