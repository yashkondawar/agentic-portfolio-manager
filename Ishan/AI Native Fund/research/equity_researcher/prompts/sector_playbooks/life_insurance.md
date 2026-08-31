# Sector Playbook — Life insurance

*Tier 2. Family: `bfsi` (`prompts/sector_packs/bfsi.md`). Shared rules: `prompts/31`.*
**Provenance:** corpus-grounded — LIC (BOB Capital, Apr-23, 36pp, 58 exhibits), Canara HSBC
Life Insurance (Centrum, Mar-26), an insurance sector initiation covering life and non-life
(JM Financial, Oct-24, 70pp, 103 exhibits), plus insurance sector notes from Kotak
Institutional (Jan-23) and ICICI Securities (Oct-20, Aug-21).

## The economic engine
A life insurer sells a multi-decade promise, collects the premium now, and recognises the
profit over the policy's life. **Accounting profit is therefore almost uninformative** — a fast-
growing insurer writing profitable business reports *worse* IFRS/Indian-GAAP earnings, because
new-business strain is expensed upfront. The sector solves this with its own metrics:

`Value of new business (VNB) = APE × VNB margin` — the economic profit written this year
`Embedded value (EV) = adjusted net worth + present value of in-force profits`
`Appraisal value = EV + a multiple of VNB` — what the franchise is worth

**This is the one sector in the registry where P/E is not merely inferior but wrong.** Say so in
the note if anyone has used it.

Three drivers move VNB margin, and they must be separated: **product mix** (protection and
non-par savings carry high margin; ULIPs and par carry low), **distribution mix** (proprietary
agency and direct beat bancassurance on margin, and bancassurance concentration is a standing
risk), and **persistency** (a lapsed policy destroys the VNB already booked).

## Analysis sequence
1. **Product mix by APE**, with the margin of each bucket: protection (term, credit-life),
   non-par guaranteed savings, par, ULIP, annuity, group. Then the *direction* of the mix. LIC's
   entire thesis in the BOB note is one mix shift: non-par at ~9.5% of individual APE (9MFY23)
   from ~7% (FY22), lifting VNB margin from 15.1% (FY22) toward 19% (FY25E) — a 400bps move.
2. **Distribution mix and its economics** — agency count and productivity, bancassurance
   partner concentration and the tie-up's expiry date, direct/online share. A single bank
   partner above ~50% of APE is a thesis-level dependency, not a footnote.
3. **Persistency by cohort** — 13th, 25th, 37th, 49th and **61st month**. The 61m figure is the
   one that matters, because it is the first that spans the typical premium-paying term of a
   savings product and the only one that has survived a full lapse cycle.
4. **VNB margin walk** — decompose the change into mix, expense, persistency and assumption
   effects. A margin rise from a one-off assumption change is not the same as one from mix.
5. **EV movement analysis** — unwind, VNB, operating variance, economic variance, and
   dividends. **Operating variance is the honesty check**: persistent negative operating
   variance means the EV assumptions are too kind.
6. **The assumption set itself** — discount rate, mortality/morbidity, lapse, expense
   assumptions and their history of revision. EV is a model output; the assumptions are the
   model.
7. **Solvency and capital** — solvency ratio against the 150% regulatory floor, and the growth
   it funds. Non-par guaranteed business consumes solvency faster.
8. **Then VNB, EV and the appraisal value.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **VNB margin** | VNB / APE | % | The profitability of what was sold this year. Decompose every change into mix / expense / persistency / assumptions — LIC's 400bps rise to 19% (FY25E) is a pure product-mix story and is defensible for that reason | Company disclosure |
| **APE growth** | annualised premium equivalent, YoY | % | APE = regular premium + 10% of single premium. Use APE, never gross written premium — single premium inflates GWP without proportionate economics. Also track individual-APE market share (LIC: 46% FY17 → 35%) | Company disclosure |
| **61m persistency** | policies in force at month 61 / policies issued | % | The long-cohort retention measure; the shorter buckets can be managed. Falling 61m persistency invalidates previously booked VNB | Public disclosures, decks |
| **Embedded value** | adjusted net worth + PV of in-force profits | INR bn | The valuation base. Always read with the movement analysis and the assumption set — never as a given number | EV disclosure / actuarial report |
| **Solvency ratio** | available solvency margin / required margin | x | Against the 1.5x floor. The constraint on writing capital-hungry non-par guaranteed business | IRDAI disclosure |

## Supporting KPIs
Individual and group APE split; protection share of APE; non-par share of individual APE;
ULIP share; annuity share; agent count and APE per agent; bancassurance partner concentration
and tie-up tenure; 13m/25m/37m/49m persistency; surrender ratio; expense ratio and commission
ratio against the IRDAI EoM limits; claims settlement ratio; VNB and EV per share; EV operating
return (ROEV); assumption-change contribution to EV; AUM and its debt/equity split;
new-business strain; renewal-premium growth; total premium growth.

