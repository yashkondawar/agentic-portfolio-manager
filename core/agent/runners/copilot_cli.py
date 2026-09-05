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
import os
import shutil
import subprocess
import sys
import threading
import uuid
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

__all__ = ["CopilotCliRunner", "resolve_copilot_bin", "safe_write", "build_cli_args"]


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
        return explicit

    # On Windows the global npm bin is usually `copilot.cmd`.
    for name in ("copilot", "copilot.cmd", "copilot.exe"):
        path = shutil.which(name)
        if path:
            return path

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
                logger.warning("Skipping MCP tools: %s", exc)

        if request.log_file is not None:
            request.log_file.parent.mkdir(parents=True, exist_ok=True)

        chosen_model = request.model or os.getenv("COPILOT_MODEL")

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
            request.log_file if request.log_file else "—",
            f", model={chosen_model}" if chosen_model else "",
        )

        log_handle: Optional[IO[str]] = None
        if request.log_file is not None:
            # Append mode so multiple runs in one session don't overwrite.
            log_handle = open(request.log_file, "a", encoding="utf-8", errors="replace")
            log_handle.write(
                f"\n{'='*72}\n"
                f"{request.label} run @ {datetime.now().isoformat(timespec='seconds')}\n"
                f"cmd: {cmd}\n"
                f"model={chosen_model}\n"
                f"{'='*72}\n"
            )
            log_handle.flush()

        emit = on_output or (lambda chunk: safe_write(sys.stdout, chunk))

        def _pump_stderr(pipe: IO[str], sink: Optional[IO[str]]) -> None:
            """Tee Copilot stderr to the console (prefixed) and optional log."""
            try:
                for raw in iter(pipe.readline, ""):
                    if not raw:
                        break
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
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
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
            assert proc.stdout is not None
            for line in proc.stdout:
                captured.append(line)
                emit(line)

            return_code = proc.wait()
            stderr_thread.join(timeout=5.0)

            if return_code != 0:
                detail = f" See log: {request.log_file}" if request.log_file else ""
                raise RuntimeError(
                    f"Copilot CLI exited with code {return_code}.{detail}"
                )

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
