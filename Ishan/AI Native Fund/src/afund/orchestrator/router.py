"""Data-driven trigger -> pipeline routing map.

Each step in a pipeline is one of:
  "py:<pipeline_fn_path>"  — pure-python, runs directly, no LLM/token cost.
  "agent:<role>"           — a Claude Code agent step (see .claude/agents/);
                              run.py builds a packet and stops for the actual
                              agent invocation (Phase 4 wires that up).
  "HUMAN"                  — a human checkpoint; run.py prints what's
                              pending and waits for --record-human-decision.

This module only defines the map and a couple of pure lookup helpers — it
does not execute anything (that's run.py's job).
"""
from __future__ import annotations

TRIGGERS: dict[str, list[str]] = {
    # Daily data ingestion — pure python, reuses the Phase 1 pipelines.
    "daily_data": [
        "py:afund.data.universe.UniversePipeline",  # only actually fetched Mondays; see run.py
        "py:afund.data.prices_yf.PricesPipeline",
        "py:afund.data.amfi_nav.AmfiNavPipeline",
        "py:afund.data.index_valuation.IndexValuationPipeline",
        "py:afund.data.india_vix.IndiaVixPipeline",  # Phase 8
        "py:afund.data.fii_dii.FiiDiiPipeline",  # Phase 8
        "py:afund.data.news_rss.NewsRssPipeline",
        "py:afund.portfolio.nav.run_daily_nav",  # mark-to-market, after prices/NAVs land
    ],
    # Standalone NAV mark-to-market — same step as daily_data's final leg, so
    # `--job daily_nav` can be run on its own (e.g. re-run after a manual
    # transaction) without re-pulling all upstream data.
    "daily_nav": [
        "py:afund.portfolio.nav.run_daily_nav",
    ],
    # Daily news enrichment — turns staged (processed=0) news_items rows into
    # structured rows via the news_processor agent.
    "daily_news_process": [
        "agent:news_processor",
    ],
    # Weekly idea generation -> human approval pipeline. Phase 10: the
    # 4-gate funnel (py:afund.cycles.funnel.run_funnel) runs FIRST, pure
    # python, no LLM cost — its output feeds idea_gen's packet as a compact
    # `funnel` slice (see orchestrator/context.py) so idea_gen reasons over
    # already-gated, ranked candidates rather than the raw screener dump.
    "weekly_idea_cycle": [
        "py:afund.cycles.funnel.run_funnel",
        "agent:idea_gen",
        "agent:synthesis",
        "agent:critique",
        "agent:risk_mgmt",
        "agent:allocator",
        "agent:fund_manager",
        "HUMAN",
    ],
    # Position monitoring: cheap deterministic invalidation check first, only
    # escalating to the (expensive) Fund Manager agent on an actual breach.
    "position_monitoring": [
        "py:afund.orchestrator.monitoring.check_invalidations",
        "agent:fund_manager",  # conditional: only invoked on breach, see run.py
        "HUMAN",
    ],
    # Monthly newsletter digest: fetch the PDFs, then digest each unparsed
    # newsletter via the macro_digest agent (run.py fans out one packet —
    # sanitized extracted PDF text + publisher/period — per unparsed row).
    "monthly_newsletter_digest": [
        "py:afund.data.newsletters.NewslettersPipeline",
        "agent:macro_digest",
    ],
    # Monthly/quarterly self-improvement review.
    "meta_research_cycle": [
        "agent:meta_research",
        "HUMAN",
    ],
    # Weekly Phase 7 cycle-engine assessment: (1) deterministic quant pass —
    # classify every catalog cycle for every scope and write
    # cycle_assessments + composite_decisions; (2) the narrative_intensity
    # agent scores the qualitative overlay per scope (run.py fans out one
    # packet per scope assessed today; ingest via --ingest-output UPDATEs
    # the narrative_* columns and recomputes that scope's composite); (3)
    # finalize recomputes every scope's composite_decisions so all ingested
    # narrative/reconciliation reads are reflected in one consistent pass.
    "weekly_cycle_assessment": [
        "py:afund.cycles.assess.run_all",
        "agent:narrative_intensity",
        "py:afund.cycles.assess.finalize",
    ],
    # Monthly macro KPI sourcing (Phase 8): FRED series (G-Sec 10Y, REER,
    # CPI/CPI_YOY, US 10Y), BIS credit-to-GDP gap bulk file, and the AMFI
    # monthly mutual-fund report. All small/cheap enough to run in one
    # monthly batch rather than daily; see config/settings.yaml cadences.
    # WORKSTREAM D adds macro_govt: GST collections, e-way bills, ICI Eight
    # Core Industries, and IIP via the MoSPI eSankhyiki MCP (EPFO/VAHAN
    # stay manual — see config/sources.yaml macro_govt group).
    "monthly_macro": [
        "py:afund.data.macro_fred.MacroFredPipeline",
        "py:afund.data.macro_bis.MacroBisPipeline",
        "py:afund.data.amfi_monthly.AmfiMonthlyPipeline",
        "py:afund.data.macro_govt.MacroGovtPipeline",
    ],
    # Phase 9 — kick off a company-level deep-dive in the external equity
    # researcher subsystem (research/equity_researcher/). Single py: step:
    # by default also runs research/disclosure_fetcher (BSE + Screener,
    # key-free, no LLM/web-search) to pre-populate input/<TICKER>/ with
    # disclosures (fetch_documents=True is prepare_kickoff's default; see
    # afund.research.er_adapter.fetch_er_documents — failure-tolerant, never
    # blocks kickoff), then writes input/<TICKER>/fund_context.json + a
    # PREPARED agent_runs row and prints the manual-first instruction; the
    # actual research run happens in a separate Claude Code session, not
    # here. Ingest later via afund.research.er_adapter.ingest_er_output (or
    # --ingest-output once its output is mapped to the equity_researcher
    # contract).
    "equity_research_kickoff": [
        "py:afund.research.er_adapter.prepare_kickoff",
    ],
    # Phase 9 — sector-level deep-dive: assemble the sector packet (cycle
    # phase, sector-filtered comparison table, registry KPI slice, knowledge
    # pointer), then hand to the sector_researcher agent.
    "sector_research": [
        "py:afund.research.sector_assembler.build_sector_packet",
        "agent:sector_researcher",
    ],
    # Phase 9 — numbers-driven rerating call once an equity_researcher run has
    # produced a valuation_handoff.json for the ticker: (1) ingest the ER
    # output into research_reports (idempotent — a no-op if already
    # ingested for today), (2) build the buy_side packet from that handoff
    # + cycle context + the buyside_depth.md pointer, (3) hand to the
    # buy_side agent (5x5 EPS x PE sensitivity grid computed in Python from
    # its scenario inputs, not by the agent).
    "buy_side_analysis": [
        "py:afund.research.er_adapter.ingest_er_output",
        "py:afund.research.er_adapter.build_buy_side_packet",
        "agent:buy_side",
    ],
    # Phase 10 — weekly ETF/MF fund analytics cache refresh: rolling
    # returns/SD/risk-adjusted + capture ratios (mapped ETFs + universe
    # mf_watchlist) and ETF premium/discount vs NAV. Pure python, no agent
    # step; writes into derived_series (see src/afund/derive/fund_analytics.py).
    "weekly_fund_analytics": [
        "py:afund.derive.fund_analytics.refresh_fund_analytics",
    ],
    # Phase 12 — monthly universe company-fit classification refresh. Pure
    # python, no agent step; assumes the (separately/manually run, see
    # `python -m afund.data.financials --universe`) batch screener scrape has
    # already populated derived_ratios for the wider universe — this step
    # itself never scrapes, only classifies whatever fundamentals already
    # exist (see src/afund/derive/company_fit.py for the data_gap bucket
    # covering instruments the scrape hasn't reached).
    "universe_fit_refresh": [
        "py:afund.derive.company_fit.refresh_company_fit",
    ],
    # Staged universe screening (user decision 2026-07-08): one ~100-name
    # polite screener stage + fit reclassification per invocation. Run
    # manually (manual-first) every day or two until data_gap count
    # converges toward zero — ~7-8 runs for full coverage, then the 30-day
    # freshness skip turns further runs into cheap incremental refreshes.
    "universe_screening_stage": [
        "py:afund.data.financials.scrape_universe_staged",
        "py:afund.derive.company_fit.refresh_company_fit",
    ],
    # Monthly AMC portfolio disclosure download (manual-first — see
    # config/settings.yaml cadences.monthly_amc_portfolios). Pure python, no
    # agent step; download-only, no Excel parsing (future scope). Static
    # AMCs (Nippon India) always run; Playwright-dependent dynamic AMCs
    # (HDFC/SBI/Kotak) are skipped with a logged install hint if the
    # optional playwright package isn't installed — see
    # src/afund/data/amc_portfolios.py module docstring.
    "monthly_amc_portfolios": [
        "py:afund.data.amc_portfolios.AmcPortfoliosPipeline",
    ],
}


def show_pipeline(trigger: str) -> list[str]:
    """Return the ordered step list for a trigger. Raises KeyError if unknown."""
    if trigger not in TRIGGERS:
        raise KeyError(f"Unknown trigger: {trigger!r}. Known triggers: {sorted(TRIGGERS)}")
    return list(TRIGGERS[trigger])
