# Sector Playbook — Real estate developers & annuity landlords

*Tier 2. Family: `infra_capital_goods` (`prompts/sector_packs/infra_capital_goods.md`). Shared rules:
`prompts/31`.*
**Provenance:** corpus-grounded — Brigade Enterprises (JM Financial, Dec-25 — a full SOTP with DCF on the
residential business and cap-rate valuation of operational annuity assets, plus the EV/pre-sales peer
table), Phoenix Mills (ICICI Securities, Dec-18 — the retail-mall annuity model), Smartworks Coworking
(Choice Broking, Dec-25 — the managed-office model), with `hotels` as the authored sibling for the
hospitality leg that many developers carry.

## The economic engine
**A developer's accounting revenue and its actual business are years apart, and this is the one fact from
which the whole playbook follows.** Under Ind AS 115, residential revenue is recognised on *completion*
(or handover), while cash arrives during construction against milestones. So:

`Pre-sales (bookings) = area sold × realisation per sqft` ← **the real business, happening now**
`Collections` ← **the cash, arriving over 2-4 years**
`Reported revenue` ← **an accounting echo of pre-sales made 3-4 years ago**

> **Therefore P/E is meaningless for a residential developer**, and a note that leads with earnings growth
> has misunderstood the asset. Lead with pre-sales, collections and the cash flow.

There are two distinct businesses here, usually inside one company:

1. **Residential development** — a working-capital-intensive manufacturing cycle: buy land, obtain
   approvals, launch, sell, build, hand over. Value = NPV of the project pipeline's cash flows.
2. **Annuity assets** — offices, malls, warehouses, hotels held for rent. Value = stabilised NOI ÷ cap
   rate. These are bond-like and are valued the way property is valued, not the way a developer is.

Brigade's structure is the corpus's worked example and it is the correct one: **the residential business
valued on a DCF of expected cash flows, the operational commercial assets valued separately, and the
hotels business separately again**, summing to a Mar'27 TP of INR 1,020.

**The industry cycle matters and it is not smooth.** Pre-sales for the sector compounded at ~14% over
FY19-24, then "the industry took a breather as bookings declined by 8% YoY in FY25 due to lingering
challenges in approvals and sharp price hikes in certain pockets" — while inventory stayed comfortable and
absorption exceeded new supply. **That combination — falling bookings with low inventory — is a
price-resistance signal, not a supply glut**, and distinguishing the two is the central cyclical judgement
in this sector. Note also the consolidation: the top-14 listed developers have been gaining pre-sales
share, which is the sector's genuine structural story post-RERA.

## Analysis sequence
1. **Pre-sales, decomposed** — booking value, **area sold (msf)** and **realisation per sqft**, as three
   series, by city and by project. Value growth that is entirely realisation is price, and price growth
   is what triggered FY25's booking decline.
2. **Collections and the cash-flow bridge** — collections against pre-sales, construction spend, land
   spend, and net operating surplus. **Operating cash flow is the honest performance measure here**, not
   revenue or PAT.
3. **The launch pipeline and its readiness** — projects launched, launch-ready (approvals in hand), and
   the land bank behind them. Distinguish approved-and-launchable from land held. Brigade's ~31 msf
   residential pipeline share is the kind of figure to establish, along with which city it sits in
   (Bengaluru concentration, in that case).
4. **Unsold inventory and its quality** — unsold area by project and by vintage, months-of-inventory at the
   current sales rate, and completed-unsold stock (the worst kind, because it consumes carrying cost with
   no construction-linked collections).
5. **Business development (land acquisition)** — msf and GDV added, the acquisition structure (outright
   purchase / JDA / JV / DM), and the cost. **A JDA is not a purchase**: the landowner takes a revenue or
   area share, which lowers capital intensity and lowers margin. Get the mix.
6. **Annuity portfolio, separately** — operational, under-construction and planned area; occupancy;
   in-place rent per sqft vs market; WALE (weighted average lease expiry); tenant concentration and
   sector mix; rent escalation clauses; and NOI. Then the cap rate applied.
7. **Balance sheet and the surplus test** — net debt, cost of debt, and **net debt to operating surplus**,
   which is the sector's leverage measure because EBITDA is an accounting artefact. Plus the REIT/InvIT
   monetisation option for stabilised annuity assets.
8. **Approvals, RERA registrations and litigation** — project-level RERA status, completion timelines
   against RERA commitments, and any title or land-litigation exposure.
