"""The Claude Code backend: Anthropic's first-party harness.

This is the one backend that serves a **Claude Pro/Max subscriber who has no
API key**. That is not a niche case - it is the single largest gap left by the
other two runners, because a subscription and an API key are different
products. ``native`` speaks to the Anthropic *API* and therefore needs a key;
Copilot needs a Copilot seat. Only Anthropic's own harness can present a
subscription credential.

Authentication, in the order the CLI resolves it:

``ANTHROPIC_API_KEY``
    Pay-as-you-go. **Takes precedence over everything else**, which is the
    trap this module exists to defuse - see :func:`billing_env_overrides`.

``CLAUDE_CODE_OAUTH_TOKEN``
    A subscription credential from ``claude setup-token`` (valid ~1 year).
    Programmatic use draws on a separate monthly credit pool rather than the
    interactive Claude Code allowance, so running this app does not eat the
    quota the user needs for coding.

An interactive ``claude login``
    Credentials on disk. Works, but we cannot see it from here, which is why
    an ambiguous environment produces a warning rather than a silent guess.

Why this adapter is small: ``claude-agent-sdk`` is architecturally a near-twin
of the Copilot CLI wrapper - it spawns a CLI, hosts stdio MCP servers and
ships built-in ``WebSearch``/``WebFetch``. So :class:`McpServerSpec` renders
into it directly and ``mcp_server.py``'s ten scraper tools work unchanged.

One thing is deliberately *not* carried over: the Copilot runner's
"write the prompt to a file and tell the model to read it" dance. That was a
Windows command-line length workaround, not a design choice, and the Agent SDK
takes the prompt directly.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

from core.agent.loop import DEFAULT_MAX_TURNS
from core.agent.types import (
    AgentRequest,
    AgentResult,
    Capability,
    McpServerSpec,
    OutputSink,
)

logger = logging.getLogger("core.agent.claude_code")

__all__ = [
    "ClaudeCodeRunner",
    "billing_env_overrides",
    "render_mcp_servers",
    "allowed_tools_for",
    "resolve_cwd",
]

_MISSING_DEPS_HINT = (
    "The 'claude_code' backend needs Anthropic's Agent SDK and CLI.\n"
    "  pip install -e '.[claude]'            # or: pip install claude-agent-sdk\n"
    "  npm install -g @anthropic-ai/claude-code\n"
    "Then authenticate ONCE with whichever you have:\n"
    "  claude setup-token                    # Pro/Max subscription\n"
    "  ...or set ANTHROPIC_API_KEY           # pay-as-you-go API billing\n"
)


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


_warned_about_billing = False


def billing_env_overrides() -> dict[str, str]:
    """Environment overrides that stop billing from silently changing hands.

    ``ANTHROPIC_API_KEY`` outranks a subscription credential in the Claude CLI,
    and it does so *silently*: the run succeeds, the report looks identical,
    and the cost lands on pay-as-you-go API billing instead of the monthly
    programmatic allowance the subscriber already paid for.

    This repo makes that collision unusually likely, because ``.env`` invites
    an ``ANTHROPIC_API_KEY`` for the ``native`` backend. A user who later adds
    a subscription would keep paying per token with nothing on screen saying so.

    The rule, chosen so that the unambiguous case is fixed and the ambiguous
    one is surfaced rather than guessed:

    * **Both credentials present** - the user has explicitly chosen this
      backend, so honour the subscription and neutralise the key for the child
      process. Announced, never silent.
    * **Only the API key** - it is the sole credential; leave it alone and say
      which pocket the money comes from, because an on-disk ``claude login``
      we cannot detect would otherwise have been the user's expectation.
    * ``CLAUDE_CODE_USE_API_KEY=1`` - an explicit opt-in to API billing that
      disables all of the above.

    Returns:
        A mapping merged over the child process environment. Empty when
        nothing needs changing.
    """
    global _warned_about_billing

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {}

    if _is_truthy(os.getenv("CLAUDE_CODE_USE_API_KEY", "")):
        return {}

    oauth = os.getenv("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if oauth:
        if not _warned_about_billing:
            _warned_about_billing = True
            logger.warning(
                "Both ANTHROPIC_API_KEY and CLAUDE_CODE_OAUTH_TOKEN are set. "
                "The API key would win and bill pay-as-you-go, so it is being "
                "withheld from the Claude CLI and your subscription is used "
                "instead. Set CLAUDE_CODE_USE_API_KEY=1 to bill the API key."
            )
        # The SDK merges this over os.environ for the child; it cannot delete a
        # key, so blank it. Every credential check treats empty as absent.
        return {"ANTHROPIC_API_KEY": ""}

    if not _warned_about_billing:
        _warned_about_billing = True
        logger.warning(
            "ANTHROPIC_API_KEY is set, so this run bills pay-as-you-go API "
            "usage, even if you also have a Claude Pro/Max subscription. To "
            "use the subscription instead, run `claude setup-token` and set "
            "CLAUDE_CODE_OAUTH_TOKEN, or clear ANTHROPIC_API_KEY."
        )
    return {}


def render_mcp_servers(
    servers: dict[str, McpServerSpec],
) -> dict[str, dict[str, Any]]:
    """Render :class:`McpServerSpec` objects into the Agent SDK's stdio dicts.

    The SDK's stdio config has no per-server ``cwd``, so a spec that sets one
    gets its directory on ``PYTHONPATH`` instead. That is what ``cwd`` was
    actually buying here: ``mcp_server.py`` imports from the repo root, and
    without it those imports fail depending on where the app was launched.
    Any existing ``PYTHONPATH`` is preserved rather than replaced.
    """
    rendered: dict[str, dict[str, Any]] = {}
    for name, spec in servers.items():
        config: dict[str, Any] = {
            "type": "stdio",
            "command": spec.command,
            "args": list(spec.args),
        }
        if spec.cwd:
            inherited = os.environ.get("PYTHONPATH", "")
            config["env"] = {
                "PYTHONPATH": (
                    f"{spec.cwd}{os.pathsep}{inherited}" if inherited else spec.cwd
                )
            }
        rendered[name] = config
    return rendered


def allowed_tools_for(request: AgentRequest) -> list[str]:
    """Build the tool allow-list.

    MCP tools are namespaced ``mcp__<server>__<tool>``; naming the server alone
    admits everything it exposes, which is what ``tools=["*"]`` means.

    ``WebSearch``/``WebFetch`` are added only when the request actually
    declares :attr:`Capability.WEB_SEARCH`, so a run that never asked for live
    browsing cannot quietly acquire it.
    """
    allowed: list[str] = []
    for name, spec in request.mcp_servers.items():
        if "*" in spec.tools:
            allowed.append(f"mcp__{name}")
        else:
            allowed.extend(f"mcp__{name}__{tool}" for tool in spec.tools)
    if Capability.WEB_SEARCH in request.requires:
        allowed.extend(["WebSearch", "WebFetch"])
    return allowed


def resolve_cwd(servers: dict[str, McpServerSpec]) -> str | None:
    """Pick the working directory for the CLI from the MCP specs.

    ``ClaudeAgentOptions.cwd`` is process-wide while ``McpServerSpec.cwd`` is
    per-server, so the two only correspond when the specs agree. They do today
    (there is one server), and if that ever stops being true the mismatch is
    reported instead of being resolved by dict ordering.
    """
    directories = {spec.cwd for spec in servers.values() if spec.cwd}
    if not directories:
        return None
    chosen = sorted(directories)[0]
    if len(directories) > 1:
        logger.warning(
            "MCP servers disagree on a working directory (%s). The Claude "
            "backend has only one, so %s is used; put any path-sensitive "
            "server behind an absolute path.",
            ", ".join(sorted(directories)),
            chosen,
        )
    return chosen


class ClaudeCodeRunner:
    """Runs an :class:`AgentRequest` through Anthropic's Claude Agent SDK."""

    name = "claude_code"
    #: Unlike ``native``, this harness genuinely browses: ``WebSearch`` and
    #: ``WebFetch`` are built into the CLI, so web-grounded requests are
    #: honoured rather than rejected.
    capabilities = frozenset(
        {Capability.WEB_SEARCH, Capability.MCP_TOOLS, Capability.STREAMING}
    )

    def run(
        self,
        request: AgentRequest,
        *,
        on_output: OutputSink | None = None,
    ) -> AgentResult:
        if request.extra_cli_args:
            logger.warning(
                "Ignoring extra_cli_args %s: they are Copilot CLI flags and "
                "have no equivalent here.",
                list(request.extra_cli_args),
            )

        emit = on_output or (
            lambda chunk: (sys.stdout.write(chunk), sys.stdout.flush())
        )
        requested_model = request.model or os.getenv("CLAUDE_MODEL", "").strip() or None

        try:
            text, reported_model = asyncio.run(
                self._run_async(request, requested_model, emit)
            )
        except ImportError as exc:  # pragma: no cover - depends on user install
            raise RuntimeError(f"{_MISSING_DEPS_HINT}\nOriginal error: {exc}") from exc

        return AgentResult(
            text=text,
            backend=self.name,
            # Prefer what the CLI actually used over what we asked for: with no
            # explicit model the subscription picks one, and a report must
            # record the model that wrote it.
            model=reported_model or requested_model,
        )

    async def _run_async(
        self,
        request: AgentRequest,
        model: str | None,
        emit: OutputSink,
    ) -> tuple[str, str | None]:
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                CLINotFoundError,
                ResultError,
                ResultMessage,
                TextBlock,
                query,
            )
        except ImportError as exc:
            raise RuntimeError(f"{_MISSING_DEPS_HINT}\nOriginal error: {exc}") from exc

        servers = dict(request.mcp_servers)
        options = ClaudeAgentOptions(
            mcp_servers=render_mcp_servers(servers),
            allowed_tools=allowed_tools_for(request),
            # Headless: there is no terminal to answer a permission prompt, so
            # anything short of this hangs the run rather than failing it.
            permission_mode="bypassPermissions",
            model=model,
            max_turns=int(os.getenv("AI_MAX_TURNS", DEFAULT_MAX_TURNS)),
            cwd=resolve_cwd(servers),
            env=billing_env_overrides(),
            stderr=self._diagnostics_sink(request),
        )

        logger.info(
            "Invoking Claude Code - label=%s (%d bytes, web_grounding=%s, "
            "mcp=%s)%s",
            request.label,
            len(request.prompt),
            Capability.WEB_SEARCH in request.requires,
            ", ".join(servers) or "none",
            f", model={model}" if model else "",
        )

        streamed: list[str] = []
        final: str | None = None
        reported_model: str | None = None

        try:
            async for message in query(prompt=request.prompt, options=options):
                if isinstance(message, AssistantMessage):
                    reported_model = getattr(message, "model", None) or reported_model
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            streamed.append(block.text)
                            emit(block.text)
                elif isinstance(message, ResultMessage):
                    if getattr(message, "result", None):
                        final = message.result
        except CLINotFoundError as exc:
            raise RuntimeError(
                "The Claude Code CLI is not installed, so the 'claude_code' "
                "backend cannot run.\n"
                "  npm install -g @anthropic-ai/claude-code\n"
                f"Original error: {exc}"
            ) from exc
        except ResultError as exc:
            raise RuntimeError(self._explain(exc)) from exc

        # The result message carries the authoritative final answer; the
        # streamed blocks are the same text and are the fallback if the CLI
        # ended without one.
        text = final if final is not None else "".join(streamed)
        if not text.strip():
            raise RuntimeError(
                "Claude Code returned an empty response. Check the CLI is "
                "authenticated (`claude setup-token`, or ANTHROPIC_API_KEY)."
            )
        return text, reported_model

    @staticmethod
    def _explain(exc: Any) -> str:
        """Turn a :class:`ResultError` into something a user can act on."""
        if getattr(exc, "subtype", None) == "error_max_turns":
            return (
                f"Claude Code hit its turn limit without finishing. Raise "
                f"AI_MAX_TURNS (currently "
                f"{os.getenv('AI_MAX_TURNS', DEFAULT_MAX_TURNS)}) if this is a "
                f"genuinely large research run.\nOriginal error: {exc}"
            )
        if getattr(exc, "api_error_status", None) in {401, 403}:
            return (
                "Claude Code rejected the credentials. Run `claude "
                "setup-token` and set CLAUDE_CODE_OAUTH_TOKEN for a Pro/Max "
                "subscription, or set ANTHROPIC_API_KEY for API billing.\n"
                f"Original error: {exc}"
            )
        if getattr(exc, "api_error_status", None) == 429:
            return (
                "Claude Code is rate limited or out of credit. Programmatic "
                "use draws on a separate monthly allowance from interactive "
                "Claude Code; lower AI_MAX_CONCURRENCY or wait for it to "
                f"refresh.\nOriginal error: {exc}"
            )
        return f"Claude Code failed: {exc}"

    @staticmethod
    def _diagnostics_sink(request: AgentRequest):
        """Route CLI stderr to the debug log, and to ``log_file`` when asked.

        Matches the Copilot runner, which tees the same stream, so a failing
        run is diagnosable on either backend.
        """
        log_file = request.log_file
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)

        def sink(line: str) -> None:
            logger.debug("[claude] %s", line.rstrip())
            if log_file is not None:
                try:
                    with open(log_file, "a", encoding="utf-8", errors="replace") as fh:
                        fh.write(line if line.endswith("\n") else line + "\n")
                except OSError:
                    pass

        return sink
