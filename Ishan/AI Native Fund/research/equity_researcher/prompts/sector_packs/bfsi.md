<!-- GENERATED from registry/kpis + knowledge/references + research/equity_researcher/config/sector_registry.yaml — edit sources, then re-run scripts/gen_sector_packs.py -->
# Sector Pack — Banking, Financial Services & Insurance *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in `prompts/sector_playbooks/` carries the KPI table, the valuation convention, the divergence cases, the exhibit set and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the two differ.** Shared research rules: `prompts/31`. Routing source of truth: `config/sector_registry.yaml`.*

**Core truth:** Lenders win by pricing the next rupee of risk correctly; sustainable ROA/ROE comes from liability franchise + underwriting, not growth. Book value quality (true provisioning, through-cycle stability) is the real number under the printed number.

## What the whole family has in common
- **Liability franchise**: CASA quality and stickiness, cost-of-funds trajectory, wholesale-funding reliance (CP dependence for NBFCs) and ALM pressure under rate moves; digital acquisition cost benchmarking.
- **Asset mix & underwriting**: secured vs unsecured mix across peers, segment seasoning, collection efficiency, restructured-book history.
- **Book value quality**: true loan-loss provisioning and through-cycle stability underlying ROA/ROCE — the printed P/B is only as good as the provisioning behind the B.
- **Regulatory moat & risk**: RBI/IRDAI/SEBI posture (licenses, digital-lending rules, Basel/capital norms); recent or impending regulation from RBI/SEBI papers.
- **Upstream/downstream flow**: marginal cost of funds (especially NBFC reliance on the commercial-paper market) vs core CASA on the liability side; collection efficiency and capital-deployment efficiency against risk-weighted assets on the asset side.
- **Porter's read**: rivalry priced on the next rupee of lending/deposit; bargaining power of depositors/wholesale money markets and sensitivity to RBI rate moves (ALM pressure).
- **Stress tests**: use publicly available stress-test results on loan books where published.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Routes on | Unit lens | Status |
|---|---|---|---|
| `banks_private` | scheduled commercial bank, casa ratio, net interest margin | per rupee of average assets | authored |
| `nbfc_diversified` | non-banking financial company, upper layer nbfc, assets under management | per rupee of average aum | authored |
| `housing_finance` | housing finance company, home loan, loan to value | per rupee of average aum | authored |
| `microfinance` | joint liability group, microfinance, microfinance institutions network | per borrower | authored |
| `life_insurance` | value of new business, annualised premium equivalent, persistency ratio | per policy | authored |
| `general_health_insurance` | combined ratio, loss ratio, claims ratio | per policy | authored |
| `amc_capital_market_infra` | asset management company, average assets under management, systematic investment plan | per rupee of aaum | authored |

`Routes on` shows the first few routing keywords only; `config/sector_registry.yaml` carries the full list and is the source of truth. A company spanning two children is multi-segment: primary by largest EBIT, the other recorded as a `secondary_playbook`. If a child is ever marked `status: pending`, analyse on this pack plus the closest authored sibling, state in the note which convention you borrowed, and do **not** fall through to `generic`.

## Interpretation frame (family default)

Multiples: primary `p_b`; secondary `p_abv`, `p_ev`, `pe_forward`; conditioned by `sustainable_roe`, `balance_sheet_risk`, `earnings_base_quality`.

These are the family-level defaults; the child playbook overrides them and carries the sub-sector's `## Divergence cases`. A conditioner names *which variable* makes a given multiple expensive or cheap — the same P/E supports opposite readings depending on it (`docs/OPINION_VS_ANALYSIS.md` §7).

## Governed KPI floor

The fund's governed KPI vocabulary for this sector is `registry/kpis/bfsi.yaml` — 23 KPIs across 9 categories (Core Valuation, Core Profitability, Core Returns, Asset Quality, Capital, Cash Flow Quality, Liability Franchise, Growth, Insurance). Read it via `registry.registry.Registry.load()`; it is never restated here, and the per-KPI detail belongs to the tier-2 playbook. `scripts/gen_sector_packs.py --check` reports any child playbook `signature_kpi` this vocabulary does not cover.

**Relative-valuation justifier:** P/B premium/discount vs sustained ROA/ROE and book-value quality — include the P/B-vs-ROE cross-sectional read across peers (who's off the regression line and why).

**Preferred sources:** RBI DBIE & circulars, IRDAI, company investor decks (NIM/GNPA walk slides), exchange filings, rating-agency reports (CRISIL/ICRA/CARE) for funding mix.

**Note:** BFSI financial statements differ structurally from industrials — inventory/receivable-days ratios are meaningless here; NII/PPOP/NIM and asset-quality lines replace the standard revenue/EBITDA frame.
