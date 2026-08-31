# Runbook — manual operation (default mode)

Everything runs manually until you decide to automate. All commands from the repo root, using the project venv. Nothing below moves money; every capital recommendation halts at the human checkpoint.

## Daily — after market close (~5 min, no LLM, no tokens)

```
.venv\Scripts\python -m afund.orchestrator.run --job daily_data
```

Runs in sequence: universe refresh (Mondays), yfinance EOD prices, AMFI NAVs, index P/E snapshot (accumulates history for the Marks percentile signal), news fetch (staged, unprocessed), portfolio NAV. Check `job_runs` in the dashboard Ops tab if anything looks off.

## Morning news table (LLM step — needs a Claude Code session)

```
.venv\Scripts\python -m afund.orchestrator.run --job daily_news_process
```

This prepares a packet of up to 40 unprocessed headlines (oldest first) and prints a READY instruction block. Then, in a Claude Code session in this project, say: **"process the prepared news packet"** — the session invokes the `news_processor` agent (haiku) and ingests the validated output into `news_items`. Repeat to clear more of the backlog.

## Weekly idea cycle (once strategies are defined)

```
.venv\Scripts\python -m afund.orchestrator.run --job weekly_idea_cycle
```

Prepares packets for idea_gen → synthesis → critique → risk_mgmt → allocator → fund_manager. Drive it from a Claude Code session ("run the prepared weekly idea cycle") — each role's validated output chains to the next; the fund_manager output lands in `decision_log` as PENDING and the pipeline halts at the human checkpoint.

Record your verdict:

```
.venv\Scripts\python -m afund.orchestrator.run --record-human-decision <id> --decision APPROVE|REJECT|MODIFY --notes "..."
```

## Monthly — newsletters (after ~5th when DSP Netra publishes)

```
.venv\Scripts\python -m afund.orchestrator.run --job monthly_newsletter_digest
```

Fetches new PDFs, prepares macro_digest packets; ask a session to run them. Notes land in `knowledge_base` (MACRO).

## Monthly — AMC portfolio disclosures (after ~15th; download-only, no parsing yet)

```
.venv\Scripts\python -m afund.orchestrator.run --job monthly_amc_portfolios
```

Downloads the last 3 months of SEBI-mandated monthly portfolio Excel files from each configured AMC to `data/raw/amc_portfolios/<AMC>/` and registers them in `amc_portfolio_files`. Static-site AMCs (Nippon India) run out of the box; Playwright-dependent AMCs (HDFC/SBI/Kotak) are skipped with an install hint unless `pip install playwright && playwright install chromium` has been run.

## Monthly — macro KPIs (any time after month-end; no LLM, no tokens)

```
.venv\Scripts\python -m afund.orchestrator.run --job monthly_macro
```

Runs FRED/BIS/AMFI plus `afund.data.macro_govt` (GST collections, e-way bills, ICI Eight Core Industries, IIP via the MoSPI eSankhyiki MCP). EPFO payroll and VAHAN vehicle registrations stay manual (WAF-blocked / Playwright-pending — see `config/sources.yaml` `macro_govt` group and `knowledge/data/kpis/vehicle_registrations.yaml`); import via `afund.data.macro_manual` once downloaded by hand.

## Quarterly — meta-research (self-improvement, propose-only)

```
.venv\Scripts\python -m afund.orchestrator.run --job meta_research_cycle --period 2026-Q3
```

Ask a session to run the prepared meta_research packet. Proposals land in `data/proposals/`; stage for review with:

```
.venv\Scripts\python scripts\apply_meta_proposal.py data\proposals\<file>.json
```

Review `git diff main..meta/<period>`; merge only if you approve. Meta-research can never modify the registry itself.

## Universe screening (staged — run every day or two until coverage completes)

```
.venv\Scripts\python -m afund.orchestrator.run --job universe_screening_stage
```

Scrapes ~100 stale names from screener.in politely (2.5s+ intervals, cached, resumable) and reclassifies the company-fit table. ~7-8 runs reach full 751-name coverage; after that each run is a cheap incremental refresh (30-day freshness skip). Watch the data_gap count fall on the Company Fit dashboard page.

## Anytime

- Dashboard: `.venv\Scripts\python -m streamlit run dashboard/app.py` → http://localhost:8501
- Contrarian screen: `.venv\Scripts\python -m afund.derive.screener`
- Regime check: index P/E, returns, signals — Regime tab in the dashboard
- Paper trade (after an APPROVE): add via `afund.portfolio.ledger.add_transaction` (a CLI wrapper can be added when trading starts)
- One-off financials pull for a name: `.venv\Scripts\python scripts\smoke_source.py financials` (watchlist-scoped; add names to `universe.watchlist` in `config/settings.yaml`)
- Macro CSV import (RBI/MOSPI portals are manual-download): see `import_macro_csv` docstring in `src/afund/data/macro_rbi.py`

## When ready to automate (dormant, not active)

- Windows Task Scheduler entries for the no-LLM daily jobs: review and run `scripts/register_tasks.ps1` (as-is it only prints/registers what's in the file — read it first).
- Morning news LLM step can become a Claude Code scheduled routine later.
