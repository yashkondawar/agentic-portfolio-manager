"""The GitHub Copilot CLI backend.

This is the behaviour-preserving extraction of the ``subprocess.Popen`` block
that was previously copy-pasted into four strategy modules. The generated
argv, flag order, streaming semantics and temp-file cleanup are unchanged; see
``tests/test_agent_port.py`` for the golden assertion that pins it.

Two deliberate consistency fixes came along with the move, both strict
improvements:

* Console echo now goes through :func:`safe_write`, which degrades gracefully
  instead of raising ``UnicodeEncodeError``. Three of the four call sites used
  a bare ``print()``, which crashes on a Windows cp1252 console the moment the
  model emits a rupee sign — routine in this app.
* ``COPILOT_MODEL`` is honoured as a fallback everywhere. Previously
  ``qtr_results`` alone ignored it.
"""

from __future__ import annotations

import json
import logging
import math
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import IO, Optional

from core.agent.types import (
    AgentRequest,
    AgentResult,
    Capability,
    McpServerSpec,
    OutputSink,
)
from core.storage import runtime_dir

logger = logging.getLogger("core.agent.copilot_cli")

__all__ = [
    "CopilotCliRunner", "CopilotCliError", "resolve_copilot_bin",
    "safe_write", "build_cli_args",
]