9. **Then SOTP: DCF the residential pipeline, cap-rate the annuity assets, value hotels separately.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Pre-sales** | booking value in the period | INR cr | **The real business.** Always decomposed into area sold and realisation per sqft, and reported by city. Sector context: ~14% CAGR FY19-24, then −8% in FY25 on price resistance | Company disclosure |
| **Realisation per sqft** | pre-sales value / area sold | INR/sqft | The price variable, and the one that caused FY25's booking decline when pushed too hard. Split like-for-like price from project/city mix — a shift to a premium micro-market raises realisation without any price increase | Computed |
| **Area sold** | area booked in the period | msf | The volume measure. **Pre-sales growth carried entirely by realisation with flat or falling area sold is price-led and self-limiting** — the sector's FY25 lesson in one metric | Company disclosure |
| **Collections** | cash collected from customers | INR cr | The cash reality. Track the collections-to-pre-sales ratio and the ageing of receivables from sold units; a widening gap means construction milestones are slipping | Company disclosure |
| **Net debt to operating surplus** | net debt / (collections − construction − land − overhead − interest) | x | **The right leverage measure**, because EBITDA and PAT are accounting echoes. Brigade's own framing pairs balance-sheet capacity with the ability to fund land acquisition and capex | Computed |

## Supporting KPIs
Pre-sales by city and by project; area sold by city; launches in the period (msf and GDV);
launch-ready inventory (approvals in hand); land bank in msf and its GDV; business development added
(msf, GDV, structure: outright / JDA / JV / DM); JDA revenue-share terms; unsold inventory by project and
vintage; months of inventory; completed-unsold stock; average project cycle time; construction spend and
its per-sqft cost; customer receivables from sold units; net operating surplus; net debt, cost of debt and
the debt maturity profile; **annuity portfolio:** operational / under-construction / planned area,
occupancy, in-place rent per sqft vs market rent, WALE, tenant sector mix and top-10 tenant concentration,
rent escalation terms, NOI and NOI margin, cap rate; retail malls: trading occupancy, consumption growth,
rent-to-sales ratio, minimum-guarantee vs revenue-share rent split; hotels: keys, ARR, occupancy (apply
`hotels`); REIT/InvIT-eligible stabilised assets and their implied value; promoter pledge; ROE and RoCE
computed on invested capital rather than accounting equity.