## Standard exhibit set
APE by product with the margin of each bucket · product-mix trend (the whole thesis for most
names) · VNB and VNB-margin walk decomposed into mix/expense/persistency/assumptions ·
distribution mix by APE with partner concentration · agent count and productivity ·
persistency by cohort (13m through 61m) across several years · EV movement analysis waterfall ·
ROEV · operating variance history · assumption-revision history · solvency ratio vs the 1.5x
floor · individual-APE market share vs private peers and LIC · AUM mix · P/EV band ·
appraisal-value build (EV + n × VNB) · valuation vs peers on P/EV against ROEV.

## Valuation convention
**P/EV, or an appraisal value = EV + a multiple of VNB. Never P/E, never P/B.** LIC (BOB
Capital): BUY, TP INR 800 at **0.7x FY25E P/EV** — a sub-1x P/EV is itself the argument, and the
note has to explain why the market discounts the stated EV (state ownership, par-fund surplus
distribution, agency dependence) rather than simply observing the discount. That distinction is
the re-rating test in `docs/ER_CORPUS_FINDINGS.md` §6 applied to this sector.

The appraisal-value form (EV + n × VNB) is the more analytically honest one because it separates
the in-force book from the franchise's ability to write new business, and it forces an explicit
view on VNB durability.

*Traps:* (i) **taking EV at face value** — it is the output of an assumption set with a
revision history; check operating variance before trusting it; (ii) valuing a mix-shift thesis
before the mix has shifted, when the margin gain is still a plan; (iii) ignoring
bancassurance-partner expiry, which can remove a third of APE on a known date;
(iv) capitalising a VNB margin lifted by a one-off assumption change; (v) using GWP or total
premium growth as the growth rate — single-premium and group business distort both;
(vi) comparing P/EV across insurers whose EV assumptions differ materially without adjustment.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It trades at 0.7x FY25E embedded value.**
- *Cheap* (`own_history_anchor`) — below 1x means the market values the in-force book at
  less than its stated worth, which for a run-off asset is close to arithmetically odd.
- *The EV itself is what is being discounted* (`earnings_base_quality`) — LIC (BOB Capital,
  BUY, TP INR 800 at 0.7x) is the corpus case, and the note's burden is to explain *why*
  the market discounts the stated EV: state ownership, par-fund surplus distribution,
  agency dependence. Simply observing the discount is the F1 re-rating failure.
- *Discriminator* (`disclosed_mechanism`) — the EV sensitivity table, and the shareholder's
  contractual share of par surplus.

**2. VNB margin is 27%, up 400bps.**
- *Durable mix shift* (`disclosed_mechanism`) — protection and non-par rising in the mix.
- *A reset* (`growth_durability`) — a pricing action or a channel push that does not repeat.
- *Discriminator* (`disclosed_mechanism`) — the product-and-channel mix bridge behind the
  margin move. The appraisal-value form (EV + n x VNB) is the more honest presentation
  precisely because it forces an explicit view on VNB durability rather than burying it.

## Forensic screens (sector-specific)
- **Persistency falling while APE grows** — new business is being written over a leaking book,
  and the previously booked VNB is being reversed in economics if not in accounting.
- VNB margin rising in the same period as an assumption revision — separate the two or the
  margin story is unproven.
- Persistently negative **operating variance** in the EV movement: the assumptions are optimistic
  and the EV is overstated.
- Group/credit-life APE surging — it is often low-margin, single-premium, lender-tied volume
  that flatters growth and is lost when the lending relationship ends.
- Single-premium business inflating GWP-based growth claims.
- Expense overrun against IRDAI's expenses-of-management limits, or expenses pushed into a
  subsidiary/related entity.
- Bancassurance commission structures with the parent bank — a related-party arrangement that
  distorts the expense comparison against unparented peers.
- Surrender and free-look cancellation rates rising in a product being pushed hard.
- Par-fund surplus distribution policy changing (particularly relevant to LIC's shareholder
  economics).
- Reinsurance arrangements that flatter the protection margin; check retention levels.

## Dependencies to map
IRDAI — product-approval regime, expenses-of-management limits, surrender-value regulations
(the 2024 revision is the template for a rule change repricing a whole product line), solvency
norms and the proposed risk-based capital transition · the tax treatment of insurance proceeds
(the Feb-23 Budget's INR 5 lakh non-ULIP premium cap directly repriced the non-par savings
opportunity — this is the sector's clearest example of fiscal policy as a demand driver) ·
interest rates and the yield curve (non-par guaranteed products carry real ALM and reinvestment
risk) · equity markets for ULIP flows and for EV's economic variance · bancassurance regulation
and open architecture · mortality/morbidity experience and reinsurance pricing · pension and
annuity policy (NPS, EPS) · Ind AS 117 adoption timing, which will change the reported-earnings
frame this playbook currently works around.

## Common archetypes here
`margin-expansion` (the product-mix shift — by far the most common and, when the mix is
actually moving, the most defensible), `regulatory-tailwind` or its inverse, `re-rating`
(especially for sub-1x-P/EV names, where the mechanism for the discount closing must be named),
`quality-compounder` for franchises with genuine proprietary distribution, and
`special-situation` for demergers and stake sales. `deep-value-sotp` appears where a listed
insurer sits inside a bank or holdco — value the stake, apply the holdco discount, and publish
the implied blended multiple.
