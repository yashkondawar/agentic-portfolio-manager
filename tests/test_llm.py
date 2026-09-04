import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

# The Copilot SDK is an optional dependency now that the agent backend is
# pluggable (AI_AGENT_BACKEND). Skip this whole module rather than failing the
# suite for users running the `native` or `claude_code` backends, who have no
# reason to install it.
pytest.importorskip(
    "copilot",
    reason="github-copilot-sdk not installed; install with `pip install -e '.[copilot]'`",
)

from copilot.session_events import AssistantMessageData  # noqa: E402
from copilot.tools import ToolInvocation  # noqa: E402

import core.llm as llm_module  # noqa: E402
import main  # noqa: E402
from core.llm import (  # noqa: E402
    CopilotConfigurationError,
    CopilotLLM,
    copilot_tools,
    get_copilot_model,
    get_copilot_timeout,
    run_copilot_prompt,
    validate_copilot_configuration,
)
from strategies.parallel_agents import ParallelAgentsStrategy  # noqa: E402


def test_copilot_defaults(monkeypatch):
    monkeypatch.setenv("COPILOT_MODEL", "")
    monkeypatch.setenv("COPILOT_TIMEOUT", "")

    assert get_copilot_model() == "claude-opus-4.7"
    assert get_copilot_timeout() == 300.0


@pytest.mark.parametrize("value", ["invalid", "0", "-1"])
def test_invalid_copilot_timeout(monkeypatch, value):
    monkeypatch.setenv("COPILOT_TIMEOUT", value)

    with pytest.raises(CopilotConfigurationError, match="COPILOT_TIMEOUT"):
        get_copilot_timeout()


def test_invalid_explicit_cli_path(monkeypatch, tmp_path):
    missing_path = tmp_path / "missing-copilot"
    monkeypatch.setenv("COPILOT_CLI_PATH", str(missing_path))

    with pytest.raises(CopilotConfigurationError, match="does not exist"):
        validate_copilot_configuration()


def test_langchain_tool_is_adapted_for_copilot():
    class FakeTool:
        name = "stock_lookup"
        description = "Look up one stock."
        args = {"symbol": {"type": "string"}}

        async def ainvoke(self, arguments):
            return {"symbol": arguments["symbol"], "price": 100}

    tool = copilot_tools([FakeTool()])[0]
    result = asyncio.run(
        tool.handler(
            ToolInvocation(
                tool_name=tool.name,
                arguments={"symbol": "TCS"},
            )
        )
    )

    assert tool.name == "stock_lookup"
    assert tool.skip_permission is True
    assert result.result_type == "success"
    assert '"symbol": "TCS"' in result.text_result_for_llm


def test_run_prompt_uses_selected_model_and_deletes_session(monkeypatch):
    monkeypatch.setenv("COPILOT_MODEL", "claude-opus-4.7")
    captured = {}

    class FakeSession:
        session_id = "session-1"

        async def send_and_wait(self, prompt, timeout):
            captured["prompt"] = prompt
            captured["timeout"] = timeout
            return SimpleNamespace(
                data=AssistantMessageData(
                    content="research complete",
                    message_id="message-1",
                )
            )

    class FakeClient:
        async def create_session(self, **kwargs):
            captured["session_options"] = kwargs
            return FakeSession()

        async def delete_session(self, session_id):
            captured["deleted"] = session_id

    content = asyncio.run(
        run_copilot_prompt(
            "Analyze TCS",
            client=FakeClient(),
            timeout=30,
        )
    )

    assert content == "research complete"
    assert captured["session_options"]["model"] == "claude-opus-4.7"
    assert captured["session_options"]["tools"] == []
    assert captured["deleted"] == "session-1"


def test_sync_adapter_formats_parallel_agent_messages(monkeypatch):
    monkeypatch.setattr(
        llm_module,
        "validate_copilot_configuration",
        lambda: None,
    )
    captured = {}

    async def fake_run(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return '{"signal":"bullish"}'

    monkeypatch.setattr(llm_module, "run_copilot_prompt", fake_run)

    response = CopilotLLM(model="claude-opus-4.7", timeout=45).invoke(
        [
            {"role": "system", "content": "Return JSON."},
            {"role": "user", "content": "Analyze INFY."},
        ]
    )

    assert response.content == '{"signal":"bullish"}'
    assert "SYSTEM:\nReturn JSON." in captured["prompt"]
    assert "USER:\nAnalyze INFY." in captured["prompt"]
    assert captured["model"] == "claude-opus-4.7"


def test_sequential_research_runs_four_copilot_stages(monkeypatch):
    calls = []
    outputs = ["stocks", "market", "news", "recommendation"]

    @asynccontextmanager
    async def fake_client():
        yield object()

    async def fake_run(prompt, *, client, tools):
        calls.append(
            {
                "prompt": prompt,
                "tools": [tool.name for tool in tools],
            }
        )
        return outputs[len(calls) - 1]

    # The workflow now runs on any provider, so pin the backend rather than
    # relying on whatever this machine happens to have configured.
    monkeypatch.setenv("AI_AGENT_BACKEND", "copilot_cli")
    monkeypatch.setattr(main, "copilot_client", fake_client)
    monkeypatch.setattr(main, "run_copilot_prompt", fake_run)

    tool_names = {name for names in main._STAGE_TOOLS.values() for name in names}
    system = main.StockResearchSystem()
    system.tools = [SimpleNamespace(name=name) for name in tool_names]

    result = asyncio.run(system.analyze_stocks("Analyze TCS"))

    assert [message["content"] for message in result["messages"]] == outputs
    assert set(calls[0]["tools"]) == main._STAGE_TOOLS["stock_finder_agent"]
    assert set(calls[1]["tools"]) == main._STAGE_TOOLS["market_data_agent"]
    assert calls[2]["tools"] == ["fetch_stock_news"]
    assert calls[3]["tools"] == []
    assert "stocks" in calls[1]["prompt"]
    assert "market" in calls[2]["prompt"]
    assert "news" in calls[3]["prompt"]


def test_parallel_strategy_uses_copilot_by_default(monkeypatch):
    sentinel_model = object()
    captured = {}

    monkeypatch.setattr(
        llm_module,
        "get_llm",
        lambda: sentinel_model,
    )

    def fake_analysis(symbols, *, llm, portfolio_value):
        captured["symbols"] = symbols
        captured["llm"] = llm
        captured["portfolio_value"] = portfolio_value
        return {}

    monkeypatch.setattr(
        "agents.workflow.run_parallel_analysis",
        fake_analysis,
    )
    monkeypatch.setattr(
        "agents.workflow.format_analysis_report",
        lambda results: "complete",
    )

    strategy = ParallelAgentsStrategy()
    params = strategy.coerce_params({"symbols": "TCS", "portfolio_value": 500_000})
    result = strategy.run(params)

    assert params["use_llm"] is True
    assert captured["llm"] is sentinel_model
    assert captured["symbols"] == ["TCS"]
    assert result.status == "completed"
