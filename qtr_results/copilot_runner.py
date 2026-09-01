"""Thin Copilot-CLI runner for the quarterly-results strategy.

Reuses the verified Copilot-CLI + scraper-MCP plumbing from
``swing_trading_copilot`` (the same helpers ``watchlist_curator`` relies on) so
we don't re-implement subprocess/streaming/MCP-config wiring.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import List, Optional

from core.storage import runtime_dir
from swing_trading_copilot import (  # verified plumbing
    _resolve_copilot_bin,
    _write_scraper_mcp_config,
)

logger = logging.getLogger("qtr_results.copilot")


def _safe_write(stream, text: str) -> None:
    """Write ``text`` to a console stream without ever raising on encoding.

    The Copilot output routinely contains characters (e.g. the ₹ rupee sign) that
    the default Windows console code page (cp1252) cannot encode; a naive
    ``print`` then raises ``UnicodeEncodeError`` and aborts output capture. We
    round-trip through the stream's own encoding with ``errors="replace"`` so the
    echo degrades gracefully instead of breaking the run.
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


def run_copilot(
    prompt_text: str,
    *,
    web_grounding: bool = True,
    scraper_tools: bool = True,
    model: Optional[str] = None,
) -> str:
    """Run the Copilot CLI non-interactively on a prompt; stream + return stdout."""
    copilot_bin = _resolve_copilot_bin()

    tmp_dir = runtime_dir() / "copilot"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = tmp_dir / f"qtr-prompt-{uuid.uuid4().hex[:8]}.md"
    prompt_file.write_text(prompt_text, encoding="utf-8")

    short_prompt = (
        f"Read the file `{prompt_file.as_posix()}` in its entirety using your "
        "file-read tool. It contains your role, context and a request. Follow it "
        "exactly and respond with ONLY the final Markdown report, which MUST end "
        "with the required ```json``` block. Do not echo the prompt or narrate "
        "what you are doing."
    )

    cmd: List[str] = [
        copilot_bin,
        "-p", short_prompt,
        "--allow-all-tools",
        "--add-dir", str(tmp_dir),
        "-s",
    ]
    if web_grounding:
        cmd.append("--allow-all-urls")

    scraper_cfg_file: Optional[Path] = None
    if scraper_tools:
        try:
            scraper_cfg_file = _write_scraper_mcp_config(tmp_dir)
            cmd.extend(["--additional-mcp-config", f"@{scraper_cfg_file}"])
            logger.info("Scraper MCP server attached via %s", scraper_cfg_file.name)
        except FileNotFoundError as e:
            logger.warning("Skipping scraper tools: %s", e)

    if model:
        cmd.extend(["--model", model])

    logger.info(
        "Invoking Copilot CLI (prompt %s, %d bytes)%s",
        prompt_file.name,
        prompt_file.stat().st_size,
        f", model={model}" if model else "",
    )

    def _pump_stderr(pipe) -> None:
        try:
            for raw in iter(pipe.readline, ""):
                if not raw:
                    break
                _safe_write(sys.stderr, f"[copilot] {raw}")
        finally:
            try:
                pipe.close()
            except Exception:  # noqa: BLE001
                pass

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        stderr_thread = threading.Thread(target=_pump_stderr, args=(proc.stderr,), daemon=True)
        stderr_thread.start()

        captured: List[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            captured.append(line)
            _safe_write(sys.stdout, line)

        rc = proc.wait()
        stderr_thread.join(timeout=5.0)
        if rc != 0:
            raise RuntimeError(f"Copilot CLI exited with code {rc}.")
        return "".join(captured)
    finally:
        try:
            prompt_file.unlink(missing_ok=True)
        except OSError:
            pass
        if scraper_cfg_file is not None:
            try:
                scraper_cfg_file.unlink(missing_ok=True)
            except OSError:
                pass
