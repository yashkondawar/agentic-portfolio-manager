# Sector Playbook — FMCG & packaged consumer

*Tier 2. Family: `consumer_retail` (`prompts/sector_packs/consumer_retail.md`). Shared rules:
`prompts/31`.*
**Provenance:** corpus-grounded — Bikaji Foods (Nuvama, Jun-24, 46pp, 66 exhibits), Varun
Beverages (Ambit, Apr-26 and Nuvama, Sep-21 — the latter is also the corpus's canonical
re-rating failure case, see `docs/ER_CORPUS_FINDINGS.md` §6), Radico Khaitan (JM Financial,
Sep-25) and Tilaknagar Industries (JM Financial, Mar-26) for alcoholic beverages, Zydus Wellness
(BOB Capital, Mar-22), Eureka Forbes (Nuvama, Sep-25) and LG Electronics India (ICICI
Securities, Oct-25; Elara, Mar-26) for durables, Kaveri Seed (LKP, Aug-24).

## The economic engine
An FMCG company buys a commodity, brands it, and pushes it through a distribution network to a
consumer who buys it repeatedly and cheaply. The identity is simple and every KPI is a term in
it:

`Revenue = volume × realisation per case` → `Gross profit = volume × (realisation − input cost)`
→ `EBITDA = gross profit − A&P − distribution − overhead`

Three things follow, and they are what separate this playbook from every other consumer child:

- **Volume is the only honest growth number.** Value growth blends volume, price and mix. Price
  growth is borrowed from inflation and reverses; mix is real but capped; **volume growth is the
  franchise.** Bikaji's thesis is explicitly built this way — 18% revenue CAGR FY24-27E "powered
  by volume growth of 14-15% annually". Demand the split, always.
- **Distribution reach is the moat and it is a countable asset.** Direct-reach outlets, total
  outlets, stockists, and the direct/indirect split. Bikaji planned to "expand direct reach by
  25% over next two years"; that is a capex-like investment in the moat, and it shows up as
  cost before it shows up as revenue.
- **A&P is discretionary and therefore a lever for flattering margins.** Advertising and
  promotion is a real investment in future volume that can be switched off for a quarter to make
  EBITDA look better. Always read the EBITDA margin and the A&P ratio together.

## Analysis sequence
1. **Decompose growth into volume, price and mix** — three separate series, for the company and
   for each major category. If the company does not disclose volume, say so as a data gap; do
   not infer it silently.
2. **Realisation per case (or per unit) and the input spread.** Varun Beverages' "India
   realization per case improved from CY20 on Sting + NCB scale-up" is the pattern: realisation
   rising because of *mix* (new higher-priced products), not price increases on the core. Split
   them, because they have different durabilities.
3. **The cost stack and its pass-through mechanics** — the two or three key inputs (palm oil,
   wheat, milk solids, PET/resin, sugar, glass, ENA for liquor) with each one's hedging or
   contracting mechanism and the lag. Gross margin held through a rising input is the pricing-power
   test; gross margin expanding because an input fell is a cycle, and it reverses.
4. **Distribution architecture, counted** — direct-reach outlets, total outlets, stockists,
   van/rural routes, and the general-trade / modern-trade / e-commerce / quick-commerce split
   with its **margin by channel**. Quick-commerce usually carries a better realisation and a
   worse net margin after platform fees; get the arithmetic, not the narrative.
5. **Category position and premiumisation evidence** — market share by category (from NielsenIQ
   or company disclosure), the premium tier's share of revenue and its growth. For liquor, the
   prestige-and-above (P&A) mix is the whole story.
6. **A&P intensity vs peers and vs the company's own history**, mapped against subsequent volume
   growth. This tells you whether the spend works.
7. **Working capital and the trade's health** — receivable days by channel and inventory in the
   trade. Primary sales (to the distributor) can outrun secondary (to the consumer) for two or
   three quarters before it corrects.
8. **Then ROCE and the multiple.** In this sector ROCE is the multiple's justification, because
   the assets are small and the brand is not on the balance sheet.

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Volume growth** | YoY growth in units / cases / tonnes sold | % | The franchise measure. Bikaji: 14-15% p.a. underpinning an 18% revenue CAGR — the gap is price/mix and must be named. If volume is undisclosed, that is a reportable gap, not an estimate | Decks, transcripts, AR |
| **Gross margin** | (revenue − raw material) / revenue | % | The pricing-power test *through* an input cycle. Expansion coinciding with a falling input index is cyclical (see `margin-expansion.md` condition 5), not structural | P&L |
| **A&P as % of sales** | advertising & promotion / revenue | % | Read beside the EBITDA margin. A margin beat delivered by cutting A&P is borrowed from next year's volume | P&L, segment note |
| **Direct-reach outlets** | outlets serviced directly by the company | count | The countable moat. Track direct *and* total reach, and the direct share — Bikaji's planned +25% direct reach is an investment that precedes the revenue | Decks (rarely in the AR) |
| **EBITDA margin** | EBITDA / revenue | % | Bridge every change into gross margin, A&P, distribution and overhead. An unbridged margin move is not an analysis | P&L |

## Supporting KPIs
Realisation per case/unit; volume and value market share by category (NielsenIQ/Kantar);
premium-tier (or P&A) mix; new-product share of revenue (typically disclosed as % from products
launched in the last 3 years); channel mix with margin by channel; quick-commerce and
e-commerce share; modern-trade share; rural vs urban split; stockist and van-route count;
revenue per outlet; capacity and utilisation by plant; in-house vs contract-manufactured share;
freight as % of sales (Varun Beverages charts this against volume growth — a real operating-leverage
tell); receivable and inventory days by channel; ROCE and ROCE excluding goodwill;
fixed-asset turnover; royalty or franchise fees to a parent; state-mix and excise exposure for
liquor; per-capita consumption of the category (the long-run headroom argument).

