# Sector Pack — Banking, Financial Services & Insurance *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in
`prompts/sector_playbooks/` carries the KPI table, the valuation convention, the exhibit set
and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the
two differ.** Shared research rules: `prompts/31`. Routing source of truth:
`config/sector_registry.yaml`.*

**Family scope:** any business whose product is money or risk — banks, NBFCs, HFCs, MFIs,
life and general/health insurers, AMCs, and capital-market infrastructure.

## Statement fork — the one thing every child inherits

`families.bfsi.bfsi_statements: true`. This is structural, not cosmetic:

- Extraction uses the **BFSI addendum** in `prompts/10` (NII, advances/deposits or AUM,
  GNPA/NNPA/PCR, CAR/CET-1, and the insurer/AMC equivalents) rather than the manufacturing
  P&L tree.
- `tools/compute_ratios.py --family bfsi` suppresses the ratios in
  `families.bfsi.skip_ratios` — inventory/receivable/payable days, cash-conversion cycle,
  EBITDA margin, EV/EBITDA, asset turnover. A lender has no inventory and no meaningful
  EBITDA; computing them produces confident nonsense that then contaminates the peer table.
- **EV/EBITDA and P/E are the wrong family of multiple** for anything this leveraged. Which
  multiple *is* right differs by child — see the playbook.

## What the whole family genuinely has in common

Only these four are cross-cutting. Everything else is child-specific and lives in the playbook.

- **Leverage makes capital the growth constraint.** Growth is funded by capital, not by
  retained cash flow alone, so a growth forecast that ignores the capital raise it implies is
  incomplete. Always ask what the plan does to the capital ratio and whether a raise is
  already announced.
- **The regulator sets the perimeter.** RBI (banks, NBFCs, upper-layer classification,
  digital-lending and risk-weight changes), NHB (housing finance), IRDAI (insurers), SEBI
  (AMCs, market infrastructure), MFIN self-regulation (microfinance). A rule change can
  reprice an entire book, and the regulator is usually the largest exogenous risk.
- **Earnings are an estimate, not a measurement.** Provisioning is a judgement, so reported
  profit embeds a management choice about the future. This is why the family needs the
  earnings-quality and governance modules harder than any other, and why a through-cycle
  record matters more than any single year.
- **Cycle overlay.** Credit and underwriting cycles are long, and the good years look
  structural from inside them. Position the current year against a full cycle before
  extrapolating anything.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Covers | Unit lens |
|---|---|---|
| `banks_private` | scheduled commercial banks with a deposit franchise | per ₹ of average assets |
| `nbfc_diversified` | multi-product retail NBFCs | per ₹ of average AUM |
| `housing_finance` | HFCs, long-tenor secured mortgage books | per ₹ of average AUM |
| `microfinance` | JLG/MFI lending | per borrower |
| `life_insurance` | life insurers | per policy |
| `general_health_insurance` | general and health insurers | per policy |
| `amc_capital_market_infra` | AMCs, exchanges, depositories, RTAs | per ₹ of AAUM |

Multi-line financial groups (a bank with an AMC and an insurance arm): primary = the
largest-EBIT line's playbook; list the others as `secondary_playbooks` and pull only their
KPI tables. A holdco over several regulated subsidiaries is usually a
`special-situation`/SOTP thesis — see `prompts/thesis_archetypes/`.

**All seven children are `status: authored`** (as of 2026-08-03), so triage resolves to a tier-2
playbook and that playbook governs. The degradation path survives only for future registry
additions: if a child is ever marked `status: pending`, analyse on this pack plus the closest
authored sibling (`nbfc_diversified` for any lender, `life_insurance` or
`general_health_insurance` for a risk carrier), state in the note which convention you borrowed,
and do **not** fall through to `generic`.

## Preferred sources for this family

RBI DBIE and circulars, NHB, IRDAI, SEBI, MFIN/CRIF bureau data, rating-agency reports
(CRISIL/ICRA/CARE) for funding mix and rating history, and the company's own NIM/GNPA walk
slides. Per-child source notes live in the playbook.
