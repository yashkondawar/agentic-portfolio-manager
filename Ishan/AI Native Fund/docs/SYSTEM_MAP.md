# SYSTEM_MAP — AI-Native Fund

Current build state + data availability, updated post-Workstream-E
(2026-07-13; HEAD `01980c1` + this workstream's wiring audit). Companion to
the repo `CLAUDE.md` (conventions/commands) and `docs/RUNBOOK.md` (ops
commands). Update this file at each phase gate / major workstream.

## Module map

| Module | Responsibility |
|---|---|
| `src/afund/config.py` | Loads `config/settings.yaml` (raw dict; `sector_index_map` lives here) |
| `src/afund/sources.py` | Loads `config/sources.yaml` (source registry w/ verify_status) |
| `src/afund/db/` | SQLite connection + `schema.sql` (idempotent CREATE IF NOT EXISTS + migrations) |
| `src/afund/data/base.py` | `Pipeline` base class: fetch/parse/upsert lifecycle + job_runs logging |
| `src/afund/data/universe.py` | NSE universe + benchmark/sector INDEX instruments + ETF registration |
| `src/afund/data/prices_yf.py` | Daily OHLCV via yfinance for universe + indices |
| `src/afund/data/index_valuation.py` | Index PE/PB/DY: daily snapshot (nse_all_indices) + historical backfill (niftyindices Daily_Snapshot archive) |
| `src/afund/data/amfi_nav.py`, `amfi_monthly.py` | MF NAVs (AMFI daily) + AMFI monthly report |
| `src/afund/data/news_rss.py`, `newsletters.py`, `newsletter_text.py` | News + newsletter ingestion |
| `src/afund/data/financials.py` | Quarterly financials (yfinance; revenue/ebitda/net_profit/eps + raw_json); `scrape_universe_staged` polite screener batch |
| `src/afund/data/macro_fred.py`, `macro_bis.py` | Phase 8 macro sourcing: FRED (G-Sec 10Y, REER, CPI, US 10Y) + BIS credit-to-GDP gap bulk file |
| `src/afund/data/macro_govt.py` | **Workstream D**: government monthly/quarterly datasets — GST collections, e-way bills, ICI Eight Core Industries, IIP (via MoSPI eSankhyiki MCP with PDF/manual fallback); one `MacroGovtPipeline` per-source try/except so a broken source degrades gracefully rather than failing the whole job. |
| `src/afund/data/corp_actions.py` | Corporate actions |
| `src/afund/data/india_vix.py`, `fii_dii.py` | India VIX + FII/DII net flows (Phase 8) |
| `src/afund/data/amc_portfolios.py` | Monthly AMC portfolio disclosure downloader — static AMCs (Nippon India) live via plain requests; dynamic AMCs (HDFC/SBI/Kotak) gated on Playwright (see Known gaps). |
| `src/afund/derive/` | `ratios.py`, `returns.py`, `technicals.py`, `screener.py` (bottom-up screens), `regime.py` (Marks-lens valuation overlay, subsumed by cycles/), `company_fit.py` (universe fit classification), `fund_analytics.py` (ETF/MF rolling analytics) |
| `src/afund/cycles/` | Phase 7 cycle engine: `framework.py` (loads `cycle_framework.yaml`), `classify.py`, `composite.py`, `assess.py`, `funnel.py` (4-gate idea funnel), `narrative.py`, `anchors.py`, `transforms.py`, `parabolic.py` |
| `src/afund/research/` | Phase 9 ER bridge: `er_adapter.py` (prepare_kickoff/fetch_er_documents/ingest_er_output/build_buy_side_packet), `sector_assembler.py` (sector packet), `sensitivity.py` (5x5 EPS x PE grid), `interpretation.py` (`resolve_frame()` — the only place the fund's family frames and the ER playbook frames are layered) |
| `src/afund/agents/` | `contracts.py` (pydantic agent-output contracts, `ROLE_MODELS` registry), `runner.py`, `sanitize.py` |
| `src/afund/orchestrator/` | `router.py` (`TRIGGERS` map), `context.py` (packet builder), `scheduler.py`, `escalation.py`, `monitoring.py`, `run.py` |
| `src/afund/memory/` | `stores.py`, `retrieval.py` (episodic/semantic memory over DB) |
| `src/afund/portfolio/` | `ledger.py`, `nav.py`, `risk.py` (paper portfolio) |
| `registry/` | Governed vocabulary: `registry.py` loader, `kpis/*.yaml` (8 sectors), `strategies/` (incl. `cycle_framework.yaml`), `rules/risk_limits.yaml`, `rules/eps_bridge.yaml` (Phase 11 EPS-bridge checker thresholds, all DRAFT), `rules/interpretation_frames.yaml` (12 conditioning variables, 5 discriminator types, 8 family frames, all DRAFT). `Registry.load()` reads only `risk_limits.yaml`; the two rules files are read directly with yaml by their consumers |
| `knowledge/` | Three-tier knowledge repo: `loader.py`, `data/kpis/` (macro + `micro/<8 sectors>`, 56 KPIs total incl. Workstream D's gst_collections/eway_bills/epfo_payroll/ici_index/iip_yoy/vehicle_registrations), `data/cycles/catalog.yaml` (16 cycles), `references/` (methodology/sectors/kpi_interpretation prose, incl. `methodology/eps_bridge.md`, `methodology/buyside_depth.md` + `methodology/facts_vs_interpretation.md`). See `knowledge/README.md` |
| `research/equity_researcher/` | External ER subsystem v2.1 (own CLAUDE.md, own Claude Code session): `tools/convert_docs.py`, `build_comprehensive_statement.py`, `eps_bridge_check.py` (zero-token deterministic EPS-bridge checker), `export_financials_xlsx.py` (IS/BS/CF tree + Quarterly + Ratios + EPS_Bridge + RedFlags sheets), `preflight.py`/`validate_state.py`/`validate_sector_registry.py` (own gates); `config/sector_registry.yaml` (8 families → 32 tier-2 playbooks), `docs/OPINION_VS_ANALYSIS.md` (taxonomy, 10 failure modes, 18-check audit, 9 banned reasoning patterns) |
| `research/disclosure_fetcher/` | Ticker-only ER material gathering (BSE + Screener primary, key-free, web-search fallback OFF by default) — feeds `research/equity_researcher/input/<TICKER>/` |
| `dashboard/app.py` | Streamlit dashboard (read-only; native numeric columns, row-click drill-in, cycle-wheel selection, fragment-scoped panels) |
| `scripts/` | `init_db.py`, `backfill_prices.py`, `smoke_source.py`, `apply_meta_proposal.py`, `register_tasks.ps1`, `map_etf_scheme_codes.py`, `gen_sector_packs.py`, `gen_eps_thresholds.py`, `check_interpretation_frames.py` (one-way vocabulary check, not a generator), `wiring_check.py` (permanent zero-network wiring audit, see below) |
| `.claude/agents/` | 13 fund agent definitions (see roster) |

## DB tables (row counts as of 2026-07-13)

| Table | Rows | Note |
|---|---|---|
| daily_prices | 1,465,597 | universe + index OHLCV |
| index_data | 27,581 | PE/PB/DY: NIFTY 50/500 + 8 sector indices, full 2016-2026 daily; NIFTY TOTAL MARKET 2021-2026 (index launched Oct 2021) |
| instruments | 773 | incl. 12 INDEX rows (766-773 = the 8 sector indices) |
| universe_membership | 751 | |
| mf_navs | 22,689 | |
| corporate_actions | 2,546 | |
| news_items | 503 | |
| financials_quarterly | 554 | staged universe screening (~100 names/run, user decision 2026-07-08) now populating this at scale |
| knowledge_base | 21 | machine-accumulated notes (distinct from knowledge/ tree) |
| macro_series | 21,033 | Phase 8 (FRED/BIS/AMFI) + Workstream D (GST/EWAY/ICI/IIP) fills; still placeholder-only for sources not yet sourced (VAHAN, EPFO, NPCI) |
| derived_ratios | 461 | |
| derived_series | 10 | Phase 10 fund-analytics cache (rolling returns/SD, ETF prem/disc) |
| company_fit | 751 | Phase 12 universe fit classification |
| newsletters | 2 | |
| research_reports | 0 | wired (Phase 9 ER bridge), awaiting first ingested ER run — KPITTECH is next (see Known gaps) |
| amc_portfolio_files | 2 | Workstream C: static-AMC (Nippon India) downloads live; dynamic AMCs deferred on Playwright |
| decision_log | 1 | |
| cycle_assessments | 288 | Phase 7 weekly cycle engine, live |
| composite_decisions | 18 | |
| agent_runs 31 / job_runs 53 / schema_migrations 3 / nav_history 2 | | |
| calibration, lessons, mf_holdings, positions, thesis_tracker, transactions | 0 | wired, awaiting live flow (no real trades/theses yet — paper portfolio) |

## Data availability

| KPI / dataset | Source | Cadence | Status |
|---|---|---|---|
| G-Sec 10Y | FRED `INDIRLTLT01STM` CSV gateway (no key) | monthly | verified |
| India VIX | `nse` lib fetch_historical_vix_data + allIndices | daily | verified |
| FII/DII net | NSE fii-dii CSV via nse lib | daily, fwd-accumulate | verified |
| Credit-to-GDP gap | BIS bulk `data.bis.org/static/bulk/WS_CREDIT_GAP_csv_col.zip` series Q.IN.P.A.A | quarterly | verified |
| REER | FRED `RBINBIS` / BIS EER bulk M.R.B.IN | monthly | verified |
| CPI (`cpi_yoy`) | FRED `INDCPIALLMINMEI` (YoY computed) | monthly | verified, but **stale**: FRED lags ~12-15 months (latest 2025-03 as of 2026-07); `inflation_anchor` enforces a 6-month staleness cutoff and reads `data_stale` until a fresh point lands — fresh route is manual MOSPI import via `afund.data.macro_manual` (series_code `CPI_YOY`) |
| MF retail inflows | AMFI monthly PDF note | monthly | verified |
| **GST collections** (`GST_COLLECTIONS`) | gst.gov.in statistics workbook (single 26-sheet XLSX) | monthly | **verified — Apr-24 through May-26** (~2yr; not full FY2017-18-forward, source only publishes a rolling window) |
| **E-way bills** (`EWAY_BILLS`) | ewaybillgst.gov.in per-FY XLSX files | monthly | **verified — full history from 2018-07** (backfilled in one pass) |
| **EPFO payroll** (`epfo_payroll`) | epfindia.gov.in payroll XLSX | monthly | **broken** — F5 BIG-IP WAF rejects GET (200 status but ~246-byte HTML rejection page, not the binary); confirmed targeted block via working controls on same domain. No fetch function wired; `source_status: manual` |
| **Eight Core Industries** (`ICI_INDEX` + 8 sub-sectors) | eaindustry.nic.in monthly PDF (`IPR_{year}_{month}.pdf`) | monthly, ~20-day lag | **verified — ~18 months backfilled**; pdfplumber table extraction off page index 3 |
| **IIP** (`IIP_INDEX`, `IIP_YOY`) | MoSPI eSankhyiki MCP server (JSON-RPC/SSE, BETA) | monthly | **verified — 167 points, 2012-04 through 2026-03, one call, no pagination**; `fetch_iip_via_mcp` degrades gracefully (try/except) if the BETA contract changes |
| **VAHAN vehicle registrations** | vahan.parivahan.gov.in (JS-rendered dashboard) | monthly | **manual** — no static file/API; needs Playwright (see Known gaps headline item) |
| **NPCI UPI/FASTag** | npci.org.in stats/export pages | monthly | **broken** — HTTP 403 to scripted requests.Session (browser-UA bot-wall), distinct failure class from EPFO; no scripted fetch attempted per plan |
| PPAC petroleum | ppac.gov.in dashboard/Excel/PDF | monthly | manual (not scripted this pass) |
| CEA/Grid-India power | JS/cert-gated PDF bundles | monthly | manual |
| Railways freight | PIB prose (no predictable URL) | monthly | manual |
| Steel (JPC) | steel.gov.in press releases (JPC itself paywalled) | monthly | manual; partially covered via `ICI_STEEL` sub-series |
| DGCA traffic | S3 PDFs, non-sequential doc IDs | monthly | manual (borderline future-parser candidate) |
| Mcap/GDP (`mcap_gdp`) | NSE total mcap + India nominal GDP | quarterly | **missing** — both inputs unsourced; `cycle_refs: [valuation_cycle, gdp_business_cycle]`, blocked on `gdp_business_cycle` promotion |
| HY spreads | none free (FIMMDA login-only) | — | missing/deferred |
| Breadth, GSR, gold-to-Nifty, index EPS growth, ETF prem/disc, MF capture | EXISTING tables only | — | derivable |

Machine-readable per-KPI status: `knowledge/data/kpis/*.yaml`
(`source_status` field — the "KPI finder" that gates the cycle engine and
doubles as the sourcing worklist). Full technical detail (headers,
content-type guards, table extraction offsets) per source:
`config/sources.yaml` → `macro_govt:` group.

## Agent roster (13 current, `.claude/agents/`)

| Agent | Tier | Role |
|---|---|---|
| fund_manager | opus | final synthesis packet; the recommendation the human sees |
| critique | opus | independent challenge (never the thesis author); includes Pre-Mortem extension |
| synthesis | opus | house view; sharpens/softens theses |
| meta_research | opus | monthly self-improvement proposals (never auto-applied) |
| buy_side | opus | numbers-driven rerating call from an ER valuation handoff + cycle context; conviction score + 5x5 EPS x PE sensitivity grid (computed in Python, not by the agent). Packet upgraded (Phase 11) with `eps_bridge_check`, `xlsx_path`, and `narrative_findings_reference` pointers — see ER chain below. A standalone `buy_side` role/config also exists for non-default, ad hoc invocation outside the `buy_side_analysis` trigger. |
| research_head | sonnet | research dispatcher, invoked sub-agent-to-sub-agent by idea_gen/synthesis/critique/fund_manager directly — never an `agent:` step in `orchestrator.router.TRIGGERS`, so intentionally has no `contracts.ROLE_MODELS` entry (documented exception in `scripts/wiring_check.py`) |
| idea_gen | sonnet | candidate ideas (top-down + bottom-up); reasons over the pre-gated 4-gate funnel output |
| risk_mgmt | sonnet | pre-trade checks + monitoring; cycle-aware phase_multipliers |
| allocator | sonnet | sizing + vehicle choice; allocation bands |
| macro_digest | sonnet | newsletter → MACRO knowledge-base notes |
| narrative_intensity | sonnet | qualitative -100..+100 overlay per cycle-assessment scope, weekly |
| sector_researcher | sonnet | sector-level deep-dive off `sector_assembler`'s packet |
| news_processor | haiku | raw news → news_items rows |

`equity_researcher` is an external subsystem role (own Claude Code session
in `research/equity_researcher/`, no `.claude/agents/*.md`); it DOES have a
`contracts.ROLE_MODELS` entry (`EquityResearchNote`) for `er_adapter`'s
`ingest_er_output` validation but no `model_tiers` entry, since it never
runs via `afund.agents.runner`'s dispatch (documented exception in
`scripts/wiring_check.py`).

## ER / buy-side data flow (Phase 9 + Phase 11)

```
research/disclosure_fetcher (BSE+Screener, ticker-only, no LLM)
  → research/equity_researcher/input/<TICKER>/  (raw disclosures)
  → [separate Claude Code session] equity_researcher subsystem (v2.1):
      tools/convert_docs.py → triage T2 picks 1 of 32 tier-2 playbooks
      → tools/build_comprehensive_statement.py
      → tools/eps_bridge_check.py (deterministic, registry/rules/eps_bridge.yaml, DRAFT thresholds)
      → tools/export_financials_xlsx.py (workspace/<TICKER>/exports/<TICKER>_financials.xlsx)
      → prompts/33 → state/interpretation_ledger.json (one fact, ≥2 readings, discriminator)
      → prompts/34 → findings/thesis_redteam.json (18-check opinion audit; 16-18 audit the ledger)
      → valuation_handoff.json (carries sector_playbook + interpretation_ledger)
  → afund.research.er_adapter.ingest_er_output  (writes research_reports, incl. xlsx_path;
      records the ledger + red-team files as sources)
  → afund.research.er_adapter.build_buy_side_packet
      (adds eps_bridge_check / xlsx_path / narrative_findings_reference pointers, plus
       sector_playbook / interpretation_frame / interpretation_ledger / redteam_findings /
       opinion_audit_reference)
  → agent:buy_side  (buy_side_analysis trigger) → names a multiple_conditioner
```

**Interpretation frames (facts vs analysis).** The lens the packets carry is
governed data, not prose: `registry/rules/interpretation_frames.yaml` owns the
closed 12-token conditioning vocabulary, the 5 discriminator types and the 8
family-level default multiples (all DRAFT); the ER
`config/sector_registry.yaml` mirrors the 8 families and adds the 32 tier-2
playbooks. `src/afund/research/interpretation.py::resolve_frame()` is the only
place the two tiers are combined (family first, playbook layered on top, key by
key — the same semantics as `eps_bridge_check._override_chain`), and it feeds
both `build_buy_side_packet` and `sector_assembler.build_sector_packet`.
`scripts/check_interpretation_frames.py --check` is a one-way check (never a
generator): the 32-playbook registry stays upstream-owned. Doctrine:
`knowledge/references/methodology/facts_vs_interpretation.md`; corpus evidence:
`research/equity_researcher/docs/OPINION_VS_ANALYSIS.md`.

## Phase history

| Phase | Commit | Scope |
|---|---|---|
| 0 | `7e49839` | repo skeleton, schema, registry seed, agent definitions |
| 1 | `a9f8f1e` | data pipelines (universe, prices, NAVs, news, financials, macro, newsletters, derive) |
| 2 | `2aa2c00` | memory stores + deterministic orchestrator brain |
| 3 | `7685ec0` | paper portfolio, risk metrics, Streamlit dashboard |
| 4 | `efaac63` | agent contracts, sanitization, ingestion, newsletter digest plumbing |
| 5 | `7188adf` | meta-research proposal loop, calibration wiring, apply-proposal staging |
| 5.x | `1bbe347`, `b2b9dcd`, `5a3e161` | screener, runbook (manual-first), historical index P/E backfill |
| 6 | — | sector-index P/E backfill (8 indices, 10y), knowledge/ repo + loader, CLAUDE.md + this map |
| 7 | — | cycle engine: cycles/*, cycle_framework.yaml (DRAFT), live cycles, narrative_intensity, weekly_cycle_assessment |
| 8 | — | macro data sourcing: FRED/BIS/NSE-lib/AMFI-PDF → macro_series; Yield Gap + EVI go live |
| 9 | — | ER subsystem copy + adapter + research_reports; sector_researcher + buy_side agents; 5×5 sensitivity |
| 10 | — | ETF/MF analytics, funnel wiring, premortem, cycle-aware risk |
| 11 | — | EPS-bridge doctrine (eps_bridge_check, export_financials_xlsx, buy_side packet upgrade), multipage dashboard |
| 12 | — | universe fit classification (`company_fit`), staged universe screening |
| Workstream C | `6be278d` | AMC monthly portfolio downloader: static AMCs live, dynamic (Playwright) deferred |
| Workstream D | — | govt macro pipelines: GST/EWAY/ICI/IIP verified w/ spans; EPFO WAF-broken, NPCI 403, VAHAN manual (see Data availability + Known gaps) |
| Workstream E | — | `scripts/wiring_check.py` permanent audit (127/127 at the time); SYSTEM_MAP refresh |
| **ER v2.1 + facts/interpretation** | this commit | **ER subsystem synced to v2.1 in both projects (two-tier sector routing, thesis synthesis + red-team, 32 playbooks); the interpretation ledger authored upstream and wired into fund contracts, both packet builders, four agent prompts, `registry/rules/interpretation_frames.yaml` + `knowledge/references/methodology/facts_vs_interpretation.md`; `wiring_check.py` now 152/152** |

## Known gaps / risks

**HEADLINE: Playwright install (~200MB, one-time) required at full scale
— unlocks VAHAN vehicle registrations + HDFC/SBI/Kotak AMC portfolio
downloads (user decision 2026-07-13: deferred).** This is the single
largest remaining "connected but not executing at full scale" gap: both
`afund.data.amc_portfolios` (dynamic AMCs) and the VAHAN route for
`vehicle_registrations` are code-ready pending this one optional
dependency; static/manual fallbacks cover the interim.

1. EPFO payroll (`epfo_payroll`) — F5 BIG-IP WAF returns a fake-200
   HTML rejection page instead of the XLSX binary; confirmed targeted
   (working controls on the same domain succeed). No fetch function
   wired; `source_status: manual`.
2. NPCI UPI/FASTag stats — HTTP 403 bot-wall to scripted requests, a
   distinct failure class from EPFO's fake-200. No scripted fetch
   attempted further per plan.
3. `mcap_gdp` KPI unsourced — both inputs (NSE total mcap, India nominal
   GDP) `status: missing`; blocked on `gdp_business_cycle` promotion in
   the catalog before it's worth prioritizing.
4. CPI staleness — FRED's `INDCPIALLMINMEI` lags ~12-15 months; the
   `inflation_anchor` enforces a 6-month staleness cutoff and reports
   `data_stale` rather than silently using a year-old print. Fresh route
   is the manual MOSPI import (`afund.data.macro_manual`, series_code
   `CPI_YOY`), not yet run.
5. KPITTECH equity-research run pending — 75MB of real disclosure
   documents already staged in `research/equity_researcher/input/KPITTECH/`
   (annual reports FY2022-2026, quarterly results, BSE acquisition
   disclosures, investor PPTs) via `disclosure_fetcher`, but the ER
   subsystem run itself (separate Claude Code session) has not executed
   yet — `research_reports` table is still empty, so buy-side/EPS-bridge
   verification for a real company remains fixture-based until this runs.
   The v2.1 artifacts (T2 playbook pick, `state/interpretation_ledger.json`,
   `findings/thesis_redteam.json`) are on the same critical path: the fund
   side reads all three, and every one of them is proven only by fixture
   today. The one existing real run, the standalone project's NALCO
   workspace, predates the ledger — `tools/validate_state.py` correctly
   warns that prompts/33 step 6b never ran there.
6. Yield Gap at monthly resolution only (FRED G-Sec; user accepted).
7. ETF→AMFI scheme-code mapping — some ETFs still lack
   `amfi_scheme_code`; blocks premium/discount for those names
   (`scripts/map_etf_scheme_codes.py` exists to close remaining gaps).
8. HY spreads unavailable free (FIMMDA login-only) — Credit cycle rides
   credit-to-GDP gap alone.
9. ALL framework thresholds are DRAFT until user calibrates/back-tests —
   engine + web app must label DRAFT (this includes `eps_bridge.yaml`).
10. NSE index P/E methodology break ~Apr 2021 (standalone→consolidated
    earnings): level shift in PE series; backfilled rows carry
    `source='backfill_niftyindices_daily_snapshot'` provenance so
    percentile windows can be scoped if needed.
11. `financials_quarterly` stores only 5 dedicated columns + raw_json —
    most sector micro-KPIs are `derivable`, not `available` (see
    `knowledge/data/kpis/micro/*.yaml`); staged universe screening is
    steadily filling this in (~100 names/run, converging toward zero
    `data_gap` rows in `company_fit`).
12. NIFTY TOTAL MARKET history starts 2021-10 (index launch) — its
    percentile windows are structurally short.
13. NIFTY FINANCIAL SERVICES has no working public yfinance ticker
    (`yf_ticker=None`); its OHLCV depends on the index_data snapshot path.
14. GST collections source (`gst_collection_xlsx`) only publishes a
    rolling ~2-year window (Apr-24 onward as of this check) — not the
    full FY2017-18-forward history originally hoped for; no deeper
    archive identified yet.