## Standard exhibit set
**Pre-sales decomposed into area sold and realisation per sqft, by city** (the sector's defining exhibit) ·
pre-sales vs collections vs reported revenue as three series — showing the multi-year lag explicitly ·
the operating-cash-flow bridge: collections − construction − land − overhead − interest · launch pipeline
with approval status and expected launch dates · land bank and GDV with acquisition structure ·
business-development additions by year · unsold inventory by project and vintage, with months-of-inventory ·
completed-unsold stock trend · industry pre-sales growth and the top-14 developers' share (the
consolidation story) · city-level absorption vs new supply and inventory months · **annuity portfolio
table: asset, area, occupancy, in-place vs market rent, WALE, NOI** · rent escalation schedule ·
tenant sector mix and concentration · net debt and net-debt-to-operating-surplus · debt maturity ·
**the SOTP table: residential DCF + annuity at cap rate + hotels**, with the cap rate and discount rate
stated · EV/pre-sales and EV/EBITDA peer comparison (both, per Brigade's peer table) · NAV per share build.

## Valuation convention
**SOTP — NAV/GAV of the residential pipeline (or a DCF of its cash flows), plus annuity assets at a cap
rate, plus any hotels valued on their own convention. P/E is meaningless.**

Brigade (JM Financial) is the template: *"We value the company on an SoTP basis… Residential business is
valued using DCF of expected cash flows; its operational commercial assets are valued at…"* with hotels
treated separately, producing a Mar'27 TP of INR 1,020. Note also that the peer table runs **EV/pre-sales
alongside EV/EBITDA** — EV/pre-sales is the sector's cleanest cross-sectional comparator precisely because
it sidesteps the revenue-recognition lag.

**State every input the SOTP rests on:** the discount rate on residential cash flows, the cap rate on each
annuity asset class (offices, retail and warehousing do not share a cap rate), the assumed price
escalation, and the assumed sales velocity. A developer NAV is highly sensitive to velocity and price
assumptions, so **publish a sensitivity table on those two** — this is one sector where
`prompts/32`'s sensitivity mandate is genuinely load-bearing rather than a formality.

*Traps:* (i) **using P/E, or reading reported revenue growth as performance** — the defining error;
(ii) valuing the full land bank at current realisations when much of it lacks approvals and will be
monetised over 10-15 years — apply a discount for time and approval risk, and disclose the assumption;
(iii) treating a JDA project's full GDV as the company's, ignoring the landowner's share; (iv) applying
one cap rate across offices, malls and warehousing; (v) crediting under-construction annuity assets at
stabilised NOI; (vi) ignoring completed-unsold inventory's carrying cost; (vii) capitalising a
peak-velocity year (FY24) or extrapolating FY25's decline without diagnosing whether it was price
resistance or demand loss.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It trades at 60x earnings.**
- *Absurd* (`peer_set_choice`).
- *Meaningless, not absurd* (`accounting_basis`) — revenue recognition lags pre-sales by
  years, so P/E measures a past project cycle against a present market cap. The convention
  is SOTP: NAV/GAV of the residential pipeline (or a DCF of its cash flows), plus annuity
  assets at a cap rate, plus hotels on their own convention.
- *Discriminator* (`disclosed_mechanism`) — pre-sales against recognised revenue, with
  EV/pre-sales as the cross-sectional comparator. Brigade's peer table (JM Financial) runs
  EV/pre-sales alongside EV/EBITDA precisely because it sidesteps the recognition lag.

**2. The stock trades at 0.8x stated NAV.**
- *A 20% discount, therefore cheap* (`own_history_anchor`).
- *The NAV is an output, not a fact* (`terminal_value_share`) — it rests on a discount rate
  on residential cash flows, a cap rate on each annuity asset, and a launch schedule. Move
  any one and the NAV moves further than the discount does.
- *Discriminator* (`disclosed_mechanism`) — state every input the SOTP rests on and
  sensitise them. An unsensitised NAV cannot support a discount argument.

## Forensic screens (sector-specific)
- **Pre-sales growth entirely from realisation with flat or falling area sold** — price-led, and the FY25
  sector decline shows where that ends.
- Pre-sales including a project's full value where the company holds a partial share (JDA/JV) — check
  whether disclosure is company-share or gross.
- Cancellations netted quietly, or the cancellation rate undisclosed; pre-sales restated downward without
  comment in a later period.
- **Collections lagging pre-sales widely** — construction milestones are slipping, or customers are
  defaulting; check receivables from sold units and their ageing.
- Revenue recognised on handover accelerated by handing over incomplete units, or occupancy certificate
  timing managed across a year-end.
- Unsold inventory not aged; completed-unsold stock disclosed only in aggregate.
- Land advances and "deposits toward land" sitting in other assets for years — a JDA or purchase that
  never closed, or an impaired advance.
- Interest capitalised into inventory beyond the permitted period, or on projects where construction has
  paused — this flatters both the P&L and the project margin.
- Project-level margins computed on land at historical cost, presenting inflation as development margin.
- Annuity assets revalued upward with the gain routed through the P&L or reserves; cap rate assumption
  changed between periods.
- Under-construction annuity assets counted at stabilised NOI; occupancy quoted as "leased" (including
  letters of intent) rather than as rent-paying.
- Related-party transactions: land purchased from promoter entities, construction contracts to
  promoter-owned contractors, project-management fees to a promoter entity.
- SPV/subsidiary debt and guarantees outside the headline net-debt figure; a REIT/InvIT transfer presented
  as operating cash flow.
- RERA completion commitments already breached, with penalty exposure not provided.
- Promoter pledging; group-company obligations serviced by the listed entity.

## Dependencies to map
Home-loan interest rates and mortgage availability — the primary residential demand driver (link to
`housing_finance`) · household income and the affordability ratio in each target micro-market ·
**city-level absorption, new supply and inventory months** — the sector is hyper-local, so national data
is nearly useless (the same discipline `hotels` and `cement` require) · **approval timelines**, which
FY25's booking decline was partly attributed to: RERA registration, environmental clearance, CC/OC issuance
and municipal approvals · stamp duty and registration charges, and any state concession · GST on
under-construction property and input-tax-credit treatment · RERA enforcement and its consolidation
effect — the structural reason the top-14 listed developers keep gaining share · construction cost
inflation (steel, cement, labour) and its effect on project margins already sold · SARFAESI/IBC-driven
distressed land supply · **office-leasing demand, especially GCC expansion**, and the return-to-office
trend for the annuity leg · retail consumption growth for malls · warehousing demand and 3PL expansion
(link to `logistics`) · REIT/InvIT market depth and prevailing cap rates, which set the exit value for
annuity assets · FDI and private-equity capital availability for platform deals · land-title digitisation
and litigation timelines.

## Common archetypes here
`capex-to-cashflow` (the launch pipeline converting to collections — the dominant archetype, and the one
whose cash bridge must be shown) · `market-share-gainer` — **unusually well-evidenced in this sector**,
since post-RERA consolidation toward the top-14 listed developers is a documented industry shift, not a
company claim · `deep-value-sotp` (NAV discount, common where the market prices a developer on earnings
and ignores the annuity portfolio) · `balance-sheet-repair` and `turnaround` for the post-2018 NBFC-crisis
survivors · `margin-expansion` where the mix shifts to premium or to annuity income · `cyclical-recovery`
and `cyclical-peak` on the residential cycle — and note that FY25's −8% booking decline makes cycle
positioning an explicit requirement here, not an optional flourish. Treat `re-rating` and
`quality-compounder` with the standard skepticism weight: a developer compounds only if it can keep
replacing land at returns above its cost of capital, and that must be shown through the
business-development track record across a cycle.
