"""Regression tests for the agent port.

The central test here is :func:`test_cli_args_match_pre_refactor_contract`,
which pins the exact Copilot CLI argv the four strategy modules used to build
by hand. If that assertion fails, the refactor has changed what gets sent to
the CLI and the repo owner's working setup is at risk.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

import pytest

from core.agent import (
    AgentRequest,
    Capability,
    McpServerSpec,
    UnsupportedCapability,
    available_backends,
    get_agent_runner,
    run_agent,
)
from core.agent.runners.copilot_cli import build_cli_args, write_mcp_config


# ─── The golden contract ──────────────────────────────────────────────────────

def test_cli_args_match_pre_refactor_contract(tmp_path: Path) -> None:
    """Byte-for-byte the argv the hand-rolled call sites produced.

    Transcribed from ``swing_trading_copilot.run_analysis`` as it existed
    before the extraction: flag set, flag order and value formatting.
    """
    cfg = tmp_path / "mcp-abcd1234.json"
    args = build_cli_args(
        "copilot.cmd",
        "SHORT_PROMPT",
        tmp_path,
        allow_urls=True,
        mcp_config=cfg,
        log_level="debug",
        model="claude-opus-4.7",
        extra_cli_args=("--foo", "bar"),
    )

    assert args == [
        "copilot.cmd",
        "-p", "SHORT_PROMPT",
        "--allow-all-tools",
        "--add-dir", str(tmp_path),
        "-s",
        "--allow-all-urls",
        "--additional-mcp-config", f"@{cfg}",
        "--log-level", "debug",
        "--model", "claude-opus-4.7",
        "--foo", "bar",
    ]


def test_cli_args_minimal_form(tmp_path: Path) -> None:
    """With everything optional switched off, only the base flags remain."""
    args = build_cli_args(
        "copilot",
        "P",
        tmp_path,
        allow_urls=False,
        mcp_config=None,
        log_level=None,
        model=None,
    )
    assert args == [
        "copilot",
        "-p", "P",
        "--allow-all-tools",
        "--add-dir", str(tmp_path),
        "-s",
    ]
    for absent in ("--allow-all-urls", "--additional-mcp-config", "--log-level", "--model"):
        assert absent not in args


def test_web_grounding_flag_is_driven_by_capability(tmp_path: Path) -> None:
    """`--allow-all-urls` appears iff the request declares WEB_SEARCH."""
    without = build_cli_args(
        "copilot", "P", tmp_path,
        allow_urls=False, mcp_config=None, log_level=None, model=None,
    )
    with_web = build_cli_args(
        "copilot", "P", tmp_path,
        allow_urls=True, mcp_config=None, log_level=None, model=None,
    )
    assert "--allow-all-urls" not in without
    assert "--allow-all-urls" in with_web


# ─── MCP rendering ────────────────────────────────────────────────────────────

def test_mcp_config_render_matches_previous_format(tmp_path: Path) -> None:
    """The JSON written for the CLI is unchanged from _write_scraper_mcp_config."""
    spec = McpServerSpec(command="python.exe", args=["mcp_server.py"], cwd="/repo")
    path = write_mcp_config({"indian-stock-data": spec}, tmp_path)
    written = json.loads(path.read_text(encoding="utf-8"))

    assert written == {
        "mcpServers": {
            "indian-stock-data": {
                "type": "stdio",
                "command": "python.exe",
                "args": ["mcp_server.py"],
                "cwd": "/repo",
                "tools": ["*"],
            }
        }
    }


def test_scraper_mcp_points_at_real_server() -> None:
    from core.agent import scraper_mcp

    servers = scraper_mcp()
    assert "indian-stock-data" in servers
    spec = servers["indian-stock-data"]
    assert Path(spec.args[0]).name == "mcp_server.py"
    assert Path(spec.args[0]).exists()


# ─── Capability negotiation ───────────────────────────────────────────────────

def test_native_backend_rejects_web_search_up_front() -> None:
    """A backend without live browsing must fail loudly, not degrade silently.

    Producing a swing-trade report with no current news, that still *looks*
    complete, is a correctness failure in a financial tool.
    """
    request = AgentRequest(
        prompt="irrelevant",
        requires=frozenset({Capability.WEB_SEARCH}),
    )
    with pytest.raises(UnsupportedCapability) as excinfo:
        run_agent(request, backend="native")

    assert Capability.WEB_SEARCH in excinfo.value.missing
    assert "native" in str(excinfo.value)


def test_request_without_web_search_passes_capability_check() -> None:
    request = AgentRequest(prompt="x", requires=frozenset({Capability.MCP_TOOLS}))
    runner = get_agent_runner("native")
    assert request.missing_from(runner.capabilities) == frozenset()


# ─── Registry ─────────────────────────────────────────────────────────────────

def test_default_backend_is_copilot_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """On a machine with Copilot installed, the refactor changes nothing.

    Forced rather than inferred: since detection landed, an un-pinned version
    of this test would pass or fail depending on whether the machine running
    it happens to have the Copilot CLI.
    """
    import core.agent.detect as detect

    monkeypatch.delenv("AI_AGENT_BACKEND", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.setattr(detect, "_copilot_ready", lambda: True)
    assert get_agent_runner().name == "copilot_cli"


def test_backend_selected_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT_BACKEND", "native")
    assert get_agent_runner().name == "native"


def test_unknown_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown agent backend"):
        get_agent_runner("does-not-exist")


def test_registry_lists_all_three() -> None:
    assert available_backends() == ["claude_code", "copilot_cli", "native"]


# ─── Provenance ───────────────────────────────────────────────────────────────

def test_result_carries_backend_and_model() -> None:
    """Reports from different harnesses must never be silently comparable."""
    from core.agent import AgentResult

    result = AgentResult(text="report", backend="native", model="openai:gpt-4o")
    assert result.backend == "native"
    assert result.model == "openai:gpt-4o"


# ─── Native runner ────────────────────────────────────────────────────────────

def test_native_runner_loads_real_scraper_tools() -> None:
    """The portability claim, actually exercised.

    Spawns the real ``mcp_server.py`` over stdio and adapts it into LangChain
    tools. This is what proves the same ``McpServerSpec`` reaches a non-Copilot
    harness — if MCP wiring breaks, every backend except copilot_cli silently
    loses its data tools.
    """
    import asyncio

    from core.agent import scraper_mcp
    from core.agent.runners.native import NativeRunner

    pytest.importorskip("langchain_mcp_adapters")

    request = AgentRequest(prompt="unused", mcp_servers=scraper_mcp())
    tools = asyncio.run(NativeRunner()._load_tools(request))

    names = {t.name for t in tools}
    # The tools the strategies actually depend on.
    assert {
        "fetch_stock_price",
        "fetch_fundamentals",
        "fetch_technical_indicators",
        "fetch_stock_news",
        "scrape_url",
    } <= names


def test_native_loop_executes_tools_then_returns_final_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hand-written tool-calling loop terminates and feeds results back."""
    pytest.importorskip("langchain_core")
    from langchain_core.messages import AIMessage

    from core.agent.runners import native as native_mod

    calls: list[str] = []

    class _StubTool:
        name = "fetch_stock_price"

        async def ainvoke(self, args):
            calls.append(args.get("symbol", ""))
            return "RELIANCE: 1400.50"

    class _StubModel:
        def __init__(self):
            self.turn = 0

        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            self.turn += 1
            if self.turn == 1:
                return AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "fetch_stock_price",
                        "args": {"symbol": "RELIANCE"},
                        "id": "call_1",
                    }],
                )
            return AIMessage(content="FINAL REPORT")

    monkeypatch.setattr(native_mod, "_default_model", lambda: "stub:model")
    monkeypatch.setattr(
        "langchain.chat_models.init_chat_model", lambda *a, **k: _StubModel()
    )

    async def _fake_load_tools(self, request):
        return [_StubTool()]

    monkeypatch.setattr(native_mod.NativeRunner, "_load_tools", _fake_load_tools)

    result = native_mod.NativeRunner().run(
        AgentRequest(prompt="analyse RELIANCE"), on_output=lambda _: None
    )

    assert result.text == "FINAL REPORT"
    assert result.backend == "native"
    assert calls == ["RELIANCE"], "the tool should have been invoked exactly once"


