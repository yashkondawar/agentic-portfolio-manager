import io
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from core.agent import AgentRequest
from core.agent.runners import copilot_cli as cli


@pytest.mark.parametrize("model", [None, "", "  "])
def test_cli_uses_the_shared_sol_default(monkeypatch, tmp_path, model):
    monkeypatch.delenv("COPILOT_MODEL", raising=False)
    monkeypatch.delenv("COPILOT_TIMEOUT", raising=False)
    monkeypatch.setattr(cli, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "resolve_copilot_bin", lambda: "copilot")
    commands = []

    class Process:
        stdout = io.StringIO("report\n")
        stderr = io.StringIO("")

        def wait(self):
            return 0

    def launch(command, **kwargs):
        commands.append(command)
        return Process()

    monkeypatch.setattr(cli.subprocess, "Popen", launch)
    result = cli.CopilotCliRunner().run(
        AgentRequest(prompt="test", model=model), on_output=lambda text: None,
    )
    assert result.model == "gpt-6.1-sol"
    assert commands[0][commands[0].index("--model") + 1] == "gpt-6.1-sol"
    assert result.text == "report\n"
    assert not list((tmp_path / "copilot").iterdir())


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_deadline_is_rejected_before_creating_files(monkeypatch, tmp_path, timeout):
    monkeypatch.setattr(cli, "runtime_dir", lambda: tmp_path)
    with pytest.raises(ValueError, match="finite and positive"):
        cli.CopilotCliRunner().run(AgentRequest(prompt="test", timeout=timeout))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("parent_exits", [False, True])
def test_timeout_stops_a_quiet_process_and_its_pipe_holding_child(
    monkeypatch, tmp_path, parent_exits,
):
    monkeypatch.setattr(cli, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "resolve_copilot_bin", lambda: sys.executable)
    child = "import os,time; print('CHILD:'+str(os.getpid()),flush=True); time.sleep(60)"
    script = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
        f"time.sleep({0.2 if parent_exits else 60})"
    )
    executable = getattr(sys, "_base_executable", sys.executable)
    monkeypatch.setattr(cli, "build_cli_args", lambda *a, **k: [executable, "-c", script])
    output = []
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="timed out after 2s"):
        cli.CopilotCliRunner().run(
            AgentRequest(prompt="test", timeout=2), on_output=output.append,
        )
    assert time.monotonic() - started < 20
    logs = list((tmp_path / "copilot").iterdir())
    assert logs and all(path.suffix == ".log" for path in logs)
    child_pid = next(int(line.split(":")[1]) for line in output if line.startswith("CHILD:"))
    if os.name == "nt":
        check = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"if (Get-Process -Id {child_pid} -ErrorAction SilentlyContinue) {{ exit 1 }}"],
            capture_output=True, timeout=10,
        )
        assert check.returncode == 0
    else:
        # An exited orphan can briefly remain as a zombie awaiting its reaper.
        stat = Path("/proc") / str(child_pid) / "stat"
        assert not stat.exists() or stat.read_text().split()[2] == "Z"


@pytest.mark.parametrize("hoisted", [False, True])
def test_windows_npm_install_uses_its_native_binary_without_node(monkeypatch, tmp_path, hoisted):
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(cli.platform, "machine", lambda: "AMD64")
    shim = tmp_path / "copilot.cmd"
    shim.touch()
    modules = tmp_path / "node_modules" / "@github"
    if not hoisted:
        modules = modules / "copilot" / "node_modules" / "@github"
    native = modules / "copilot-win32-x64" / "copilot.exe"
    native.parent.mkdir(parents=True)
    native.touch()
    monkeypatch.setenv("COPILOT_BIN", str(shim))
    assert cli.resolve_copilot_bin() == str(native)


def test_custom_cli_wrapper_is_not_replaced(monkeypatch, tmp_path):
    wrapper = tmp_path / "company-wrapper.cmd"
    wrapper.touch()
    monkeypatch.setenv("COPILOT_BIN", str(wrapper))
    assert cli.resolve_copilot_bin() == str(wrapper)


@pytest.mark.parametrize(
    "failures,expected_attempts",
    [
        ([(1, "fetch failed: ECONNRESET")], 2),
        ([(3221225786, "")], 2),
        ([(1, "HTTP 503 service unavailable")] * 3, 3),
        ([(1, "HTTP 500")], 2),
        ([(1, "'node' is not recognized")], 1),
        ([(1, "unsupported model gpt-6.1-sol")], 1),
        ([(1, "authentication failed (HTTP 503)")], 1),
        ([(1, "unclassified failure")], 1),
        ([(1, "A document numbered 503 could not be parsed")], 1),
    ],
)
def test_cli_preserves_diagnostics_and_only_retries_transient_failures(
    monkeypatch, tmp_path, failures, expected_attempts,
):
    monkeypatch.setattr(cli, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "resolve_copilot_bin", lambda: "copilot")
    attempts = []
    sleeps = []
    monkeypatch.setattr(cli.time, "sleep", sleeps.append)

    def launch(command, **kwargs):
        index = len(attempts)
        attempts.append(command)
        code, diagnostic = failures[index] if index < len(failures) else (0, "")

        class Process:
            stdout = io.StringIO("successful report\n" if code == 0 else "")
            stderr = io.StringIO(diagnostic)

            def wait(self):
                return code

        return Process()

    monkeypatch.setattr(cli.subprocess, "Popen", launch)
    run = lambda: cli.CopilotCliRunner().run(
        AgentRequest(prompt="test", timeout=60), on_output=lambda text: None,
    )
    if expected_attempts > len(failures):
        assert run().text == "successful report\n"
    else:
        with pytest.raises(cli.CopilotCliError) as error:
            run()
        assert (failures[-1][1] or "No stdout/stderr diagnostic") in str(error.value)
        assert "See log:" in str(error.value)
    assert len(attempts) == expected_attempts
    assert sleeps == [2, 4][:expected_attempts - 1]
    logs = list((tmp_path / "copilot").iterdir())
    assert len(logs) == min(len(failures), expected_attempts)
    assert all(path.suffix == ".log" for path in logs)
    assert "model=gpt-6.1-sol" in logs[0].read_text(encoding="utf-8")


def test_retries_share_one_deadline(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: now[0])

    def sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr(cli.time, "sleep", sleep)
    budgets = []
    runner = cli.CopilotCliRunner()

    def fail(request, **kwargs):
        budgets.append(request.timeout)
        now[0] += 3
        raise cli.CopilotCliError("503 service unavailable", retryable=True)

    monkeypatch.setattr(runner, "_run_once", fail)
    with pytest.raises(cli.CopilotCliError):
        runner.run(AgentRequest(prompt="test", timeout=10))
    assert budgets == [10, 5]


def test_required_mcp_configuration_failure_never_launches_without_tools(monkeypatch, tmp_path):
    from core.agent import McpServerSpec

    monkeypatch.setattr(cli, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "resolve_copilot_bin", lambda: "copilot")

    def failed_config(*args):
        raise OSError("disk unavailable")

    def unexpected_launch(*args, **kwargs):
        pytest.fail("Agent must not run with required tools silently missing")

    monkeypatch.setattr(cli, "write_mcp_config", failed_config)
    monkeypatch.setattr(cli.subprocess, "Popen", unexpected_launch)
    with pytest.raises(cli.CopilotCliError, match="required Copilot MCP tools"):
        cli.CopilotCliRunner().run(AgentRequest(
            prompt="research", mcp_servers={"scraper": McpServerSpec(command="python")},
        ))
    assert not list((tmp_path / "copilot").iterdir())