## Standard exhibit set
Volume / price / mix decomposition of revenue growth (the sector's single most important
exhibit) · realisation per case trend with the mix driver called out · gross margin against the
key input's price index on a second axis · A&P ratio vs EBITDA margin over 10 years ·
direct and total reach with the direct share · channel mix with margin by channel ·
market share by category vs peers · premium-tier mix trend · new-product contribution ·
capacity and utilisation by plant · freight as % of sales vs volume · working-capital days by
channel · per-capita consumption vs comparable markets · ROCE trend and vs peers ·
P/E one-year-forward band with the dates and causes of both extremes · valuation vs peers on
P/E against ROCE and volume growth.

## Valuation convention
**Target P/E × forward EPS**, with the premium justified by **ROCE and volume durability** — not
by brand adjectives. The corpus's dominant method (50% of notes) applied to its most
multiple-sensitive sector.

**This sector is where the corpus's worst valuation practice lives, and the playbook must guard
against it.** Varun Beverages (Nuvama, Sep-21) is the canonical instance: observe a discount to
Indian FMCG peers, assert it is unwarranted, assume it narrows, and let that assumption *be* the
target multiple — no mechanism, no falsifier. The passage is quoted in full, with the discount
and the FY23E multiple, at `docs/ER_CORPUS_FINDINGS.md` §6. **VBL then performed extremely well,
which is exactly why the reasoning must be judged separately from the outcome.** If our note
argues a re-rating here, `prompts/33`'s 40% rule and `prompts/34`'s mechanism-and-falsifier test
are mandatory, not optional.

*Traps:* (i) discount-narrowing as the argument, per above; (ii) capitalising a gross margin
inflated by a soft input cycle; (iii) paying a premium multiple for value growth that is mostly
price in an inflationary year; (iv) crediting distribution expansion before the reach numbers
move; (v) using a global FMCG peer set on Indian growth without adjusting for either; (vi) for
durables and appliances, applying an FMCG multiple to a business with retail-like seasonality and
far worse working capital.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It trades at 55x forward EPS against a sector median of 42x.**
- *The brand deserves it* (`peer_set_choice`) — a quality premium, as always in this sector.
- *Unearned until proven* (`incremental_roce`) — the premium is justified by ROCE and volume
  durability, not by adjectives. This is the sector where the corpus's worst valuation
  practice lives.
- *Discriminator* (`peer_distribution`) — ROCE and five-year volume CAGR against the peer
  set. And the standing warning: Varun Beverages (Nuvama, Sep-21) observed a discount to
  Indian FMCG peers, asserted it was unwarranted, assumed it narrowed, and let that
  assumption *be* the target multiple — no mechanism, no falsifier. VBL then performed
  extremely well, which is exactly why the reasoning must be judged separately from the
  outcome (`docs/OPINION_VS_ANALYSIS.md` §2 F1).

**2. Revenue grew 14%.**
- *Strong demand* (`growth_durability`).
- *Price, not volume* (`growth_durability`) — a price-and-mix-led year during input
  inflation does not repeat, and volume was flat.
- *Discriminator* (`disclosed_mechanism`) — the volume/price/mix decomposition the company
  publishes. This sector discloses it; there is no excuse for asserting around it.

## Forensic screens (sector-specific)
- **Value growth reported without volume** — or volume disclosed only in the good quarters.
- Gross margin expansion exactly tracking a falling input index, described as premiumisation.
- A&P cut in the same quarter the EBITDA margin beat — check the two together.
- **Primary sales outrunning secondary**: receivable days and trade inventory rising while
  reported growth holds. This is channel stuffing and it corrects within a year.
- New-product revenue counted for longer than the stated window, or the window changed.
- Reach numbers restated or redefined (direct vs total, outlets vs "touchpoints") between years.
- Quick-commerce revenue booked gross while platform fees sit in "other expenses".
- Contract-manufacturing arrangements with promoter-related entities; royalty payments to a
  parent rising ahead of revenue.
- Capitalised brand-building or launch costs; scheme/discount spend moved between "revenue
  deduction" and "advertising" — the two presentations give different gross margins on identical
  economics.
- Subsidiary or export losses parked outside the reported segment.
- For liquor: state-level receivables from government corporations, and inventory build ahead of
  an excise-policy change.

## Dependencies to map
Monsoon and rural wages (IMD, MGNREGA) for mass consumption · key agri and crude-linked input
prices (palm oil, wheat, sugar, milk, PET/resin, glass, ENA) with duty changes · GST rate changes
on the category · state excise policy and route-to-market regimes for alcohol — these change
without notice and can remove a state's revenue for a quarter (Tilaknagar and Radico are both
exposed) · NielsenIQ/Kantar category data · quick-commerce platform economics and their
commission trajectory · PLI for food processing where applicable · the parent's global brand
arrangement for bottlers and licensees (Varun Beverages is 90%+ of PepsiCo's India volumes —
a dependency in both directions) · per-capita consumption benchmarks for the headroom argument.

## Common archetypes here
`quality-compounder` (the default claim — needs ROCE plus durable volume, not brand language),
`margin-expansion` (the corpus's most-used archetype at 70% — check condition 5 against the input
cycle), `market-share-gainer` (verify from third-party category data, not company assertion),
`garp`, and `re-rating`, which carries the highest skepticism weight in this sector for the
reasons above. `regulatory-tailwind` applies to GST and excise changes and to PLI. Watch for
`cyclical-peak` dressed as premiumisation when a soft input cycle is doing the work.
