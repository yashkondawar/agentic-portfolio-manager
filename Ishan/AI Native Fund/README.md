# AI-Native Fund — Phase 0

A human-in-the-loop investment research platform, India-first and globally
aware. It is **not** an autonomous trading system: nothing in this codebase
executes trades or moves money. The pipeline researches, critiques, risk-checks,
and proposes — a human always makes the final approve/modify/reject call, and
order execution happens outside this system entirely.

## Design in one paragraph

A deterministic Python "brain" (data ingestion, ratio calculation, risk
checks, scheduling) does as much of the work as possible without an LLM.
LLMs are invoked only at genuine judgment nodes — synthesizing research,
red-teaming a thesis, sizing a position, producing a final recommendation —
via Claude Code agent definitions in `.claude/agents/`. A versioned
`registry/` (strategies, sector KPI sets, risk limits, prompts) is the single
source of truth every agent reads from; nothing downstream hardcodes rules
that belong in the registry. See `docs/source-material/architecture-blueprint.txt`
for the full 13-role pipeline design this scaffold implements incrementally.

## Repository layout

- `src/afund/` — Python package (src layout). `db/` holds the SQLite schema
  and connection helper; `config.py` loads `config/settings.yaml`.
- `config/` — `settings.yaml` (runtime settings, model tiers, cadences) and
  `sources.yaml` (every external URL/pattern the system touches, with a
  verified/needs_smoke_test status).
- `registry/` — the git-versioned rulebook: sector KPI vocabularies
  (`registry/kpis/`), strategy definitions (`registry/strategies/`), risk
  limits (`registry/rules/`), and agent prompt fragments
  (`registry/prompts/`). Loaded and pydantic-validated via `registry/registry.py`.
- `.claude/agents/` — Claude Code agent definitions for each pipeline role
  (news processing, research, idea generation, synthesis, critique, risk,
  allocation, fund management, meta-research).
- `scripts/init_db.py` — idempotent DB initializer.
- `tests/` — pytest suite covering schema integrity and registry validity.
- `docs/source-material/` — the original architecture blueprint and
  deep-research prompt suite this scaffold was built from.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

## Initialize the database

```powershell
.venv\Scripts\python scripts\init_db.py
```

Creates `data/afund.db` (SQLite, WAL mode, foreign keys enforced) from
`src/afund/db/schema.sql` and prints the resulting table count. Safe to
re-run — schema application and migration recording are both idempotent.

## Run tests

```powershell
.venv\Scripts\python -m pytest tests/ -q
```

## LLM backends

`config/settings.yaml -> llm.backend` selects how agent steps run:

- `claude_code` (default): the orchestrator never calls an LLM. Each
  `agent:` pipeline step writes a context packet plus a PREPARED
  `agent_runs` row and prints the exact instruction to invoke the
  `.claude/agents/<role>` Claude Code agent and feed its JSON reply back
  via `--ingest-output <agent_runs_id> --file <output.json>` (which
  contract-validates the reply against `src/afund/agents/contracts.py`).
- `api`: direct Anthropic API calls via `afund.agents.runner.invoke_api`.
  Requires the `anthropic` package — deliberately NOT a declared
  dependency; install it manually (`.venv\Scripts\python -m pip install anthropic`)
  and set the `ANTHROPIC_API_KEY` env var. Model ids and per-MTok prices
  come from `api_model_ids` / `api_prices_per_mtok` in settings.yaml.

## Status

Phase 0: repository scaffolding, database schema, registry seed content
(KPI sets, a draft strategy, risk-limit placeholders), and agent role
definitions. No data ingestion, scheduling, or orchestration logic is wired
up yet — that begins in Phase 1, per the build sequence in the architecture
blueprint.