def test_native_tool_failure_is_reported_to_the_model_not_raised() -> None:
    """A dead scraper must not abort the whole research run."""
    import asyncio

    from core.agent.runners.native import NativeRunner

    class _Boom:
        name = "broken"

        async def ainvoke(self, args):
            raise RuntimeError("upstream 503")

    text = asyncio.run(
        NativeRunner._invoke_tool({"broken": _Boom()}, {"name": "broken", "args": {}})
    )
    assert "failed" in text.lower()
    assert "503" in text


def test_native_flattens_anthropic_style_content_blocks() -> None:
    """Block-style content must not leak a Python repr into a report."""
    from core.agent.runners.native import NativeRunner

    class _Msg:
        content = [
            {"type": "text", "text": "Hello "},
            {"type": "text", "text": "world"},
        ]

    assert NativeRunner._text_of(_Msg()) == "Hello world"


def test_native_model_is_inferred_from_the_single_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One key is enough. Restating it as AI_MODEL buys the user nothing.

    Someone whose only credential is a GOOGLE_API_KEY has already said which
    provider they can reach; demanding AI_MODEL too is a second setup step and
    was the exact wall the Gemini-only user hit.
    """
    from core.agent.runners.native import _default_model

    for var in ("AI_MODEL", "NATIVE_MODEL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    assert _default_model() == "google_genai:gemini-2.5-pro"


def test_native_explicit_model_beats_the_inferred_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.agent.runners.native import _default_model

    monkeypatch.delenv("NATIVE_MODEL", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setenv("AI_MODEL", "openai:gpt-4o")
    assert _default_model() == "openai:gpt-4o"


def test_native_raises_when_nothing_at_all_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no key and no model there is genuinely nothing to infer."""
    from core.agent.runners.native import _default_model

    for var in (
        "AI_MODEL",
        "NATIVE_MODEL",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="No model provider is configured"):
        _default_model()


# ---------------------------------------------------------------------------
# Optional-dependency contract
#
# github-copilot-sdk is an *extra*, not a hard dependency. A user on the
# `native` backend must be able to start the app without it. This is easy to
# regress: any new module-scope `import copilot` anywhere in the startup path
# would break every non-Copilot user, and would be invisible on a dev machine
# that has the SDK installed. Run it in a subprocess with the import blocked.
# ---------------------------------------------------------------------------

