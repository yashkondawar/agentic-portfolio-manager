"""API-mode runner (scaffold — see api_mode/README.md; native Claude Code is the default).

Demonstrates the correct request shapes per tier and runs a single wave. Full circular
orchestration (staleness propagation, fan-out, verification gating) is TODO here; the
native orchestrator implements it today via prompts/01_orchestration_protocol.md.

Usage:
  python api_mode/run_pipeline.py TICKER --phase extract|analyze|report [--doc path.pdf]
"""
import argparse, base64, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Tier map — mirrors config/agent_config.yaml. Verified request shapes (2026-06 API):
#  - haiku-4-5: no thinking config, no effort param (unsupported); plain create
#  - sonnet-5: adaptive thinking is the default; effort inside output_config
#  - opus-4-8: adaptive thinking must be set explicitly; effort inside output_config
TIERS = {
    "extraction":   {"model": "claude-haiku-4-5",  "max_tokens": 16000,
                     "thinking": None,                       "effort": None},
    "analysis":     {"model": "claude-sonnet-5",   "max_tokens": 32000,
                     "thinking": {"type": "adaptive"},       "effort": "medium"},
    "research":     {"model": "claude-sonnet-5",   "max_tokens": 32000,
                     "thinking": {"type": "adaptive"},       "effort": "medium"},
    "verification": {"model": "claude-sonnet-5",   "max_tokens": 16000,
                     "thinking": {"type": "adaptive"},       "effort": "medium"},
    "report":       {"model": "claude-opus-4-8",   "max_tokens": 64000,
                     "thinking": {"type": "adaptive"},       "effort": "high"},
}

PHASE_PROMPTS = {  # phase -> (tier, prompt files loaded as cached system blocks)
    "extract": ("extraction", ["prompts/00_citation_standard.md", "prompts/10_extract_financials.md"]),
    "analyze": ("analysis",   ["prompts/00_citation_standard.md", "prompts/20_fundamental_analysis.md"]),
    "report":  ("report",     ["prompts/00_citation_standard.md", "prompts/41_final_report.md"]),
}


def cache_key(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
    return h.hexdigest()[:16]


def system_blocks(prompt_files):
    """Stable shared prompts first, cache breakpoint on the last stable block."""
    blocks = []
    for i, rel in enumerate(prompt_files):
        text = (ROOT / rel).read_text(encoding="utf-8")
        block = {"type": "text", "text": f"<file path={rel}>\n{text}\n</file>"}
        if i == len(prompt_files) - 1:
            block["cache_control"] = {"type": "ephemeral"}
        blocks.append(block)
    return blocks


def pdf_block(path: Path):
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return {"type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data}}


def run_wave(client, phase: str, ticker: str, doc: Path | None, user_task: str):
    tier_name, prompt_files = PHASE_PROMPTS[phase]
    tier = TIERS[tier_name]
    ws = ROOT / "workspace" / ticker
    (ws / "cache").mkdir(parents=True, exist_ok=True)

    key = cache_key(phase, *(str((ROOT / f).stat().st_mtime) for f in prompt_files),
                    str(doc) if doc else "", user_task)
    marker = ws / "cache" / f"{key}.done"
    if marker.exists():
        print(f"cache hit: {phase} already done ({marker.name}) — delete marker to force re-run")
        return None

    content = []
    if doc is not None:
        content.append(pdf_block(doc))
    content.append({"type": "text", "text": user_task})

    kwargs = dict(
        model=tier["model"],
        max_tokens=tier["max_tokens"],
        system=system_blocks(prompt_files),
        messages=[{"role": "user", "content": content}],
    )
    if tier["thinking"]:
        kwargs["thinking"] = tier["thinking"]
    if tier["effort"]:
        kwargs["output_config"] = {"effort": tier["effort"]}

    # Stream (required at these max_tokens) and collect the final message.
    with client.messages.stream(**kwargs) as stream:
        msg = stream.get_final_message()

    text = "".join(b.text for b in msg.content if b.type == "text")
    out = ws / "cache" / f"{key}.out.md"
    out.write_text(text, encoding="utf-8")
    marker.write_text(json.dumps({"phase": phase, "model": tier["model"],
                                  "usage": msg.usage.model_dump()}), encoding="utf-8")
    print(f"OK: {phase} via {tier['model']} -> {out}")
    print(f"usage: in={msg.usage.input_tokens} out={msg.usage.output_tokens} "
          f"cache_read={msg.usage.cache_read_input_tokens}")
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--phase", choices=sorted(PHASE_PROMPTS), required=True)
    ap.add_argument("--doc", default=None, help="source PDF for extract phase")
    ap.add_argument("--task", default=None, help="override the user-turn task text")
    a = ap.parse_args()

    try:
        import anthropic
    except ImportError:
        sys.exit("pip install anthropic (api_mode is optional — native mode needs no SDK)")

    client = anthropic.Anthropic()
    doc = Path(a.doc) if a.doc else None
    task = a.task or {
        "extract": f"Extract per your instructions from the attached document for {a.ticker}. "
                   f"Output fact records JSON only.",
        "analyze": f"Run your analysis for {a.ticker} using the workspace facts pasted below.\n"
                   f"TODO(scaffold): inline facts/derived_metrics.json content here.",
        "report":  f"Draft the final note for {a.ticker} from the workspace state pasted below.\n"
                   f"TODO(scaffold): inline state summaries here.",
    }[a.phase]

    run_wave(client, a.phase, a.ticker, doc, task)

    # TODO(scaffold): the circular loop — after each wave, parse open_questions.json,
    # dispatch research waves, mark stale findings, re-run owners, gate on verification.
    # Native mode implements this today (prompts/01_orchestration_protocol.md).


if __name__ == "__main__":
    main()
