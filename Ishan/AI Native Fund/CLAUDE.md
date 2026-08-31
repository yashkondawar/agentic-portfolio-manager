# AI-Native Fund

AI-native investment research/decision system for Indian markets (NSE
equities, ETFs, MFs). Deterministic Python does data/orchestration; LLM
agents do reasoning at explicit points; every capital decision halts at a
human checkpoint (manual-first — nothing moves money). Paper portfolio.

## Hard rules

- Python: ALWAYS `.venv\Scripts\python` (never bare `python`).
- Registry (`registry/`) is the governed source of truth for KPI
  vocabulary, strategies, risk rules — read via `registry.registry.Registry.load()`,
  never hardcode its content downstream.
- Deep KPI definitions + 16-cycle catalog: `knowledge/` — read via
  `knowledge.loader.load()`. Three-tier contract in `knowledge/README.md`
  (registry=vocabulary, knowledge/data=machine defs, knowledge/references=prose).
- All strategy/framework thresholds are DRAFT until user back-tests —
  label them DRAFT in any output.
- DB writes are idempotent upserts (`ON CONFLICT ... DO UPDATE`,
  COALESCE to never clobber non-NULL with NULL). Schema changes are
  additive migrations via `src/afund/db/schema.sql` + `scripts/init_db.py`.
- Agents never fetch data — they receive sanitized packets built by
  `src/afund/orchestrator/context.py`; outputs must validate against
  `src/afund/agents/contracts.py`.
- Never fabricate data for missing sources; mark `data_pending` /
  `missing` honestly (see `knowledge/data/kpis/*.yaml` source_status).
- Token frugality: packets carry pointers to reference prose, not the
  prose itself.

## Key commands

```
.venv\Scripts\python -m pytest -q                      # full test suite
.venv\Scripts\python -m afund.orchestrator.run --job daily_data
.venv\Scripts\python -m afund.orchestrator.run --job daily_news_process
.venv\Scripts\python -m afund.orchestrator.run --job weekly_idea_cycle
.venv\Scripts\python -m streamlit run dashboard/app.py
.venv\Scripts\python scripts/smoke_source.py <group> <name>   # verify a source
```

## Directory map

```
config/          settings.yaml (incl. sector_index_map), sources.yaml (verify_status per source)
registry/        registry.py loader; kpis/ (8 sectors), strategies/, rules/
knowledge/       loader.py; data/kpis/ (16 macro + micro/<8>), data/cycles/catalog.yaml (16); references/
src/afund/       data/ (pipelines), derive/, agents/, orchestrator/, memory/, portfolio/, db/
.claude/agents/  11 fund agents (fund_manager/critique/synthesis=opus, most=sonnet, news=haiku)
scripts/         init_db.py, backfill_prices.py, smoke_source.py, apply_meta_proposal.py
dashboard/       Streamlit app (read-only)
docs/            RUNBOOK.md (ops), SYSTEM_MAP.md (build state), source-material/
tests/           pytest; fixtures/ for offline pipeline tests
data/afund.db    SQLite (gitignored)
```

## Data facts that save a session

- `index_data`: daily PE/PB/DY for NIFTY 50/500 + 8 sector indices
  (BANK, FINANCIAL SERVICES, IT, PHARMA, AUTO, FMCG, METAL,
  INFRASTRUCTURE, ENERGY), full 2016→now. Sector-slug→index mapping:
  `config/settings.yaml -> sector_index_map`.
- NSE index P/E methodology break ~Apr 2021 (standalone→consolidated);
  backfilled rows tagged `source='backfill_niftyindices_daily_snapshot'`.
- `macro_series` is placeholder-only until Phase 8 (FRED/BIS/NSE-lib
  sourcing). Most macro KPIs are status `missing` — check
  `knowledge/data/kpis/` before assuming availability.
- niftyindices.com serves HTTP 200 HTML shell (not 404) for missing
  dates; nse endpoints need the bootstrap session in
  `src/afund/data/http.py`.

## Pointers

- Current build state + data availability: `docs/SYSTEM_MAP.md`
- Ops commands / manual cadence: `docs/RUNBOOK.md`
- Cycle framework methodology: `knowledge/references/methodology/`
- Plan for Phases 7-11: `C:\Users\Admin\.claude\plans\d-downloads-fund-architecture-docx-d-do-zany-tome.md`