_NO_SDK_PROBE = """
import sys, importlib.abc


class _Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "copilot" or name.startswith("copilot."):
            raise ModuleNotFoundError("No module named 'copilot'")
        return None


sys.meta_path.insert(0, _Block())

import main  # noqa: F401
import app  # noqa: F401

import core.llm as llm

assert llm.SDK_AVAILABLE is False, "probe failed to hide the SDK"

for call in (
    llm.validate_copilot_configuration,
    lambda: llm.copilot_tools([]),
    llm.CopilotLLM,
):
    try:
        call()
    except llm.CopilotConfigurationError as exc:
        assert "AI_AGENT_BACKEND=native" in str(exc), f"unhelpful message: {exc}"
    else:  # pragma: no cover - only on regression
        raise AssertionError(f"{call} did not raise without the SDK")

from core.agent import get_agent_runner

assert type(get_agent_runner("native")).__name__ == "NativeRunner"

print("NO_SDK_OK")
"""


def test_app_starts_and_fails_helpfully_without_the_copilot_sdk() -> None:
    """`main` and `app` must import with the SDK absent, and Copilot-only
    entry points must raise an actionable error rather than ImportError."""
    import subprocess
    import sys as _sys

    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [_sys.executable, "-c", _NO_SDK_PROBE],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert "NO_SDK_OK" in proc.stdout, (
        "app does not start without github-copilot-sdk.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr[-3000:]}"
    )


