# Sector Playbook — Electronics manufacturing (EMS / ODM)

*Tier 2. Family: `auto_engineering` (`prompts/sector_packs/auto_engineering.md`). Shared rules:
`prompts/31`.*
**Provenance:** corpus-grounded — Dixon Technologies (Emkay Global, Jan-25 — the corpus's clearest
statement of the assembly-vs-component margin gap and the backward-integration thesis), EPACK Durable
(ICICI Securities, Dec-24), LG Electronics India (ICICI Securities, Oct-25 and Elara Capital, Mar-26 —
the brand-owner counterparty view), with Amber-adjacent durables content from Eureka Forbes (Nuvama,
Sep-25).

## The economic engine
An EMS company **rents manufacturing capacity to a brand owner.** It buys the bill of materials, puts
it together, and keeps a few percent:

`Revenue = units × ASP` , `Gross margin ≈ 5-10%` , `EBITDA margin ≈ 3-6%`

Two consequences dominate everything, and they are what make this playbook different from
`auto_ancillary`:

- **Margins are razor-thin, so the business is a working-capital and asset-turn business, not a margin
  business.** Return on capital is earned by turning inventory fast on a thin spread. A 100bps margin
  move is a 20-30% earnings move, so **the forecast risk is asymmetric and the balance sheet is the
  real constraint.** Growth is funded by working capital, which is why receivable and inventory days
  are thesis-critical rather than housekeeping.
- **The value ladder is the whole strategy, and the corpus quantifies it.** Dixon's note contrasts
  **~3.5% margin in assembly against double-digit margin in manufacturing/components**, and the
  display JV with HKC is cited as commanding **over 20% gross margin**. So:

> **Climbing from assembly → ODM → components is not incremental improvement; it is a change of
> business model, and it is where every rupee of re-rating in this sector comes from.**

The ladder, in ascending order of value capture: **CM/SMT contract assembly** (brand supplies design and
often materials) → **EMS** (own procurement, still brand's design) → **ODM** (own design — the brand
buys a finished product) → **component manufacture** (display modules, PCBs, mechanicals, camera
modules) → **backward-integrated component + ODM**. Establish where revenue actually sits, and where
the *incremental* revenue is going.

**Policy is the reason this industry exists in India, and it is dated.** The PLI schemes are the moat's
foundation: Dixon's thesis rests on a **Rs 170bn IT-hardware PLI** and an anticipated **~Rs 250-400bn
component PLI**, alongside four anchor brands (HP, Acer, Lenovo and one other) and import
substitution. **Every scheme has a term, localisation thresholds, and a claw-back — find the dates and
the conditions, and ask what the economics look like afterwards.** This is the same discipline
`renewables` applies to ALMM/DCR.

## Analysis sequence
1. **Place revenue on the value ladder** — CM/EMS vs ODM vs components — by revenue *and* by gross
   profit. Then the same split for incremental revenue over the forecast period. A company at 90%
   assembly claiming an ODM re-rating has not earned it yet.
2. **Vertical mix and each vertical's own cycle** — mobile, consumer electronics (TV), lighting, home
   appliances (RAC, washing machines), IT hardware (laptops, servers), wearables, telecom, auto
   electronics. Each has different ASPs, seasonality, margins and customer structures.
3. **Customer concentration and the contract's shape.** Top-5 share, and for each major customer:
   who owns the design, who bears BOM price risk, who owns the inventory, the payment terms, and
   whether there is a volume commitment. **In pure assembly the customer often supplies materials —
   check whether revenue is gross or net, because it changes the margin denominator entirely.**
4. **The working-capital engine, in detail.** Inventory days (raw material / WIP / finished goods
   separately), receivable days by customer, payable days, and the cash-conversion cycle. Then ask how
   the next year's growth is funded — this is where EMS companies fail.