class CopilotCliError(RuntimeError):
    """A CLI failure with retained diagnostics and an explicit retry policy."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def _installed_native_cli(path: str) -> str:
    """Use the native payload of this npm installation, not its Node shim."""
    shim = Path(path)
    if sys.platform != "win32" or shim.name.lower() not in {
        "copilot", "copilot.cmd", "copilot.ps1",
    }:
        return path
    architecture = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        architecture
    )
    if arch is None:
        return path
    modules = shim.parent / "node_modules" / "@github"
    package = f"copilot-win32-{arch}"
    for candidate in (
        modules / "copilot" / "node_modules" / "@github" / package / "copilot.exe",
        modules / package / "copilot.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return path


def safe_write(stream: IO[str], text: str) -> None:
    """Write ``text`` to a console stream without ever raising on encoding.

    Copilot output routinely contains characters (e.g. the rupee sign) that the
    default Windows console code page cannot encode; a naive ``print`` then
    raises ``UnicodeEncodeError`` and aborts output capture mid-run. We
    round-trip through the stream's own encoding with ``errors="replace"`` so
    the echo degrades gracefully instead of breaking the run.
    """
    try:
        stream.write(text)
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "utf-8"
        stream.write(text.encode(enc, errors="replace").decode(enc, errors="replace"))
    try:
        stream.flush()
    except Exception:  # noqa: BLE001
        pass


def resolve_copilot_bin() -> str:
    """Locate the ``copilot`` executable."""
    explicit = os.getenv("COPILOT_BIN")
    if explicit:
        if not Path(explicit).exists():
            raise RuntimeError(f"COPILOT_BIN points to non-existent path: {explicit}")
        return _installed_native_cli(explicit)

    # On Windows the global npm bin is usually `copilot.cmd`.
    for name in ("copilot", "copilot.cmd", "copilot.exe"):
        path = shutil.which(name)
        if path:
            return _installed_native_cli(path)

    raise RuntimeError(
        "GitHub Copilot CLI not found on PATH.\n"
        "Install with:  npm install -g @github/copilot\n"
        "Then run `copilot` once to authenticate.\n"
        "Or set COPILOT_BIN to the absolute path of the binary."
    )


def write_mcp_config(servers: dict[str, McpServerSpec], tmp_dir: Path) -> Path:
    """Render :class:`McpServerSpec` objects into a Copilot CLI MCP config."""
    config = {
        "mcpServers": {
            name: {
                "type": "stdio",
                "command": spec.command,
                "args": list(spec.args),
                "cwd": spec.cwd,
                "tools": list(spec.tools),
            }
            for name, spec in servers.items()
        }
    }
    cfg_path = tmp_dir / f"mcp-{uuid.uuid4().hex[:8]}.json"
    cfg_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return cfg_path


def build_cli_args(
    copilot_bin: str,
    short_prompt: str,
    tmp_dir: Path,
    *,
    allow_urls: bool,
    mcp_config: Optional[Path],
    log_level: Optional[str],
    model: Optional[str],
    extra_cli_args: tuple[str, ...] = (),
) -> list[str]:
    """Assemble the Copilot CLI argv.

    Split out from :meth:`CopilotCliRunner.run` purely so the golden test can
    assert the flag set and ordering without spawning a process.

    ``-p`` runs the CLI in programmatic (non-interactive) mode.
    ``--allow-all-tools`` skips the tool-permission prompts that would
    otherwise block a headless run. ``-s`` strips stats noise.
    """
    cmd: list[str] = [
        copilot_bin,
        "-p", short_prompt,
        "--allow-all-tools",
        "--add-dir", str(tmp_dir),
        "-s",
    ]
    # Allow all URLs so web-fetch / search tools don't trigger an interactive
    # approval prompt mid-run.
    if allow_urls:
        cmd.append("--allow-all-urls")
    if mcp_config is not None:
        cmd.extend(["--additional-mcp-config", f"@{mcp_config}"])
    if log_level is not None:
        cmd.extend(["--log-level", log_level])
    if model:
        cmd.extend(["--model", model])
    if extra_cli_args:
        cmd.extend(extra_cli_args)
    return cmd


class CopilotCliRunner:
    """Runs an :class:`AgentRequest` through the GitHub Copilot CLI."""

    name = "copilot_cli"
    capabilities = frozenset(
        {Capability.WEB_SEARCH, Capability.MCP_TOOLS, Capability.STREAMING}
    )

    def run(
        self,
        request: AgentRequest,
        *,
        on_output: OutputSink | None = None,
    ) -> AgentResult:
        from core.llm import get_copilot_timeout

        timeout = request.timeout if request.timeout is not None else get_copilot_timeout()
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Copilot CLI timeout must be finite and positive")
        deadline = time.monotonic() + timeout
        for attempt in range(1, 4):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Copilot CLI {request.label} exhausted its {timeout:g}s budget")
            try:
                return self._run_once(
                    replace(request, timeout=remaining), on_output=on_output,
                )
            except CopilotCliError as exc:
                delay = 2 ** attempt
                if not exc.retryable or attempt == 3 or deadline - time.monotonic() <= delay:
                    raise
                logger.warning(
                    "Transient Copilot CLI failure (%s); retrying attempt %s/3 in %ss",
                    exc, attempt + 1, delay,
                )
                time.sleep(delay)
        raise AssertionError("Unreachable Copilot retry state")

    def _run_once(
        self, request: AgentRequest, *, on_output: OutputSink | None = None,
    ) -> AgentResult:
        from core.llm import get_copilot_model, get_copilot_timeout

        started = time.monotonic()
        chosen_model = (request.model or "").strip() or get_copilot_model()
        timeout = request.timeout if request.timeout is not None else get_copilot_timeout()
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Copilot CLI timeout must be finite and positive")
        copilot_bin = resolve_copilot_bin()

        tmp_dir = runtime_dir() / "copilot"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # The prompt is handed over as a file: Windows cmd.exe caps a command
        # line at ~8191 chars and a portfolio prompt blows straight past that.
        prompt_file = tmp_dir / f"{request.label}-prompt-{uuid.uuid4().hex[:8]}.md"
        prompt_file.write_text(request.prompt, encoding="utf-8")

        handoff = request.handoff_instruction or (
            "Read the file `{path}` in its entirety using your file-read tool. "
            "Follow the instructions in that file exactly and respond with ONLY "
            "the final Markdown report — do not echo the prompt or describe what "
            "you are doing."
        )
        short_prompt = handoff.format(path=prompt_file.as_posix())

        scraper_cfg_file: Optional[Path] = None
        if request.mcp_servers:
            try:
                scraper_cfg_file = write_mcp_config(
                    dict(request.mcp_servers), tmp_dir
                )
                logger.info(
                    "MCP server(s) attached via %s: %s",
                    scraper_cfg_file.name,
                    ", ".join(request.mcp_servers),
                )
            except OSError as exc:
                prompt_file.unlink(missing_ok=True)
                raise CopilotCliError(f"Could not configure required Copilot MCP tools: {exc}") from exc

        if request.log_file is not None:
            request.log_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = build_cli_args(
            copilot_bin,
            short_prompt,
            tmp_dir,
            allow_urls=Capability.WEB_SEARCH in request.requires,
            mcp_config=scraper_cfg_file,
            log_level=request.log_level if request.log_file is not None else None,
            model=chosen_model,
            extra_cli_args=request.extra_cli_args,
        )

        logger.info(
            "Invoking Copilot CLI (%s) — label=%s (prompt: %s, %d bytes, "
            "web_grounding=%s, mcp=%s, log=%s)%s",
            copilot_bin,
            request.label,
            prompt_file.name,
            prompt_file.stat().st_size,
            Capability.WEB_SEARCH in request.requires,
            bool(request.mcp_servers),
            request.log_file or prompt_file.with_suffix(".log"),
            f", model={chosen_model}" if chosen_model else "",
        )

        diagnostics = request.log_file or prompt_file.with_suffix(".log")
        succeeded = False
        log_handle: Optional[IO[str]] = None
        if diagnostics is not None:
            # Append mode so multiple runs in one session don't overwrite.
            log_handle = open(diagnostics, "a", encoding="utf-8", errors="replace")
            log_handle.write(
                f"\n{'='*72}\n"
                f"{request.label} run @ {datetime.now().isoformat(timespec='seconds')}\n"
                f"cmd: {cmd}\n"
                f"model={chosen_model}\n"
                f"{'='*72}\n"
            )
            log_handle.flush()

        emit = on_output or (lambda chunk: safe_write(sys.stdout, chunk))
        stderr_tail: deque[str] = deque(maxlen=40)

        def _pump_stderr(pipe: IO[str], sink: Optional[IO[str]]) -> None:
            """Tee Copilot stderr to the console (prefixed) and optional log."""
            try:
                for raw in iter(pipe.readline, ""):
                    if not raw:
                        break
                    stderr_tail.append(raw[-4096:])
                    safe_write(sys.stderr, f"[copilot] {raw}")
                    if sink is not None:
                        sink.write(raw)
                        sink.flush()
            finally:
                try:
                    pipe.close()
                except Exception:  # noqa: BLE001
                    pass

        try:
            if time.monotonic() - started >= timeout:
                raise TimeoutError(f"Copilot CLI {request.label} exhausted its startup budget")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            # Consume stderr on a thread; a chatty MCP/log stream can otherwise
            # fill the pipe buffer and deadlock the run.
            stderr_thread = threading.Thread(
                target=_pump_stderr,
                args=(proc.stderr, log_handle),
                daemon=True,
            )
            stderr_thread.start()

            captured: list[str] = []
            timed_out = threading.Event()
            finished = threading.Event()

            def expire() -> None:
                if finished.is_set():
                    return
                timed_out.set()
                logger.error("Copilot CLI %s exceeded its %.0fs deadline", request.label, timeout)
                if os.name == "nt":
                    # Kill only this invocation's captured descendants, including
                    # MCP servers; killing cmd.exe alone leaves their pipes open.
                    script = f"""
