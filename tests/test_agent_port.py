"""Regression tests for the agent port.

The central test here is :func:`test_cli_args_match_pre_refactor_contract`,
which pins the exact Copilot CLI argv the four strategy modules used to build
by hand. If that assertion fails, the refactor has changed what gets sent to
the CLI and the repo owner's working setup is at risk.
"""

from __future__ import annotations

import json
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
    """Existing setups must be unaffected by the refactor."""
    monkeypatch.delenv("AI_AGENT_BACKEND", raising=False)
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


def test_native_requires_explicit_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """No silent default — the model determines which API key is needed."""
    from core.agent.runners.native import _default_model

    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.delenv("NATIVE_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="AI_MODEL is not set"):
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
