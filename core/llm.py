"""GitHub Copilot SDK integration used by all model-backed workflows."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Sequence

from copilot import CopilotClient, RuntimeConnection
from copilot.client import StopError
from copilot.session import PermissionDecisionUserNotAvailable
from copilot.session_events import AssistantMessageData
from copilot.tools import Tool, ToolInvocation, ToolResult

logger = logging.getLogger(__name__)

DEFAULT_COPILOT_MODEL = "claude-opus-4.7"
DEFAULT_COPILOT_TIMEOUT = 300.0


class _IgnoreUnsupportedShutdown(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not record.exc_info:
            return True
        error = record.exc_info[1]
        return not (
            error is not None
            and "runtime.shutdown" in str(error)
            and "-32601" in str(error)
        )


logging.getLogger("copilot._jsonrpc").addFilter(_IgnoreUnsupportedShutdown())


class CopilotConfigurationError(RuntimeError):
    """Raised when the local Copilot SDK runtime cannot be used."""


@dataclass(frozen=True)
class CopilotResponse:
    """Minimal response contract consumed by the parallel analyst code."""

    content: str


def get_copilot_model() -> str:
    """Return the configured model, treating blank overrides as unset."""
    return os.getenv("COPILOT_MODEL", "").strip() or DEFAULT_COPILOT_MODEL


def get_copilot_timeout() -> float:
    """Return the per-agent response timeout in seconds."""
    raw_timeout = os.getenv("COPILOT_TIMEOUT", "").strip()
    if not raw_timeout:
        return DEFAULT_COPILOT_TIMEOUT
    try:
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise CopilotConfigurationError(
            "COPILOT_TIMEOUT must be a number of seconds."
        ) from exc
    if timeout <= 0:
        raise CopilotConfigurationError("COPILOT_TIMEOUT must be greater than zero.")
    return timeout


def validate_copilot_configuration() -> None:
    """Fail early when neither the CLI nor an explicit SDK runtime exists."""
    explicit_path = os.getenv("COPILOT_CLI_PATH", "").strip()
    if explicit_path and not Path(explicit_path).is_file():
        raise CopilotConfigurationError(
            f"COPILOT_CLI_PATH does not exist: {explicit_path}"
        )

    if explicit_path:
        return

    if shutil.which("copilot") or shutil.which("copilot.exe"):
        return

    # The SDK can download its pinned runtime, but it still needs an existing
    # Copilot login in the user's Copilot home.
    copilot_home = Path.home() / ".copilot"
    if not copilot_home.exists():
        raise CopilotConfigurationError(
            "GitHub Copilot is not configured. Install and sign in to Copilot "
            "CLI, then restart the app."
        )


def _runtime_connection() -> RuntimeConnection:
    explicit_path = os.getenv("COPILOT_CLI_PATH", "").strip()
    if explicit_path:
        return RuntimeConnection.for_stdio(path=explicit_path)

    # On Windows, prefer the signed system installation. Some application
    # control policies block the SDK's downloaded executable.
    if sys.platform == "win32":
        installed_exe = shutil.which("copilot.exe")
        if installed_exe:
            return RuntimeConnection.for_stdio(path=installed_exe)

    return RuntimeConnection.for_stdio()


async def _stop_client(client: CopilotClient) -> None:
    try:
        await client.stop()
    except ExceptionGroup as group:
        unexpected = [
            error for error in group.exceptions if not isinstance(error, StopError)
        ]
        if unexpected:
            raise ExceptionGroup(
                "Unexpected errors while stopping Copilot SDK", unexpected
            )
        logger.debug(
            "Copilot CLI does not support graceful runtime shutdown; "
            "the SDK terminated the owned process."
        )


@asynccontextmanager
async def copilot_client() -> AsyncIterator[CopilotClient]:
    """Start a Copilot SDK client using the authenticated local user."""
    validate_copilot_configuration()
    client = CopilotClient(
        connection=_runtime_connection(),
        working_directory=str(Path.cwd()),
        use_logged_in_user=True,
    )
    try:
        await client.start()
        yield client
    except PermissionError as exc:
        raise CopilotConfigurationError(
            "The Copilot SDK runtime could not start. Set COPILOT_CLI_PATH "
            "to an executable Copilot CLI installation."
        ) from exc
    finally:
        await _stop_client(client)


def _tool_schema(langchain_tool: Any) -> dict[str, Any]:
    args_schema = getattr(langchain_tool, "args_schema", None)
    if args_schema is not None and hasattr(args_schema, "model_json_schema"):
        return args_schema.model_json_schema()
    schema = getattr(langchain_tool, "args", None)
    if isinstance(schema, dict):
        return {
            "type": "object",
            "properties": schema,
            "required": list(schema),
        }
    return {"type": "object", "properties": {}}


def _tool_result_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except TypeError:
        return str(result)


def copilot_tools(langchain_tools: Iterable[Any]) -> list[Tool]:
    """Adapt LangChain tools to read-only Copilot SDK custom tools."""
    sdk_tools: list[Tool] = []
    for langchain_tool in langchain_tools:
        name = getattr(langchain_tool, "name", "")
        if not name:
            raise ValueError("Every Copilot tool must have a name.")

        async def handler(
            invocation: ToolInvocation,
            bound_tool: Any = langchain_tool,
        ) -> ToolResult:
            try:
                if hasattr(bound_tool, "ainvoke"):
                    result = await bound_tool.ainvoke(invocation.arguments)
                else:
                    result = await asyncio.to_thread(
                        bound_tool.invoke, invocation.arguments
                    )
            except Exception as exc:
                logger.exception(
                    "Copilot custom tool failed",
                    extra={"tool_name": getattr(bound_tool, "name", "unknown")},
                )
                return ToolResult(
                    text_result_for_llm=f"Tool failed: {exc}",
                    result_type="failure",
                    error=str(exc),
                )
            return ToolResult(
                text_result_for_llm=_tool_result_text(result),
                result_type="success",
            )

        sdk_tools.append(
            Tool(
                name=name,
                description=(
                    getattr(langchain_tool, "description", "")
                    or f"Run the {name} stock research tool."
                ),
                parameters=_tool_schema(langchain_tool),
                handler=handler,
                skip_permission=True,
                defer="never",
            )
        )
    return sdk_tools


async def run_copilot_prompt(
    prompt: str,
    *,
    client: CopilotClient | None = None,
    tools: Sequence[Any] = (),
    model: str | None = None,
    timeout: float | None = None,
) -> str:
    """Run one isolated Copilot agent prompt and return its final text."""
    sdk_tools = copilot_tools(tools)
    selected_model = model or get_copilot_model()
    response_timeout = timeout or get_copilot_timeout()

    async def invoke(active_client: CopilotClient) -> str:
        def deny_builtin_tools(request: Any, invocation: Any) -> Any:
            return PermissionDecisionUserNotAvailable()

        session = await active_client.create_session(
            model=selected_model,
            tools=sdk_tools,
            on_permission_request=deny_builtin_tools,
        )
        try:
            event = await session.send_and_wait(
                prompt,
                timeout=response_timeout,
            )
        finally:
            await active_client.delete_session(session.session_id)

        if event is None or not isinstance(event.data, AssistantMessageData):
            raise RuntimeError("Copilot completed without an assistant response.")
        content = event.data.content.strip()
        if not content:
            raise RuntimeError("Copilot returned an empty assistant response.")
        return content

    if client is not None:
        return await invoke(client)

    async with copilot_client() as managed_client:
        return await invoke(managed_client)


def _format_messages(messages: Any) -> str:
    if isinstance(messages, str):
        return messages
    if not isinstance(messages, Sequence):
        return str(messages)

    formatted: list[str] = []
    for message in messages:
        if isinstance(message, dict):
            role = str(message.get("role", "user")).upper()
            content = message.get("content", "")
        else:
            message_type = getattr(message, "type", None)
            role = str(message_type or message.__class__.__name__).upper()
            content = getattr(message, "content", str(message))
        formatted.append(f"{role}:\n{content}")
    return "\n\n".join(formatted)


class CopilotLLM:
    """Synchronous adapter for parallel analysts that call ``llm.invoke``."""

    def __init__(
        self,
        *,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        validate_copilot_configuration()
        self.model = model or get_copilot_model()
        self.timeout = timeout or get_copilot_timeout()

    def invoke(self, messages: Any) -> CopilotResponse:
        content = asyncio.run(
            run_copilot_prompt(
                _format_messages(messages),
                model=self.model,
                timeout=self.timeout,
            )
        )
        return CopilotResponse(content=content)


def get_llm(temperature: float | None = None) -> CopilotLLM:
    """Return the repository's GitHub Copilot SDK model adapter."""
    if temperature is not None:
        logger.debug("Copilot SDK ignores temperature; model behavior is host-managed.")
    return CopilotLLM()


__all__ = [
    "CopilotConfigurationError",
    "CopilotLLM",
    "CopilotResponse",
    "DEFAULT_COPILOT_MODEL",
    "copilot_client",
    "copilot_tools",
    "get_copilot_model",
    "get_llm",
    "run_copilot_prompt",
    "validate_copilot_configuration",
]