$all = Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId
$ids = [System.Collections.Generic.List[int]]::new()
$ids.Add({proc.pid})
for ($i = 0; $i -lt $ids.Count; $i++) {{
    foreach ($child in $all) {{
        if ($child.ParentProcessId -eq $ids[$i] -and -not $ids.Contains([int]$child.ProcessId)) {{
            $ids.Add([int]$child.ProcessId)
        }}
    }}
}}
$ids.Reverse()
foreach ($id in $ids) {{ Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }}
"""
                    try:
                        subprocess.run(
                            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, timeout=20, check=True,
                        )
                    except (OSError, subprocess.SubprocessError):
                        logger.exception("Could not terminate the timed-out Copilot process tree")
                        proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)

            timer = threading.Timer(max(0, timeout - (time.monotonic() - started)), expire)
            timer.daemon = True
            timer.start()
            assert proc.stdout is not None
            try:
                for line in proc.stdout:
                    captured.append(line)
                    emit(line)
                return_code = proc.wait()
            finally:
                finished.set()
                timer.cancel()
                timer.join()
            stderr_thread.join(timeout=5.0)
            if timed_out.is_set():
                message = (
                    f"Copilot CLI {request.label} timed out after {timeout:.3g}s. "
                    f"See log: {diagnostics}"
                )
                if log_handle is not None:
                    log_handle.write(message + "\n")
                raise TimeoutError(message)

            if return_code != 0:
                diagnostic = ("".join(stderr_tail).strip() or "".join(captured).strip())[-4000:]
                lower = diagnostic.lower()
                permanent = any(marker in lower for marker in (
                    "not recognized", "not found", "unknown model", "unsupported model",
                    "model is not available", "unauthorized", "authentication",
                    "sign in", "login required", "invalid argument", "unknown option",
                ))
                transient = return_code in (3221225786, -1073741510) or any(
                    marker in lower for marker in (
                        "rate limit", "internal server error", "bad gateway", "gateway timeout",
                        "temporarily unavailable", "connection reset", "econnreset",
                        "etimedout", "fetch failed", "socket hang up", "network error",
                        "overloaded", "service unavailable",
                    )
                ) or bool(re.search(
                    r"\b(?:http(?: error)?(?: status)?|status(?: code)?)[:=\s]+"
                    r"(?:429|500|502|503|504)\b",
                    lower,
                ))
                message = (
                    f"Copilot CLI exited with code {return_code} (model={chosen_model}). "
                    f"{diagnostic or 'No stdout/stderr diagnostic returned.'} "
                    f"See log: {diagnostics}"
                )
                logger.error("%s", message)
                if log_handle is not None:
                    log_handle.write(message + "\n")
                raise CopilotCliError(
                    message, retryable=transient and not permanent,
                )

            succeeded = True
            return AgentResult(
                text="".join(captured),
                backend=self.name,
                model=chosen_model,
            )
        finally:
            if log_handle is not None:
                try:
                    log_handle.close()
                except Exception:  # noqa: BLE001
                    pass
            # Best-effort cleanup of per-run temp files (prompt + MCP config).
            try:
                prompt_file.unlink(missing_ok=True)
            except OSError:
                pass
            if scraper_cfg_file is not None:
                try:
                    scraper_cfg_file.unlink(missing_ok=True)
                except OSError:
                    pass
            if succeeded and request.log_file is None:
                try:
                    diagnostics.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("Could not remove successful CLI diagnostic log %s: %s", diagnostics, exc)
