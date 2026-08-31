# BFSI — Sector Playbook (Banks, NBFCs, HFCs, MFIs, Insurers, capital-market infra)

Synthesized superset of `registry/kpis/bfsi.yaml` (qualitative_checks,
cycle_overlap_checks, niche_pointers) and the external ER project's BFSI
sector pack. KPI vocabulary: `registry/kpis/bfsi.yaml`; deep KPI
definitions: `knowledge/data/kpis/micro/bfsi.yaml`. Sector cycle index:
NIFTY BANK (primary), NIFTY FINANCIAL SERVICES (broader read) — see
`config/settings.yaml -> sector_index_map`.

## Core truth

Lenders win by pricing the next rupee of risk correctly; sustainable
ROA/ROE comes from liability franchise + underwriting, not growth. Book
value quality (true provisioning, through-cycle stability) is the real
number under the printed number.

## Qualitative lenses

- **Liability franchise**: CASA quality and stickiness, cost-of-funds
  trajectory, wholesale-funding reliance (CP dependence for NBFCs) and
  ALM pressure under rate moves; digital acquisition cost benchmarking.
- **Asset mix & underwriting**: secured vs unsecured mix across peers,
  segment seasoning, collection efficiency, restructured-book history.
- **Book value quality**: true loan-loss provisioning and through-cycle
  stability underlying ROA/ROCE — the printed P/B is only as good as the
  provisioning behind the B.
- **Regulatory moat & risk**: RBI/IRDAI/SEBI posture (licenses,
  digital-lending rules, Basel/capital norms); recent or impending
  regulation from RBI/SEBI papers.
- **Upstream/downstream flow**: marginal cost of funds (especially NBFC
  reliance on the commercial-paper market) vs core CASA on the liability
  side; collection efficiency and capital-deployment efficiency against
  risk-weighted assets on the asset side.
- **Porter's read**: rivalry priced on the next rupee of lending/deposit;
  bargaining power of depositors/wholesale money markets and sensitivity
  to RBI rate moves (ALM pressure).
- **Stress tests**: use publicly available stress-test results on loan
  books where published.

## Cycle overlay

- **Valuation vs earnings cycle**: is the current P/B premium/discount
  justified by ROA/ROE stability, or driven purely by the valuation cycle
  (investor enthusiasm)? Run the sector's own eight-phase read on NIFTY
  BANK P/E-P/B percentiles (`index_data` now carries ~2016-onward
  history) before answering.
- **Credit-cycle stage vs book quality**: easy-money vintages sour later
  — check vintage disclosures; how do peers handle ALM pressure from
  wholesale-funding reliance? Cross-read with `credit_debt_cycle` anchors
  (`knowledge/data/cycles/catalog.yaml`).
- **Policy/profit cycle**: if enjoying a regulatory moat, assess
  political risk and long-term sustainability, including receivable-day
  exposure to government counterparties.

## Niche pointers

- **Life insurers**: VNB margin (protection vs savings mix), growth in
  non-par protection, persistency, solvency ratio.
- **HFCs**: interest-rate sensitivity; regional property registration
  volume trends.
- **MFIs / rural lenders**: state concentration; explicit exposure and
  resilience to political risk from state-level loan waivers.
- **AMCs / depositories / exchanges**: take rates, market-linked volumes,
  float income.

## Relative-valuation justifier

P/B premium/discount vs sustained ROA/ROE and book-value quality —
include the P/B-vs-ROE cross-sectional read across peers (who's off the
regression line and why).

## Preferred sources

RBI DBIE & circulars, IRDAI, company investor decks (NIM/GNPA walk
slides), exchange filings, rating-agency reports (CRISIL/ICRA/CARE) for
funding mix.

## Extraction note

BFSI financial statements differ structurally from industrials —
inventory/receivable-days ratios are meaningless here; NII/PPOP/NIM and
asset-quality lines replace the standard revenue/EBITDA frame.
