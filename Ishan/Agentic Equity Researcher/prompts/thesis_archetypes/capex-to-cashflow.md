# Archetype — Capex to cashflow

**Skepticism weight: 3 (medium).**

## Definition
A heavy investment phase is ending. Capacity commissioned during it now generates
earnings while capex falls back to maintenance levels, so free cash flow inflects sharply.

## Return source
FCF inflection — and, usually, the balance-sheet and payout consequences of it. Often
pairs with `balance-sheet-repair.md`.

## `must_be_true`
1. **The capex programme is disclosed and dated**, project by project, with investment,
   status and commissioning date.
2. **Maintenance capex is separately estimated**, so the post-programme run-rate is a
   number rather than an assumption. Typically anchored to depreciation or to historical
   pre-programme capex/sales.
3. **The new capacity's incremental returns are estimated** — asset turns and incremental
   ROCE implied by the capex, sanity-checked against the existing asset base.
4. **Ramp is modelled, not switched on.** New capacity contributes from the disclosed
   commissioning date at ramped utilisation, not at full utilisation from day one.
5. **No follow-on programme is already announced.** Serial capex companies never reach
   the inflection; check the transcript for the next phase.

## Standard evidence pattern
Project pipeline table (project · investment · status · commissioning) → gross block
walk → utilisation path → maintenance capex estimate → FCF bridge → net debt walk →
implied incremental ROCE.

## Standard failure mode
**The inflection that keeps receding**, because a new programme is announced each time
the last one completes. Second: **commissioning slippage** — the whole thesis is a date,
and dates in Indian infrastructure and heavy industry slip routinely.

## Falsifiers
- A new capex programme announced before the current one has generated a full year of FCF.
- A commissioning date slips more than two quarters, or capex overruns >15-20%.
- Utilisation on the new asset materially below the ramp assumption.
- Working capital absorbs the FCF that the P&L generates.

## Sectors where it recurs
Cement, metals, chemicals, hospitals, hotels, renewables, city gas, paper, sugar.

## Corpus note
The existing agent already has the right instinct here: `prompts/41` requires a capex /
growth-project pipeline table, and the NALCO run flagged commissioning slippage and CWIP
concentration as monitorables. This archetype turns that into a thesis-level test.