# ---------------------------------------------------------------------------
# First-run backend detection
#
# The point of detection is that a user who has never opened Settings still
# gets a working default. These tests pin the precedence order, because a
# reshuffle would silently move users onto a provider (and a bill) they did
# not choose.
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for var in (
        "AI_AGENT_BACKEND",
        "AI_MODEL",
        "NATIVE_MODEL",
        "COPILOT_CLI_PATH",
        "COPILOT_BIN",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CODE_USE_API_KEY",
        "CLAUDE_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_explicit_backend_always_wins(clean_env: pytest.MonkeyPatch) -> None:
    from core.agent.detect import detect_backend

    clean_env.setenv("AI_AGENT_BACKEND", "native")
    clean_env.setenv("GOOGLE_API_KEY", "x")
    choice = detect_backend()
    assert choice.backend == "native"
    assert choice.explicit is True


def test_copilot_is_preferred_when_fully_installed(
    clean_env: pytest.MonkeyPatch,
) -> None:
    import core.agent.detect as detect

    clean_env.setattr(detect, "_copilot_ready", lambda: True)
    clean_env.setenv("GOOGLE_API_KEY", "x")

    choice = detect.detect_backend()
    assert choice.backend == "copilot_cli"
    assert choice.explicit is False
    assert choice.resolved is True


def test_api_key_selects_native_when_copilot_is_absent(
    clean_env: pytest.MonkeyPatch,
) -> None:
    import core.agent.detect as detect

    clean_env.setattr(detect, "_copilot_ready", lambda: False)
    clean_env.setattr(detect, "_native_ready", lambda: True)
    clean_env.setenv("GOOGLE_API_KEY", "x")

    choice = detect.detect_backend()
    assert choice.backend == "native"
    assert choice.model == "google_genai:gemini-2.5-pro"
    assert "GOOGLE_API_KEY" in choice.reason


def test_nothing_installed_is_flagged_unresolved(clean_env: pytest.MonkeyPatch) -> None:
    """A bare machine must not look like a working Copilot install."""
    import core.agent.detect as detect

    clean_env.setattr(detect, "_copilot_ready", lambda: False)
    clean_env.setattr(detect, "_native_ready", lambda: False)
    # This machine genuinely has the Claude SDK installed and is signed in, so
    # without stubbing that too the "bare machine" being simulated is not bare.
    clean_env.setattr(detect, "_claude_code_ready", lambda: False)

    choice = detect.detect_backend()
    assert choice.resolved is False
    assert "No model provider detected" in choice.reason


def test_api_key_without_langchain_is_unresolved_not_silently_copilot(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Having a key but no LangChain is a setup error, not a Copilot user."""
    import core.agent.detect as detect

    clean_env.setattr(detect, "_copilot_ready", lambda: False)
    clean_env.setattr(detect, "_native_ready", lambda: False)
    clean_env.setenv("OPENAI_API_KEY", "x")

    choice = detect.detect_backend()
    assert choice.resolved is False
    assert "LangChain is not installed" in choice.reason


def test_ai_model_alone_implies_native(clean_env: pytest.MonkeyPatch) -> None:
    import core.agent.detect as detect

    clean_env.setattr(detect, "_copilot_ready", lambda: True)
    clean_env.setenv("AI_MODEL", "ollama:llama3.1")

    choice = detect.detect_backend()
    assert choice.backend == "native"
    assert choice.model == "ollama:llama3.1"


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------


def test_persist_settings_preserves_comments_and_unmanaged_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Saving from the UI must not shred a hand-edited .env."""
    import core.agent.settings as settings

    env = tmp_path / ".env"
    env.write_text(
        "# my notes\nZERODHA_API_KEY=secret\n\n# section\nUSE_FREE_SCRAPER=true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "env_file", lambda: env)

    settings.persist_settings(
        {"AI_AGENT_BACKEND": "native", "AI_MODEL": "openai:gpt-4o"}
    )

    text = env.read_text(encoding="utf-8")
    assert "# my notes" in text
    assert "ZERODHA_API_KEY=secret" in text
    assert "AI_AGENT_BACKEND=native" in text
    assert "AI_MODEL=openai:gpt-4o" in text
    assert os.environ["AI_MODEL"] == "openai:gpt-4o"


def test_persist_settings_rejects_unmanaged_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A settings form must not be able to write arbitrary env vars."""
    import core.agent.settings as settings

    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings, "env_file", lambda: env)

    with pytest.raises(ValueError, match="unmanaged keys"):
        settings.persist_settings({"PATH": "/tmp/evil"})


def test_blank_value_clears_the_live_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import core.agent.settings as settings

    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings, "env_file", lambda: env)
    monkeypatch.setenv("AI_MODEL", "openai:gpt-4o")

    settings.persist_settings({"AI_MODEL": ""})
    assert "AI_MODEL" not in os.environ


# ---------------------------------------------------------------------------
# Shared tool loop + provider-neutral sequential workflow
# ---------------------------------------------------------------------------


class _FakeTool:
    def __init__(self, name: str, result: str = "tool-output") -> None:
        self.name = name
        self._result = result
        self.calls: list[dict] = []

    async def ainvoke(self, args):
        self.calls.append(args)
        return self._result


class _FakeModel:
    """Chat model that emits a scripted sequence of responses."""

    def __init__(self, script) -> None:
        self._script = list(script)
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = list(tools)
        return self

    async def ainvoke(self, messages):
        return self._script.pop(0)


class _Msg:
    def __init__(self, content="", tool_calls=None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


def test_tool_loop_runs_tools_then_returns_final_text() -> None:
    import asyncio as _asyncio

    from core.agent.loop import run_tool_loop

    tool = _FakeTool("get_price", "1234")
    model = _FakeModel(
        [
            _Msg(tool_calls=[{"name": "get_price", "args": {"s": "TCS"}, "id": "1"}]),
            _Msg(content="TCS trades at 1234."),
        ]
    )

    out = _asyncio.run(
        run_tool_loop(model=model, tools=[tool], prompt="price of TCS?")
    )
    assert out == "TCS trades at 1234."
    assert tool.calls == [{"s": "TCS"}]
    assert model.bound_tools == [tool]


def test_tool_loop_turn_limit_is_enforced() -> None:
    """An unbounded loop against a paid API is a bill nobody wants."""
    import asyncio as _asyncio

    from core.agent.loop import run_tool_loop

    tool = _FakeTool("spin")
    model = _FakeModel(
        [_Msg(tool_calls=[{"name": "spin", "args": {}, "id": "x"}])] * 10
    )

    with pytest.raises(RuntimeError, match="turn limit"):
        _asyncio.run(
            run_tool_loop(model=model, tools=[tool], prompt="go", max_turns=3)
        )


def test_sequential_workflow_runs_on_a_non_copilot_backend(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """The four-stage workflow must not require Copilot any more.

    Previously main.StockResearchSystem called the SDK directly, so this
    strategy was the one workflow both non-Copilot users could not run.
    """
    import asyncio as _asyncio

    import main as main_mod

    clean_env.setenv("AI_AGENT_BACKEND", "native")
    clean_env.setenv("USE_FREE_SCRAPER", "true")

    system = main_mod.StockResearchSystem()
    system.tools = [_FakeTool("get_stock_price", "999")]
    system.backend = "native"

    # Four stages, each answering without calling a tool.
    model = _FakeModel([_Msg(content=f"stage {i} done") for i in range(4)])
    system._stage_host = lambda: _null_host(model)

    result = _asyncio.run(system.analyze_stocks("find me a stock"))

    assert result["status"] == "completed"
    assert len(result["messages"]) == 4
    assert [m["name"] for m in result["messages"]] == [
        "stock_finder_agent",
        "market_data_agent",
        "news_analyst_agent",
        "recommendation_agent",
    ]
    assert result["messages"][0]["content"] == "stage 0 done"


@contextlib.asynccontextmanager
async def _null_host(model):
    yield model


# ---------------------------------------------------------------------------
# Fan-out concurrency
#
# A Copilot seat is billed per seat; an API key is billed per request and
# metered per minute. Gemini's free tier allows a handful of requests, so the
# fan-out that is free on Copilot is a wall of 429s on the backend we just
# enabled for the API-key users.
# ---------------------------------------------------------------------------


def test_fanout_is_wider_on_copilot_than_on_a_metered_api_key(
    clean_env: pytest.MonkeyPatch,
) -> None:
    from agents.workflow import max_workers

    clean_env.setenv("AI_AGENT_BACKEND", "copilot_cli")
    copilot = max_workers()

    clean_env.setenv("AI_AGENT_BACKEND", "native")
    native = max_workers()

    assert copilot == 12, "the owner's existing fan-out must not change"
    assert native < copilot


def test_fanout_respects_an_explicit_override(clean_env: pytest.MonkeyPatch) -> None:
    from agents.workflow import max_workers

    clean_env.setenv("AI_AGENT_BACKEND", "native")
    clean_env.setenv("AI_MAX_CONCURRENCY", "9")
    assert max_workers() == 9


def test_fanout_ignores_a_non_numeric_override(clean_env: pytest.MonkeyPatch) -> None:
    """A typo must not crash a research run."""
    from agents.workflow import max_workers

    clean_env.setenv("AI_AGENT_BACKEND", "copilot_cli")
    clean_env.setenv("AI_MAX_CONCURRENCY", "lots")
    assert max_workers() == 12


@pytest.mark.parametrize(
    "message",
    [
        "Error: 429 Too Many Requests",
        "RESOURCE_EXHAUSTED: quota exceeded",
        "rate limit reached for gemini-2.5-pro",
    ],
)
def test_rate_limit_errors_are_recognised(message: str) -> None:
    from agents.workflow import looks_like_rate_limit

    assert looks_like_rate_limit(message)


def test_ordinary_failures_are_not_mistaken_for_rate_limits() -> None:
    from agents.workflow import looks_like_rate_limit

    assert not looks_like_rate_limit("Error: symbol NOTREAL not found")


# ---------------------------------------------------------------------------
# The Claude Code backend.
#
# This is the only backend that serves a Claude Pro/Max subscriber with no API
# key, and it is also the one that can never be exercised end to end on this
# machine: there is no subscription here, and the SDK only wraps a Node CLI.
# So the vendor module is faked and the adapter itself is run for real. That
# covers every decision this repo actually makes - option building, tool
# scoping, cwd translation, error translation and billing - and leaves only
# Anthropic's own code untested, which is the correct split.
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_claude_sdk(monkeypatch: pytest.MonkeyPatch):
    """Install a stand-in ``claude_agent_sdk`` for the runner's lazy import.

    The runner imports the SDK inside the method rather than at module scope,
    so replacing ``sys.modules`` here is enough; and because the runner ends up
    importing these very classes, its ``isinstance`` dispatch is exercised
    rather than bypassed.
    """
    import sys
    import types as _types

    module = _types.ModuleType("claude_agent_sdk")

    class ClaudeAgentOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class TextBlock:
        def __init__(self, text: str):
            self.text = text

    class ToolUseBlock:
        def __init__(self, name: str):
            self.name = name

    class AssistantMessage:
        def __init__(self, content, model=None):
            self.content = content
            self.model = model

    class ResultMessage:
        def __init__(self, result=None, subtype="success"):
            self.result = result
            self.subtype = subtype

    class ClaudeSDKError(Exception):
        pass

    class CLINotFoundError(ClaudeSDKError):
        pass

    class ProcessError(ClaudeSDKError):
        pass

    class ResultError(ProcessError):
        def __init__(self, message, subtype=None, api_error_status=None):
            super().__init__(message)
            self.subtype = subtype
            self.api_error_status = api_error_status

    module.ClaudeAgentOptions = ClaudeAgentOptions
    module.TextBlock = TextBlock
    module.ToolUseBlock = ToolUseBlock
    module.AssistantMessage = AssistantMessage
    module.ResultMessage = ResultMessage
    module.ClaudeSDKError = ClaudeSDKError
    module.CLINotFoundError = CLINotFoundError
    module.ProcessError = ProcessError
    module.ResultError = ResultError

    module.calls = []
    module.script = []
    module.raises = None

    async def query(*, prompt, options):
        module.calls.append({"prompt": prompt, "options": options})
        if module.raises is not None:
            raise module.raises
        for message in module.script:
            yield message

    module.query = query
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", module)

    # The billing warning fires once per process by design; reset it so tests
    # do not depend on their own ordering.
    from core.agent.runners import claude_code

    monkeypatch.setattr(claude_code, "_warned_about_billing", False)
    return module


def _claude_request(**overrides) -> AgentRequest:
    defaults = dict(
        prompt="Analyse RELIANCE",
        label="swing",
        mcp_servers={
            "indian-stock-data": McpServerSpec(
                command="python",
                args=["mcp_server.py"],
                cwd="/repo",
                tools=["*"],
            )
        },
        requires=frozenset({Capability.WEB_SEARCH, Capability.MCP_TOOLS}),
    )
    defaults.update(overrides)
    return AgentRequest(**defaults)


def _say(module, text: str, model: str | None = None):
    return module.AssistantMessage([module.TextBlock(text)], model=model)


def test_claude_backend_declares_web_search(clean_env: pytest.MonkeyPatch) -> None:
    """A web-grounded run must not be rejected before it starts.

    ``run_agent`` refuses a request whose capabilities the backend lacks, so
    getting this wrong would make every grounded strategy unusable on the one
    backend a subscriber can run.
    """
    runner = get_agent_runner("claude_code")

    assert runner.name == "claude_code"
    assert Capability.WEB_SEARCH in runner.capabilities
    assert Capability.MCP_TOOLS in runner.capabilities


def test_claude_run_builds_headless_options(
    clean_env: pytest.MonkeyPatch, fake_claude_sdk
) -> None:
    fake_claude_sdk.script = [
        _say(fake_claude_sdk, "hello"),
        fake_claude_sdk.ResultMessage(result="Final answer"),
    ]
    clean_env.setenv("AI_MAX_TURNS", "7")

    result = get_agent_runner("claude_code").run(
        _claude_request(model="claude-opus-4"), on_output=lambda _: None
    )

    options = fake_claude_sdk.calls[0]["options"]
    assert fake_claude_sdk.calls[0]["prompt"] == "Analyse RELIANCE"
    # Without this the CLI blocks on an interactive permission prompt that no
    # one is there to answer, and the run hangs instead of failing.
    assert options.permission_mode == "bypassPermissions"
    assert options.max_turns == 7
    assert options.model == "claude-opus-4"
    assert options.cwd == "/repo"
    assert result.backend == "claude_code"


def test_claude_run_prefers_the_result_message_over_streamed_text(
    clean_env: pytest.MonkeyPatch, fake_claude_sdk
) -> None:
    """Streamed blocks are progress; the result message is the answer."""
    chunks: list[str] = []
    fake_claude_sdk.script = [
        _say(fake_claude_sdk, "thinking... "),
        _say(fake_claude_sdk, "more... "),
        fake_claude_sdk.ResultMessage(result="THE REPORT"),
    ]

    result = get_agent_runner("claude_code").run(
        _claude_request(), on_output=chunks.append
    )

    assert result.text == "THE REPORT"
    assert "".join(chunks) == "thinking... more... "


def test_claude_run_falls_back_to_streamed_text(
    clean_env: pytest.MonkeyPatch, fake_claude_sdk
) -> None:
    fake_claude_sdk.script = [_say(fake_claude_sdk, "partial report")]

    result = get_agent_runner("claude_code").run(
        _claude_request(), on_output=lambda _: None
    )

    assert result.text == "partial report"


def test_claude_run_records_the_model_the_cli_actually_used(
    clean_env: pytest.MonkeyPatch, fake_claude_sdk
) -> None:
    """With no model pinned, the subscription picks one - report that one."""
    fake_claude_sdk.script = [
        _say(fake_claude_sdk, "x", model="claude-sonnet-4-5-20250929"),
        fake_claude_sdk.ResultMessage(result="done"),
    ]

    result = get_agent_runner("claude_code").run(
        _claude_request(), on_output=lambda _: None
    )

    assert fake_claude_sdk.calls[0]["options"].model is None
    assert result.model == "claude-sonnet-4-5-20250929"


def test_claude_run_rejects_an_empty_response(
    clean_env: pytest.MonkeyPatch, fake_claude_sdk
) -> None:
    """An empty report must fail loudly, not be saved as a research note."""
    fake_claude_sdk.script = [fake_claude_sdk.ResultMessage(result="")]

    with pytest.raises(RuntimeError, match="empty response"):
        get_agent_runner("claude_code").run(
            _claude_request(), on_output=lambda _: None
        )


def test_claude_model_can_be_set_from_the_environment(
    clean_env: pytest.MonkeyPatch, fake_claude_sdk
) -> None:
    fake_claude_sdk.script = [fake_claude_sdk.ResultMessage(result="ok")]
    clean_env.setenv("CLAUDE_MODEL", "claude-haiku-4")

    get_agent_runner("claude_code").run(_claude_request(), on_output=lambda _: None)

    assert fake_claude_sdk.calls[0]["options"].model == "claude-haiku-4"


# ─── Translating the spec: cwd, tools, errors ────────────────────────────────


def test_mcp_cwd_becomes_pythonpath(clean_env: pytest.MonkeyPatch) -> None:
    """The SDK's stdio config has no ``cwd``, and the imports still must work.

    ``mcp_server.py`` imports from the repo root, so dropping the spec's ``cwd``
    silently would break every scraper tool depending on where the app was
    launched from.
    """
    from core.agent.runners.claude_code import render_mcp_servers

    clean_env.delenv("PYTHONPATH", raising=False)
    rendered = render_mcp_servers(
        {"indian-stock-data": McpServerSpec(command="python", args=["m.py"], cwd="/repo")}
    )

    assert rendered["indian-stock-data"]["env"]["PYTHONPATH"] == "/repo"
    assert rendered["indian-stock-data"]["command"] == "python"
    assert rendered["indian-stock-data"]["type"] == "stdio"


def test_mcp_pythonpath_preserves_an_existing_value(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Overwriting PYTHONPATH would break whatever the user already needed."""
    from core.agent.runners.claude_code import render_mcp_servers

    clean_env.setenv("PYTHONPATH", "/existing")
    rendered = render_mcp_servers(
        {"s": McpServerSpec(command="python", args=[], cwd="/repo")}
    )

    assert rendered["s"]["env"]["PYTHONPATH"] == f"/repo{os.pathsep}/existing"


def test_wildcard_tools_admit_the_whole_server() -> None:
    from core.agent.runners.claude_code import allowed_tools_for

    allowed = allowed_tools_for(_claude_request())

    assert "mcp__indian-stock-data" in allowed


def test_named_tools_are_namespaced_individually() -> None:
    from core.agent.runners.claude_code import allowed_tools_for

    allowed = allowed_tools_for(
        _claude_request(
            mcp_servers={
                "svc": McpServerSpec(command="python", tools=["get_quote", "get_news"])
            }
        )
    )

    assert "mcp__svc__get_quote" in allowed
    assert "mcp__svc__get_news" in allowed
    assert "mcp__svc" not in allowed


def test_web_tools_are_withheld_unless_the_run_asked_for_them() -> None:
    """A run that never requested browsing must not quietly acquire it."""
    from core.agent.runners.claude_code import allowed_tools_for

    grounded = allowed_tools_for(
        _claude_request(requires=frozenset({Capability.WEB_SEARCH}))
    )
    offline = allowed_tools_for(_claude_request(requires=frozenset()))

    assert "WebSearch" in grounded and "WebFetch" in grounded
    assert "WebSearch" not in offline and "WebFetch" not in offline


def test_conflicting_server_directories_are_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One process-wide cwd cannot satisfy two servers; say so, don't guess."""
    from core.agent.runners.claude_code import resolve_cwd

    with caplog.at_level("WARNING"):
        chosen = resolve_cwd(
            {
                "a": McpServerSpec(command="python", cwd="/one"),
                "b": McpServerSpec(command="python", cwd="/two"),
            }
        )

    assert chosen in {"/one", "/two"}
    assert "disagree on a working directory" in caplog.text


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"subtype": "error_max_turns"}, "AI_MAX_TURNS"),
        ({"api_error_status": 401}, "setup-token"),
        ({"api_error_status": 429}, "monthly allowance"),
    ],
)
def test_vendor_errors_are_translated_into_advice(
    clean_env: pytest.MonkeyPatch, fake_claude_sdk, kwargs: dict, expected: str
) -> None:
    """A raw ResultError tells the user nothing about what to do next."""
    fake_claude_sdk.raises = fake_claude_sdk.ResultError("boom", **kwargs)

    with pytest.raises(RuntimeError, match=expected):
        get_agent_runner("claude_code").run(
            _claude_request(), on_output=lambda _: None
        )