5. **Backward-integration progress, with margin attached.** Which components are made in-house, at what
   margin, and what the capex and JV structure is (Dixon's HKC display JV is the template). Quantify the
   margin rub-off: assembly at ~3.5% blending toward components in double digits is arithmetic the note
   should show.
6. **PLI and incentive economics** — scheme, tranche, eligibility thresholds met, incentive accrued vs
   received, the scheme's end date, and the localisation/value-addition requirement. **Then compute
   EBITDA excluding PLI**, because that is the post-scheme run-rate.
7. **Capacity, utilisation and SMT line count**, with the customer-specific vs fungible split. Capacity
   dedicated to one brand is a concentration risk disguised as an asset.
8. **Import-substitution and localisation depth** — value addition as % of ASP, which is both the PLI
   qualifying metric and the honest measure of how much manufacturing is really happening.
9. **Then ROCE (the correct lens for a thin-margin, fast-turn business), and the multiple.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **ODM revenue share** | ODM (own-design) revenue / total revenue | % | **The value-ladder position, and the single best predictor of margin.** Dixon's contrast — ~3.5% in assembly vs double-digit in manufacturing/components — is why. Report ODM, EMS and component shares separately, and the share of *incremental* revenue | Decks, segment disclosure |
| **Inventory turns** | COGS / average inventory | x | On a 3-6% margin, the return comes from turns, not from spread. Split raw material / WIP / finished goods — component obsolescence is fast and real in electronics | Computed |
| **Customer concentration (top-5)** | top-5 customer revenue / total revenue | % | Structural, and higher than in `auto_ancillary` — often one brand is 30-50% of a vertical. Read with the contract's design-ownership and BOM-risk terms, and with the fungibility of the capacity built for that customer | AR, decks |
| **Capacity utilisation** | production / installed capacity (or SMT line-hours used / available) | % | Operating leverage on a fixed line cost, and the constraint on winning new programmes. Note the customer-dedicated share, which is not fungible | AR, decks |
| **Working capital days** | inventory + receivable − payable days | days | **The growth constraint and the thesis risk.** Thin-margin growth funded by working capital consumes cash; a rising cycle alongside rising revenue is how EMS companies get into trouble | Computed |

## Supporting KPIs
Revenue and gross profit by vertical; revenue by value-ladder tier (CM / EMS / ODM / components); ASP and
units by vertical; gross margin by vertical and by tier; value addition as % of ASP (the localisation
and PLI qualifying metric); in-house component revenue and its margin; JV structure and the JV's
margin (Dixon-HKC: >20% gross margin on displays); PLI scheme, tranche, thresholds met, incentive
accrued vs received, and the scheme end date; **EBITDA and PAT excluding PLI**; SMT line count and
capacity by plant; capacity dedicated per customer; capex and capex per line; import content as % of BOM;
forex exposure on imported components and the hedging policy; receivable days by customer; payable days
and any supply-chain-financing arrangement; inventory ageing and obsolescence provision; net debt and
net debt/EBITDA; interest cover; ROCE, ROIC and fixed-asset turnover; design/R&D headcount and R&D as %
of revenue (the ODM capability proxy); new-programme wins with start-of-production dates; warranty and
rework provisioning; scrap/yield rates.

## Standard exhibit set
Revenue and **gross profit** split by value-ladder tier, with margin by tier (the exhibit that carries
the whole thesis) · revenue mix by vertical with each vertical's margin · share of *incremental* revenue
by tier · ASP and units by vertical · **the margin bridge from assembly toward components**, showing the
blend arithmetic explicitly · backward-integration roadmap with capex, JV structure and margin per
component · **PLI table: scheme, tranche, threshold, incentive accrued, end date** · EBITDA with and
without PLI · customer concentration with contract terms (design ownership, BOM risk, payment terms) ·
capacity and utilisation by plant with the customer-dedicated share marked · **working-capital cycle
decomposed into inventory / receivable / payable days, against revenue growth** · inventory ageing and
obsolescence provision · value addition as % of ASP against the PLI requirement · import content and
forex exposure · net debt and the funding plan for the next growth year · ROCE, ROIC and asset turns ·
EV/EBITDA and P/E bands · peer table on ODM share, working-capital cycle and ROCE, not on multiples alone.

## Valuation convention
**P/E on forward EPS with a PEG cross-check**, and the premium justified by the value-ladder position and
the working-capital discipline — not by revenue growth, which in a 3-6% margin business is the cheapest
thing to buy.

Dixon is the corpus's data point and it is a demanding one: a TP of **Rs 20,000 implying ~41x Dec-26E
EV/EBITDA**. A multiple at that level is not a statement about current earnings; it is a statement that
the company will climb the ladder. So the note's own logic is the right structure to replicate — the
premium is defended by (a) the backward-integration/component foray and its "right-to-win", (b) PLI
success where competitors struggled, and (c) the display JV's >20% gross margin against ~3.5% in
assembly. **Each of those is checkable, and a note awarding this multiple must check them rather than
assert them.**

**Always publish the multiple on EBITDA excluding PLI as well.** An incentive with an end date should
not be capitalised in perpetuity; showing both is the honest presentation and it is the same discipline
`renewables` requires for policy-protected spreads.

*Traps:* (i) **capitalising PLI income in perpetuity** — the sector's defining error, since the schemes
have terms; (ii) valuing announced verticals or JVs before revenue; (iii) applying a component
manufacturer's multiple to an assembler's earnings; (iv) forecasting margin expansion without the
mix arithmetic that produces it; (v) ignoring that growth consumes working capital, so a
revenue-CAGR-driven target may require equity the model does not show; (vi) gross-vs-net revenue
recognition making margins incomparable across peers (a free-issue-material arrangement shows a much
higher margin on much lower revenue for identical economics); (vii) using a global EMS peer set
(Foxconn/Flex trade on very different growth and policy support).

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. The target implies ~41x Dec-26E EV/EBITDA.**
- *Absurd for a 3-6% margin assembler* (`peer_set_choice`) — Dixon's TP of Rs 20,000 is the
  corpus's demanding case.
- *Not a statement about current earnings at all* (`growth_rate`) — a multiple at that level
  is a statement that the company climbs the value ladder. The note's own defence is the
  right structure to replicate: the backward-integration and component foray and its
  right-to-win, PLI success where competitors struggled, and the display JV's >20% gross
  margin against ~3.5% in assembly.
- *Discriminator* (`disclosed_mechanism`) — the dated ladder: which component, which
  qualification, which margin, by when.

**2. Revenue grew 50%.**
- *The growth justifies the multiple* (`growth_rate`).
- *The cheapest thing to buy in this business* (`incremental_roce`) — in a 3-6% margin
  business revenue growth costs almost nothing to acquire; the premium is justified by the
  value-ladder position and working-capital discipline, not by the top line.
- *Discriminator* (`peer_distribution`) — a PEG cross-check alongside cash conversion and
  net working-capital days. Growth funded by stretching the balance sheet is not growth.

## Forensic screens (sector-specific)
- **Revenue recognised gross where the customer supplies materials (free-issue), or the basis changed** —
  this single choice can double or halve the reported margin with no economic difference. Check the Ind
  AS 115 principal-vs-agent judgement.
- ODM or "component" revenue defined loosely, or reclassified upward between periods to support a
  mix narrative.
- **PLI incentive recognised before eligibility thresholds are certified**, or presented inside operating
  EBITDA without disclosure; EBITDA ex-PLI never shown.
- Working-capital cycle lengthening while revenue grows — check whether growth is being funded by
  stretching payables (which is customer/supplier credit, and it reverses) or by debt.
- Supply-chain financing / bill discounting used to present better receivable days while the risk
  remains; payables reclassified as borrowings or vice versa.
- Inventory obsolescence provision flat while inventory and technology churn rise; component inventory
  ageing not disclosed. Electronics inventory loses value fast.
- Capacity announced in "lines" or "units" with no customer programme attached; capex for a specific
  brand described as general capacity.
- A single customer's programme loss disclosed as a "vertical rationalisation".
- Capitalisation of new-line commissioning, trial production or design/development costs; R&D
  capitalised in a business claiming ODM capability (the capability should be expensed and visible).
- JV accounting: the JV's losses equity-accounted while its revenue is described as the group's scale;
  the JV partner's rights over the capacity undisclosed.
- Forex gains on imported BOM presented inside operating margin; unhedged import exposure in a
  depreciating-rupee year.
- Related-party component sourcing or promoter-owned toolmakers.
- Scrap and yield losses netted into other income.

## Dependencies to map
**PLI schemes with their dates and thresholds** — mobile-phone PLI, IT-hardware PLI (Rs 170bn), the
anticipated component PLI (~Rs 250-400bn), and the SPECS/electronics-component schemes; plus the
localisation/value-addition requirements and claw-back conditions. This is the single most important
dependency in the playbook · import duties on components and finished goods, and the phased
manufacturing programme's tariff schedule · **the brand owners' own India strategy and volumes** —
Apple/Samsung/Xiaomi for mobile, HP/Acer/Lenovo/Dell for IT hardware, Voltas/Blue Star/Daikin for RAC,
and LG/Samsung for appliances (the corpus's LG Electronics India notes give the counterparty's view) ·
China+1 and the geopolitics of electronics supply chains, including US tariff policy on
China-manufactured goods, which is the demand driver for India capacity · semiconductor and display-panel
availability and pricing · component-level Chinese export controls · USD-INR and the hedging policy on
imported BOM · consumer-durable and IT-hardware demand cycles, and the summer season for RAC · GST
rates on electronics · e-waste and BIS certification requirements · government procurement preference
(PPP-MII) for IT hardware · the vertical-specific technology cycles (panel size migration, 5G, AI PCs)
that reset ASPs.

## Common archetypes here
`margin-expansion` via the value ladder — **the sector's defining and most defensible archetype when the
mix arithmetic is shown**, and pure assertion when it is not · `regulatory-tailwind` (PLI and import
substitution — genuine, dated, and requiring the ex-PLI view) · `capex-to-cashflow` (line and component
capacity commissioning) · `market-share-gainer` (programme wins from global EMS players) ·
`capex-to-cashflow` combined with `re-rating` is the common Dixon-style composite: decompose it and
apply the 40% rule, because a 41x EV/EBITDA target is mostly multiple. Treat `quality-compounder`
sceptically — a 3-6% margin business with 30-50% customer concentration compounds only while the ladder
is being climbed. And watch for `cyclical-peak` in any vertical enjoying a policy-driven
import-substitution windfall.
