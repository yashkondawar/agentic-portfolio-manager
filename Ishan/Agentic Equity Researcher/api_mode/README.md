# api_mode/ — optional API/SDK runner (NOT the default)

The default way to run this agent is **native Claude Code** in the repo root (see root README). This folder holds the alternative: a Python pipeline that drives the same prompts through the Anthropic API directly. Use it only when you need headless/batch operation (many companies overnight), CI integration, or docling/langextract span-grounded extraction.

**Status: v1 scaffold — a documented scaffold, not a second implementation.** `run_pipeline.py` implements the model tiering, request shapes, prompt-file loading, caching hooks, and the wave structure — but the full orchestration loop (staleness propagation, subagent fan-out per document, verification gating) is marked TODO where native mode currently does the work. It runs a single wave end-to-end. Treat it as the reference for *how* to call the API correctly, not a finished product.

> **Waves 6a and 6b are NOT implemented here.** `prompts/33_thesis_synthesis.md` (which owns `state/thesis.json`) and `prompts/34_thesis_redteam.md` (which owns `findings/thesis_redteam.json` and must run in a separate context) have no counterpart in this runner, and neither do the `thesis` / `adversarial` model tiers added to `config/agent_config.yaml`. So an api_mode run produces **no thesis artefact, no red-team verdict and no rating derivation** — the three things `CLAUDE.md` rule 7 calls non-negotiable. Native mode is the only mode that runs the full lifecycle. Do not read this folder's existence as parity.

## Model tiering (mirrors config/agent_config.yaml)

| Tier | Model | Thinking / effort |
|---|---|---|
| extraction | `claude-haiku-4-5` | none (no effort param — unsupported on Haiku; extraction is lookup work, thinking wasted) |
| analysis / research / verification | `claude-sonnet-5` | adaptive (default on Sonnet 5) + `output_config.effort: "medium"` |
| report | `claude-opus-4-8` | `thinking: {"type": "adaptive"}` + `output_config.effort: "high"` |

Notes baked into the scaffold (verified against current API docs):
- Sonnet 5 / Opus 4.8: adaptive thinking only; `budget_tokens` and sampling params are rejected (400). Effort lives inside `output_config`, not top-level.
- Streaming for anything with large `max_tokens`; `get_final_message()` collects the result.
- Prompt caching: the shared prompt files (citation standard + module prompt) are sent as system blocks with `cache_control: {"type": "ephemeral"}` — stable content first, volatile inputs after the breakpoint.
- Source PDFs go in as base64 `document` blocks (≤32MB request, ≤100–600 pages depending on model context).

## Extraction path (API mode's one real advantage)

Native mode reads PDFs with Claude's built-in reader (page-level anchors). API mode could instead run **docling** (layout-aware PDF → structured text) + **langextract** (character-offset grounded extraction), which would upgrade the verification wave from page-level to span-level citation checking.

**This path is not implemented.** An earlier version of this README said `extract_docling.py` "is a stub with the intended interface" — there is no such file, and there never was; this folder contains only `run_pipeline.py` and this README. The dependencies stay commented out in `tools/requirements.txt` accordingly. Treat span-level extraction as a design intent recorded here, not as code you can call.

## Run

```
pip install anthropic  # plus docling/langextract if using that path
set ANTHROPIC_API_KEY=...
python api_mode/run_pipeline.py <TICKER> --phase extract   # one wave at a time in v1
```