def test_a_missing_cli_names_the_install_command(
    clean_env: pytest.MonkeyPatch, fake_claude_sdk
) -> None:
    fake_claude_sdk.raises = fake_claude_sdk.CLINotFoundError("no claude")

    with pytest.raises(RuntimeError, match="npm install -g @anthropic-ai/claude-code"):
        get_agent_runner("claude_code").run(
            _claude_request(), on_output=lambda _: None
        )


def test_a_missing_sdk_names_the_install_command(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The likeliest first-run failure deserves the likeliest fix."""
    import sys

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)

    with pytest.raises(RuntimeError, match=r"\[claude\]"):
        get_agent_runner("claude_code").run(
            _claude_request(), on_output=lambda _: None
        )


# ─── Billing: whose money pays for the run ───────────────────────────────────
#
# ANTHROPIC_API_KEY outranks a subscription credential in the Claude CLI, and
# it does so silently - same output, different bill. This repo's own .env
# invites that key for the native backend, so the collision is likely rather
# than hypothetical.


def test_api_key_is_withheld_when_a_subscription_is_also_present(
    clean_env: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from core.agent.runners import claude_code

    clean_env.setattr(claude_code, "_warned_about_billing", False)
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-key")
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-token")

    with caplog.at_level("WARNING"):
        overrides = claude_code.billing_env_overrides()

    assert overrides == {"ANTHROPIC_API_KEY": ""}
    assert "withheld" in caplog.text


def test_a_lone_api_key_is_left_alone_but_announced(
    clean_env: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """It may be the only credential there is, so using it is right - but the
    user must be told, because an on-disk `claude login` we cannot see would
    have been the other reasonable expectation."""
    from core.agent.runners import claude_code

    clean_env.setattr(claude_code, "_warned_about_billing", False)
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-key")

    with caplog.at_level("WARNING"):
        overrides = claude_code.billing_env_overrides()

    assert overrides == {}
    assert "pay-as-you-go" in caplog.text


def test_billing_opt_in_disables_the_guard(clean_env: pytest.MonkeyPatch) -> None:
    from core.agent.runners import claude_code

    clean_env.setattr(claude_code, "_warned_about_billing", False)
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-key")
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-token")
    clean_env.setenv("CLAUDE_CODE_USE_API_KEY", "1")

    assert claude_code.billing_env_overrides() == {}


def test_subscription_only_needs_no_overrides(clean_env: pytest.MonkeyPatch) -> None:
    from core.agent.runners import claude_code

    clean_env.setattr(claude_code, "_warned_about_billing", False)
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-token")

    assert claude_code.billing_env_overrides() == {}


def test_the_guard_reaches_the_child_process(
    clean_env: pytest.MonkeyPatch, fake_claude_sdk
) -> None:
    """The decision is worthless unless it is actually passed to the SDK."""
    fake_claude_sdk.script = [fake_claude_sdk.ResultMessage(result="ok")]
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-key")
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-token")

    get_agent_runner("claude_code").run(_claude_request(), on_output=lambda _: None)

    assert fake_claude_sdk.calls[0]["options"].env == {"ANTHROPIC_API_KEY": ""}


# ─── Detection and fan-out ───────────────────────────────────────────────────


def test_a_subscription_token_selects_the_claude_backend(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.agent import detect as detect_mod

    monkeypatch.setattr(detect_mod, "_copilot_ready", lambda: False)
    monkeypatch.setattr(detect_mod, "_claude_code_ready", lambda: True)
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-token")

    choice = detect_mod.detect_backend()

    assert choice.backend == "claude_code"
    assert choice.resolved is True


def test_an_api_key_alone_still_prefers_the_cheaper_native_backend(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Having the Claude CLI installed must not re-route an API-key user.

    ``native`` talks to the API directly: no Node runtime, no agentic loop, far
    fewer tokens for the same answer. Only an explicit subscription token means
    claude_code is the one that has to run.
    """
    from core.agent import detect as detect_mod

    monkeypatch.setattr(detect_mod, "_copilot_ready", lambda: False)
    monkeypatch.setattr(detect_mod, "_claude_code_ready", lambda: True)
    monkeypatch.setattr(detect_mod, "_native_ready", lambda: True)
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-key")

    assert detect_mod.detect_backend().backend == "native"


def test_a_token_without_the_tooling_explains_what_is_missing(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.agent import detect as detect_mod

    monkeypatch.setattr(detect_mod, "_copilot_ready", lambda: False)
    monkeypatch.setattr(detect_mod, "_claude_cli", lambda: None)
    monkeypatch.setattr(detect_mod, "_claude_code_ready", lambda: False)
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-token")

    choice = detect_mod.detect_backend()

    assert choice.resolved is False
    assert "@anthropic-ai/claude-code" in choice.reason


def test_copilot_still_wins_over_a_claude_subscription(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner's working setup must not change under him."""
    from core.agent import detect as detect_mod

    monkeypatch.setattr(detect_mod, "_copilot_ready", lambda: True)
    monkeypatch.setattr(detect_mod, "_claude_code_ready", lambda: True)
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-token")

    assert detect_mod.detect_backend().backend == "copilot_cli"


def test_fanout_is_narrowest_on_the_claude_backend(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Each call spawns a CLI process and drains a small monthly credit pool."""
    from agents.workflow import max_workers

    clean_env.setenv("AI_AGENT_BACKEND", "claude_code")
    claude = max_workers()

    clean_env.setenv("AI_AGENT_BACKEND", "native")
    native = max_workers()

    assert claude == 2
    assert claude < native


# ---------------------------------------------------------------------------
# The MCP server must actually import.
#
# Nothing in the suite imported mcp_server before, so when installing the
# claude extra pulled `mcp` from 1.x to 2.x - the 2.0 release removed the
# low-level `Server.list_tools()` decorator this file is built on - all ten
# scraper tools stopped loading on EVERY backend and every test still passed.
# The agent simply reported that it had no market-data tools. This is the
# cheapest possible guard against that whole class of silent breakage.
# ---------------------------------------------------------------------------


def test_the_scraper_mcp_server_imports() -> None:
    import importlib

    module = importlib.import_module("mcp_server")

    assert hasattr(module, "server"), "mcp_server must expose its Server object"


def test_mcp_dependency_stays_on_the_supported_major() -> None:
    """Pinned in pyproject; asserted here so an upgrade fails loudly."""
    from importlib.metadata import version

    major = int(version("mcp").split(".")[0])

    assert major == 1, (
        "mcp 2.x removed the low-level Server decorators mcp_server.py uses. "
        "Porting it is a real change, not an incidental upgrade."
    )


# ─── Lessons from the live run ───────────────────────────────────────────────
#
# Both of these were found by running the backend against a real subscription,
# and neither could have been found by the faked tests above: they are facts
# about Anthropic's shipped package and about the user's machine, not about
# this repo's logic.


def test_the_bundled_cli_counts_as_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The SDK ships its own `claude` binary and prefers it over PATH.

    Observed directly: the SDK logged "Using bundled Claude Code CLI" and
    ignored the copy on PATH. Insisting on a separate `npm install -g` would
    reject an install that demonstrably works.
    """
    from core.agent import detect as detect_mod

    monkeypatch.setattr(detect_mod, "_claude_cli", lambda: None)
    monkeypatch.setattr(detect_mod, "_claude_bundled_cli", lambda: True)
    monkeypatch.setattr(detect_mod, "find_spec", lambda name: object())

    assert detect_mod._claude_code_ready() is True


def test_an_interactive_login_is_detected_as_a_last_resort(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`claude login` leaves nothing in the environment to detect.

    Verified on a real run: with no ANTHROPIC_API_KEY and no
    CLAUDE_CODE_OAUTH_TOKEN set, the backend still worked, because the CLI had
    credentials on disk. Keying detection solely on the env var would tell that
    user "no model provider detected" while the thing was working.
    """
    from core.agent import detect as detect_mod

    monkeypatch.setattr(detect_mod, "_copilot_ready", lambda: False)
    monkeypatch.setattr(detect_mod, "_claude_code_ready", lambda: True)
    monkeypatch.setattr(detect_mod, "_claude_signed_in", lambda: True)

    choice = detect_mod.detect_backend()

    assert choice.backend == "claude_code"
    assert choice.resolved is True


def test_an_api_key_still_outranks_a_mere_interactive_login(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disk check is a guess; a key is evidence. Order accordingly."""
    from core.agent import detect as detect_mod

    monkeypatch.setattr(detect_mod, "_copilot_ready", lambda: False)
    monkeypatch.setattr(detect_mod, "_claude_code_ready", lambda: True)
    monkeypatch.setattr(detect_mod, "_claude_signed_in", lambda: True)
    monkeypatch.setattr(detect_mod, "_native_ready", lambda: True)
    clean_env.setenv("GOOGLE_API_KEY", "x")

    assert detect_mod.detect_backend().backend == "native"
