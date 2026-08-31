"""Backend abstraction for agent invocation.

Two backends, selected by config/settings.yaml -> llm.backend:

  claude_code (default) — this module NEVER calls an LLM. prepare_invocation()
      writes a PREPARED agent_runs row and returns the exact instruction the
      operator (or an outer Claude Code session acting as orchestrator) needs
      to invoke the .claude/agents/<role> agent with the packet file and feed
      its JSON reply back via `--ingest-output`.

  api — direct Anthropic API calls via invoke_api(). Requires the
      `anthropic` package (NOT a declared dependency — install manually with
      `pip install anthropic`) and the ANTHROPIC_API_KEY env var (name
      configurable via llm.api_key_env). Model ids come from settings
      `api_model_ids` and costs from `api_prices_per_mtok` — config, not code.

prepare_invocation() is the single place a PREPARED agent_runs row is
written; orchestrator/run.py delegates here rather than duplicating the
insert.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
from pathlib import Path

from afund.agents import contracts
from afund.config import REPO_ROOT, load_settings

AGENTS_DIR = REPO_ROOT / ".claude" / "agents"

# role -> .claude/agents/<file>.md where the filename differs from the role.
# equity_researcher has no fund-side .claude/agents/*.md: the actual work
# happens in a separate Claude Code session inside research/equity_researcher/
# (its own CLAUDE.md governs that session). prepare_invocation() is used only
# for the PREPARED agent_runs bookkeeping in afund.research.er_adapter — no
# code path here should ever try to resolve or read a system-prompt file for
# this role.
ROLE_MD_OVERRIDES: dict[str, str] = {}

DEFAULT_MAX_OUTPUT_TOKENS = 4096


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _model_tier_for_role(role: str, settings: dict | None = None) -> str:
    settings = settings or load_settings()
    return (settings.get("model_tiers") or {}).get(role, "sonnet")


def _agent_md_path(role: str) -> Path:
    md_name = ROLE_MD_OVERRIDES.get(role, role)
    return AGENTS_DIR / f"{md_name}.md"


def read_system_prompt(role: str) -> str:
    """The body of .claude/agents/<role>.md with the YAML frontmatter block
    (--- ... ---) stripped — used as the system prompt in api backend mode."""
    path = _agent_md_path(role)
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n.*?\n---\n", text, flags=re.DOTALL)
    if match:
        text = text[match.end():]
    return text.strip()


def _insert_prepared_run(
    conn: sqlite3.Connection,
    *,
    role: str,
    model: str,
    backend: str,
    trigger: str,
    batch_id: str,
    approx_input_tokens: int | None,
) -> int:
    started_at = _now_iso()
    cur = conn.execute(
        """
        INSERT INTO agent_runs
            (run_batch_id, role, model, backend, trigger, input_tokens,
             output_tokens, cost_usd, status, error, started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 'PREPARED', NULL, ?, NULL)
        """,
        (batch_id, role, model, backend, trigger, approx_input_tokens, started_at),
    )
    conn.commit()
    return cur.lastrowid


def _approx_tokens_from_packet_file(packet_path: str | Path) -> int | None:
    try:
        packet = json.loads(Path(packet_path).read_text(encoding="utf-8"))
        return packet.get("approx_tokens")
    except (OSError, json.JSONDecodeError):
        return None


def prepare_invocation(
    conn: sqlite3.Connection,
    *,
    role: str,
    packet_path: str,
    batch_id: str,
    trigger: str,
) -> dict:
    """Write the PREPARED agent_runs row for one agent step and return the
    invocation descriptor for the active backend.

    claude_code backend -> {"backend", "role", "model", "packet_path",
    "agent_runs_id", "instruction"} — no LLM call is made; the instruction
    tells the operator/orchestrator exactly what to do.

    api backend -> same shape (model is the resolved API model id, and the
    instruction points at invoke_api()). Raises RuntimeError immediately if
    the API key env var is not set — a half-configured api backend must fail
    loudly at preparation time, not at invocation time.
    """
    settings = load_settings()
    backend = (settings.get("llm") or {}).get("backend", "claude_code")
    tier = _model_tier_for_role(role, settings)
    approx_input_tokens = _approx_tokens_from_packet_file(packet_path)

    if backend == "claude_code":
        agent_runs_id = _insert_prepared_run(
            conn, role=role, model=tier, backend="claude_code", trigger=trigger,
            batch_id=batch_id, approx_input_tokens=approx_input_tokens,
        )
        instruction = (
            f"READY: invoke Claude Code agent '{role}' with packet file {packet_path}; "
            f"expected output contract: see .claude/agents/{_agent_md_path(role).name}; "
            f"capture its JSON reply to a file, then run: "
            f".venv\\Scripts\\python -m afund.orchestrator.run --ingest-output {agent_runs_id} --file <output.json>"
        )
        return {
            "backend": "claude_code",
            "role": role,
            "model": tier,
            "packet_path": packet_path,
            "agent_runs_id": agent_runs_id,
            "instruction": instruction,
        }

    if backend == "api":
        api_key_env = (settings.get("llm") or {}).get("api_key_env", "ANTHROPIC_API_KEY")
        if not os.environ.get(api_key_env):
            raise RuntimeError(
                f"api backend not configured: env var {api_key_env} is not set "
                f"(and the 'anthropic' package must be installed: pip install anthropic)"
            )
        model_id = (settings.get("api_model_ids") or {}).get(tier)
        if not model_id:
            raise RuntimeError(f"api backend not configured: no api_model_ids entry for tier {tier!r} in settings.yaml")
        agent_runs_id = _insert_prepared_run(
            conn, role=role, model=model_id, backend="api", trigger=trigger,
            batch_id=batch_id, approx_input_tokens=approx_input_tokens,
        )
        instruction = (
            f"API MODE: call afund.agents.runner.invoke_api(role={role!r}, packet=<packet dict>, "
            f"conn=<conn>, agent_runs_id={agent_runs_id}) to invoke {model_id} directly; "
            f"the validated output is returned and usage/cost logged to agent_runs id={agent_runs_id}."
        )
        return {
            "backend": "api",
            "role": role,
            "model": model_id,
            "packet_path": packet_path,
            "agent_runs_id": agent_runs_id,
            "instruction": instruction,
        }

    raise RuntimeError(f"Unknown llm.backend {backend!r} in settings.yaml (expected 'claude_code' or 'api')")


def invoke_api(
    role: str,
    packet: dict,
    *,
    conn: sqlite3.Connection | None = None,
    agent_runs_id: int | None = None,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
):
    """Invoke the Anthropic API directly for one agent step (api backend only).

    - Lazy-imports the `anthropic` package (deliberately NOT in pyproject
      dependencies — install with `pip install anthropic` when adopting api
      mode; see README).
    - System prompt = the .claude/agents/<role>.md body, frontmatter stripped.
    - Model id from settings api_model_ids[model_tiers[role]].
    - Response text is contract-validated via contracts.validate_output.
    - If conn+agent_runs_id are given, usage and cost (from settings
      api_prices_per_mtok) are stamped onto that agent_runs row: COMPLETED on
      success, FAILED with the error on contract violation.

    Returns the validated pydantic model instance.
    """
    settings = load_settings()
    api_key_env = (settings.get("llm") or {}).get("api_key_env", "ANTHROPIC_API_KEY")
    if not os.environ.get(api_key_env):
        raise RuntimeError(f"api backend not configured: env var {api_key_env} is not set")

    try:
        import anthropic  # noqa: PLC0415 — lazy on purpose; not a declared dependency
    except ImportError as exc:
        raise RuntimeError(
            "api backend requires the 'anthropic' package, which is not installed. "
            "Run: pip install anthropic"
        ) from exc

    tier = _model_tier_for_role(role, settings)
    model_id = (settings.get("api_model_ids") or {}).get(tier)
    if not model_id:
        raise RuntimeError(f"api backend not configured: no api_model_ids entry for tier {tier!r} in settings.yaml")

    system_prompt = read_system_prompt(role)
    client = anthropic.Anthropic(api_key=os.environ[api_key_env])

    response = client.messages.create(
        model=model_id,
        max_tokens=max_output_tokens,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": (
                    "Context packet (JSON):\n\n"
                    + json.dumps(packet, indent=2, default=str)
                    + "\n\nRespond with ONLY the JSON object required by your output contract."
                ),
            }
        ],
    )

    reply_text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    input_tokens = getattr(response.usage, "input_tokens", None)
    output_tokens = getattr(response.usage, "output_tokens", None)
    cost_usd = _compute_cost(settings, tier, input_tokens, output_tokens)

    try:
        validated = contracts.validate_output(role, reply_text)
    except contracts.ContractViolation as exc:
        if conn is not None and agent_runs_id is not None:
            conn.execute(
                """
                UPDATE agent_runs SET status='FAILED', error=?, input_tokens=?,
                       output_tokens=?, cost_usd=?, finished_at=? WHERE id=?
                """,
                (str(exc), input_tokens, output_tokens, cost_usd, _now_iso(), agent_runs_id),
            )
            conn.commit()
        raise

    if conn is not None and agent_runs_id is not None:
        conn.execute(
            """
            UPDATE agent_runs SET status='COMPLETED', input_tokens=?,
                   output_tokens=?, cost_usd=?, finished_at=? WHERE id=?
            """,
            (input_tokens, output_tokens, cost_usd, _now_iso(), agent_runs_id),
        )
        conn.commit()

    return validated


def _compute_cost(settings: dict, tier: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    prices = (settings.get("api_prices_per_mtok") or {}).get(tier)
    if not prices or input_tokens is None or output_tokens is None:
        return None
    return round(
        input_tokens / 1_000_000 * float(prices.get("input", 0))
        + output_tokens / 1_000_000 * float(prices.get("output", 0)),
        6,
    )
