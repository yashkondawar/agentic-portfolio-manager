"""Provider-neutral contract for running one agent turn.

The strategies in this repo do not implement an agent loop — they build a
prompt and hand it to a harness that owns the loop (the Copilot CLI today).
This module defines the narrow port between the two so the harness can be
swapped without touching any strategy logic.

Three ideas, and nothing else:

``McpServerSpec``
    How to launch a stdio MCP server. MCP is a standard, so the *same* spec
    renders natively into every backend — Copilot's ``--additional-mcp-config``
    JSON, the Claude Agent SDK's ``mcp_servers=`` dict, and
    ``langchain-mcp-adapters``. This is what makes the abstraction honest
    rather than lowest-common-denominator.

``AgentRequest`` / ``AgentResult``
    Text in, text out, plus the provenance needed to tell two runs apart.

``AgentRunner``
    The protocol each backend implements.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:  # pragma: no cover - Python 3.10 fallback
    from enum import Enum

    class StrEnum(str, Enum):
        def __str__(self) -> str:  # pragma: no cover - trivial
            return str(self.value)


__all__ = [
    "Capability",
    "McpServerSpec",
    "AgentRequest",
    "AgentResult",
    "AgentRunner",
    "UnsupportedCapability",
    "OutputSink",
]

#: Callback used to stream incremental output to the console.
OutputSink = Callable[[str], None]


class Capability(StrEnum):
    """A feature a request may require and a backend may provide."""

    #: The harness can fetch arbitrary live URLs on its own initiative.
    #: Note this is *not* the same as our scraper MCP server's ``scrape_url``
    #: tool, which is available on every backend because it is just MCP.
    WEB_SEARCH = "web_search"
    #: The harness can host stdio MCP servers.
    MCP_TOOLS = "mcp_tools"
    #: The harness emits output incrementally rather than only at the end.
    STREAMING = "streaming"


class UnsupportedCapability(RuntimeError):
    """Raised when a backend cannot satisfy everything a request requires.

    Deliberately raised *before* the model is invoked. Silently degrading a
    swing-trade report to one with no live news is a correctness problem in a
    financial tool, so we fail loudly instead.
    """

    def __init__(self, backend: str, missing: frozenset[Capability]) -> None:
        names = ", ".join(sorted(str(c) for c in missing))
        super().__init__(
            f"Agent backend {backend!r} cannot provide: {names}.\n"
            f"Either pick a backend that can (set AI_AGENT_BACKEND), or turn the "
            f"corresponding feature off for this run."
        )
        self.backend = backend
        self.missing = missing


@dataclass(frozen=True)
class McpServerSpec:
    """How to launch one stdio MCP server."""

    command: str
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    #: Tool allow-list; ``["*"]`` means every tool the server exposes.
    tools: list[str] = field(default_factory=lambda: ["*"])


@dataclass(frozen=True)
class AgentRequest:
    """One agent turn, described without reference to any provider."""

    #: The complete prompt. Backends decide how to deliver it — inline, or
    #: written to a file and referenced (see ``handoff_instruction``).
    prompt: str

    #: Short slug used for temp-file and log naming, e.g. ``"swing"``.
    label: str = "agent"

    #: Instruction used *only* by backends that hand the prompt over as a file
    #: rather than inline, because of command-line length limits. Must contain
    #: a ``{path}`` placeholder. Backends that pass the prompt inline ignore
    #: this entirely — which is the point: the workaround stays in the one
    #: adapter that needs it.
    handoff_instruction: str | None = None

    #: MCP servers to expose, keyed by server name.
    mcp_servers: Mapping[str, McpServerSpec] = field(default_factory=dict)

    #: Capabilities this run genuinely needs. Checked up front.
    requires: frozenset[Capability] = frozenset()

    model: str | None = None
    timeout: float | None = None

    #: Optional file to tee harness diagnostics into.
    log_file: Path | None = None
    log_level: str = "debug"

    #: Escape hatch forwarded verbatim to the Copilot CLI. Ignored (with a
    #: warning) by every other backend; kept because it is already part of the
    #: public signature of three strategy entry points.
    extra_cli_args: tuple[str, ...] = ()

    def missing_from(self, provided: frozenset[Capability]) -> frozenset[Capability]:
        return frozenset(self.requires) - frozenset(provided)


@dataclass(frozen=True)
class AgentResult:
    """The output of one agent turn, plus provenance.

    ``backend`` and ``model`` exist so two reports are never compared as
    though they came from the same analyst. Identical prompts produce
    materially different calls across models, so any persisted run — and every
    backtest — must record which harness produced it.
    """

    text: str
    backend: str
    model: str | None = None
    raw: Any = None


@runtime_checkable
class AgentRunner(Protocol):
    """A harness that can execute one :class:`AgentRequest`."""

    name: str
    capabilities: frozenset[Capability]

    def run(
        self,
        request: AgentRequest,
        *,
        on_output: OutputSink | None = None,
    ) -> AgentResult:
        ...
