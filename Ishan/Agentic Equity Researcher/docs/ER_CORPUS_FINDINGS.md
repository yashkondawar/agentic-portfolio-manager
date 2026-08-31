# What Indian initiation notes actually do — findings from the corpus

*Written 2026-08-02. Supersedes the single-benchmark analysis in
`docs/PROCESS_V2_REIMAGINED.md`, which was reverse-engineered by hand from one note
(Emkay, NALCO, 2016). That document's diagnosis was right; this one replaces its
evidence base with a corpus.*

**Regenerate the counted sections** with:
```bash
python tools/er_corpus/profile_notes.py
```
Statistics below come from `reference/er_corpus/profile_summary.md`. Every percentage
is counted from converted text, not estimated. Where a claim rests on close reading of
specific notes rather than on counting, the note is named.

---

## 0. The corpus

| | |
|---|---|
| URLs attempted | 317 |
| Confirmed initiation notes | 165 |
| Brokers | 25 |
| Date range | 2010 – 2026 |
| Excluded (Motilal Oswal, per instruction) | 16 |
| Fetched but not initiations (result/company updates — kept as a contrast set) | 74 |
| Unreachable (dead broker URLs, 403/404) | 62 |

Brokers represented: JM Financial (27), ICICI Securities (20), Nuvama (11), Emkay Global
(11), Axis Capital (11), Nirmal Bang (9), BOB Capital (6), HDFC Securities (6), Choice
Broking (6), Kotak Institutional (6), Anand Rathi (5), Sushil Finance (5), Equirus (4),
Ambit (4), Elara (3), Yes Securities (3), plus LKP, Arihant, Centrum, Sharekhan, IDBI
Capital, Keynote, KRChoksey and Systematix — and 17 whose house could not be identified
from the document body.

**Honest limits.** The mix is skewed toward brokers whose PDFs survive on public
mirrors — Business Standard's `equity-brokertips` archive is the single biggest source,
and it over-represents JM Financial and ICICI Securities. Kotak (6 notes), Ambit (4) and
Axis Capital (11) are present but still thin relative to their real output, because most
of their research sits behind client walls; Spark and the foreign houses are absent. Conclusions about *house style* are therefore weaker than
conclusions about *what the genre does*.

---

## 1. The universal skeleton

Section presence and median position across the corpus (position 1 = earliest):

| Section | Present | Median position |
|---|---|---|
| Financial analysis | 90% | 3 |
| Valuation | 79% | 5 |
| Management | 76% | 5 |
| Financial statements | 76% | 7 |
| Rating box | 73% | 1 |
| Investment thesis | 65% | 3 |
| Company background | 61% | 5 |
| Risks | 61% | 5 |
| Competitive landscape / peers | 56% | 5 |
| Industry overview | 31% | 6 |
| "Story in charts" | 27% | 3 |
| Estimates (as a named section) | 26% | 5 |
| Business model (as a named section) | 24% | 6 |
| Growth drivers | 15% | 5 |
| **Sensitivity** | **14%** | 6 |
| **Governance** | **12%** | 5 |
| Capacity / expansion | 11% | 6 |
| SWOT | 1% | 13 |

The recurring spine, in print order:

```
1  Rating box + one-paragraph thesis + market data + financial summary   (page 1, always)
2  "Story in charts" — 6-10 exhibits that carry the whole argument       (page 2, ~1/3 of notes)
3  Contents / "Our thesis in a nutshell"
4  Investment rationale — the numbered pillars, expanded
5  Business model / company background — segments, products, assets
6  Industry — market size, structure, growth drivers, competitive position
7  Peer comparison — operating metrics first, multiples second
8  Financial outlook — the forecast, driver by driver
9  Valuation — the target multiple and its justification
10 Key risks
11 Financial statements (P&L, BS, CF, ratios)
12 Disclosures
```

**Four things worth noticing about that list.**

*Page 1 is the product.* A reader who stops after page one should have the rating, the
target, the one-line reason, the multi-year financial summary and the price
performance. Everything after page one is supporting evidence. Notes are written
front-loaded, not built to a conclusion.

*"Story in charts" is the most transferable format in the genre.* Roughly a third of
notes open with a spread of 6–10 exhibits that state the entire argument visually before
a word of prose. ICICI Securities' HDB Financial note uses exhibits 1–9 for exactly
this: cost of funds vs peers → AUM mix → the CV upcycle → a decade of credit cost →
franchise investment → cross-cycle RoE → P/B band → P/E band → valuation vs peers. That
sequence *is* the thesis.

*Governance appears in 12% of notes.* The existing agent's governance scoring and
red-flag ledger are genuinely differentiated. This confirms — on 165 notes rather than
one — the claim `PROCESS_V2_REIMAGINED.md` made from the Emkay benchmark alone.

*Sensitivity tables appear in 14% of notes as a section, 19% anywhere.* The agent's
mandate in `prompts/32` to publish a driver sensitivity table already exceeds what five
in six professional initiations do. Do not weaken it to match the corpus.

## 2. Exhibit density is the real quality signal

| Metric | Min | Median | Max |
|---|---|---|---|
| Pages | 6 | 31 | 77 |
| Words | 5,951 | 21,293 | 66,314 |
| Labelled exhibits (recovered as text) | 0 | 30 | 138 |
| `Source:` attributions | 0 | 48 | 158 |

Read the two exhibit rows together — see the measurement caveat in
`tools/er_corpus/README.md`. The honest read is that **a median initiation note carries
roughly 30–48 exhibits across 31 pages: more than one per page.** The current agent's
NALCO final note carried four.

Exhibit *count* is not the goal; exhibit *density per page* reflects a working method in
which every claim gets a picture and every picture gets a source line. The `Source:`
lines also reveal the evidence base. In the HDB Financial note they run: Company data,
Company RHP/DRHP, Bloomberg, NSE, RBI, NHB, MFIN, CRIF, CRISIL Intelligence, SES ESG.
That is six independent external sources beyond the filings — the layer the agent's DR2
module is supposed to produce and, in the NALCO run, largely did not.

## 3. The analyst's reasoning chain vs the print order

Notes are *printed* conclusion-first. They are *built* the other way round. Reconstructed
from where the evidence density sits:

```
1  What is this machine?        segments, products, assets, capacity, geography
2  Where does the money come
   from and go?                 revenue = volume x realisation; cost stack; unit economics
3  What does the industry
   allow?                       market size, structure, supply-demand, share, cycle position
4  What is this company's edge,
   and is it durable?           cost curve / brand / franchise / switching cost — quantified
5  What do the numbers do next?  driver-by-driver forecast, 2-3 years out
6  What is that worth?           target multiple x forward metric, justified against peers,
                                 own history, growth, and (sometimes) a DCF cross-check
7  What kills it?                risks
8  → Only now: the rating.
```

Step 6 is where opinion enters, and it enters *once*, as the choice of multiple. Almost
everything before it is checkable. This is the single most important structural fact in
the corpus, and it is the basis for §4.

The existing pipeline maps onto steps 1–5 and 7 well. It has no owner for step 6's
judgment and no owner for step 8 at all — which is exactly the gap
`prompts/33_thesis_synthesis.md` and `prompts/34_thesis_redteam.md` now fill.

## 4. Valuation: the method, and where the judgment hides

| Method | Share of notes |
|---|---|
| Target P/E × forward EPS | 50% |
| Target EV/EBITDA × forward EBITDA | 24% |
| DCF (usually as a cross-check, not the headline) | 19% |
| SOTP | 15% |
| Target P/B × forward BVPS | 8% |
| EV/Sales, embedded value, DDM | 2-3% each |

The dominant convention is **target multiple × a metric 2–3 years forward**. Four
justifications for the multiple recur, in descending order of rigour:

1. **Segment-specific peer anchoring (best).** APAR (Nuvama, Jan-25): conductors valued
   at 45x against T&D equipment peers trading above 50x; the oils division at 20x, "largely
   in line with peer Savita Oil"; blended to 38x FY27E EPS. Each leg is separately
   defensible.
2. **DCF triangulation.** Max Healthcare (Nuvama, Sep-25): 36x H1FY28E EV/EBITDA, an
   ~18% premium to peers, "aligning with our DCF (6% terminal growth, ~11% WACC)". Two
   independent methods agreeing is real evidence.
3. **Growth-adjusted.** Waaree (Yes, Sep-25): 22x FY28E, "implied PEG of 0.5x".
4. **Assumed discount-narrowing (worst — see §6).**

**A quiet mechanic worth naming: the rolled-forward base.** Targets are routinely struck
on `Sep'27E BVPS`, `Jun'27 EV/EBITDA`, `H1FY28E EV/EBITDA` rather than the current
forward year. Rolling the base forward a year mechanically lifts the target by roughly a
year of growth without changing the multiple. It is legitimate, and it is almost never
flagged as a source of return. Any agent replicating this must state the base year and
show what the target would be un-rolled.

## 5. The rating distribution is the headline finding on opinion

| Rating | Notes | Share |
|---|---|---|
| BUY | 129 | 85% |
| ADD | 9 | 6% |
| ACCUMULATE | 5 | 3% |
| REDUCE | 4 | 3% |
| SELL | 3 | 2% |
| HOLD | 2 | 1% |

**Ninety-four percent of rated initiations are positive (BUY/ADD/ACCUMULATE). Just 6% are
REDUCE, SELL or HOLD.** The BUY share measured 82% at n=34, 82% at n=109, 84% at n=132 and
85% at n=152 — about as stable as a corpus statistic gets, and it drifted *up* as the
sample grew.

*Correction against an earlier draft of this document, written at n=34: that sample
contained no SELL at all and the finding was stated as "none is a SELL". At n=152 three
SELLs appear (2%). The direction is unchanged and the conclusion below is unaffected, but
initiations at a SELL are rare rather than non-existent.*

This is a structural fact about the genre, not a coincidence of sampling: houses
initiate coverage on names they want to market, and an initiation is a client-facing
product. The consequence for anyone mining these notes is decisive:

> **The rating carries almost no information. The analysis carries nearly all of it.**

A distribution that is 97% positive cannot discriminate between companies — it has
almost no variance to work with. But the *analysis* underneath varies enormously in
quality and is largely checkable. This is the empirical justification for separating the
two, which `docs/OPINION_VS_ANALYSIS.md` operationalises.

It also means: **never calibrate the agent's rating scale against this corpus.** Copy
the analytical apparatus; discard the verdict distribution.

## 6. Thesis archetype vocabulary

Share of notes using each archetype's language:

| Archetype signal | Present | Median intensity when present |
|---|---|---|
| Margin expansion | 70% | 3 |
| Turnaround | 52% | 2 |
| Special situation | 44% | 1 |
| Capex-to-cashflow | 25% | 2 |
| Regulatory tailwind / PLI | 23% | 2 |
| **Re-rating** | **22%** | **3** |
| Market-share gain | 16% | 2 |
| Balance-sheet repair | 12% | 2 |
| Quality compounder | 10% | 2 |
| GARP | 10% | 2 |
| Cyclical recovery | 9% | 2 |
| Cyclical peak | 4% | 1 |
| Deep value | 2% | 2 |

Most notes blend two or three. The full taxonomy — with the conditions each archetype
requires, its standard failure mode, and how much benefit of the doubt it deserves —
lives in `prompts/thesis_archetypes/`.

**Roughly one initiation in five reaches for re-rating language, and when it does, it does
so repeatedly (median 3 mentions).** It is a load-bearing argument, not an aside — which is
why it gets its own checklist and the highest skepticism weight.

### The re-rating trap, in the corpus's own words

Two notes show the failure mode cleanly enough to quote.

**Varun Beverages (Nuvama, Sep-2021)** — the purest instance:

> "the discount to Indian FMCG companies is higher than what fundamentals indicate. We
> expect discount to FMCG companies to narrow further and thus assign 42x FY23E PE (30%
> discount) to VBL."

The chain is: observe a discount → assert it is unwarranted → assume it narrows → and
that assumption *is* the target multiple. Nothing in it is falsifiable, and no mechanism
or catalyst is offered for why the discount closes. Note carefully: VBL subsequently
performed extremely well, so **the call was right while the printed reasoning was
unsound.** A correct outcome does not validate circular logic — this is precisely why
the archetype needs a structural test rather than a vibe check.

**SAMHI Hotels (Yes Securities, Sep-2025)** — titled *"The Turnaround Story with
Re-rating Potential"*, whose fifth pillar is "Strong re-rating potential due to
significant valuation discount to peers". The note observes SAMHI "traded at a sharp
discount to peers over past few years, owing to myriad of factors" — and then values it
at 15x Jun'27 EV/EBITDA when it trades at ~11x FY27E. A meaningful share of the 45%
upside is the multiple moving, and "myriad of factors" is exactly the thing that needed
refuting rather than acknowledging.

To be fair to the same note, it also contains genuinely rigorous work — see §7.

**The test that separates good from bad re-rating arguments** is whether the note
identifies *the mechanism by which the discount closes* and *what would prove it isn't
closing*. "It's cheap versus peers" is an observation. "It's cheap versus peers because
the market is still pricing pre-turnaround leverage, and the FY27 net-debt/EBITDA print
below 2x is the event that forces a re-mark" is an argument. The corpus contains far
more of the former.

## 7. What good notes do that a naive AI report would not

Concrete, transferable moves observed in the corpus:

1. **Adjust the multiple for economic ownership before comparing.** SAMHI is valued on
   *attributable* EV/EBITDA net of GIC's JV share. Comparing headline EV/EBITDA across
   peers with different minority structures is simply wrong, and most summarisers do it.
2. **Prove a capability claim with a realised transaction.** SAMHI's "we recycle capital
   well" is evidenced by the Duet India (Chennai OMR) disposal at ~20x EV/EBITDA against
   an acquisition discipline of buying below replacement cost. A claim with a price
   attached beats an adjective.
3. **Publish the metric that contradicts the thesis.** ICICI's HDB Financial note carries
   Exhibit 29, "HDB has relatively grown at a slow pace vs. peers over the past 3 years",
   inside a BUY. Including the disconfirming exhibit is a credibility marker — and a
   behaviour the red-team module should require of us.
4. **Decompose growth into price and volume, then say which one you are betting on.**
   Max Healthcare: "Volume to remain key revenue driver… as ARPOB growth to moderate."
   One sentence that tells you the whole forecast's shape.
5. **Product-level granularity in the KPI table.** HDB Financial tabulates average ticket
   size *and* average tenor *per product*, plus sourcing mix (~80% direct), plus the share
   of branches in tier-4+ towns. These are the numbers that explain the margin, and none
   of them is in a financial statement.
6. **A qualitative peer scorecard alongside the quantitative one.** SAMHI rates eight
   peers High/Moderate/Low across owned-expansion pipeline, competitive intensity,
   leverage, market resilience, asset positioning, segmental diversification, geographic
   diversification, operational efficiency and concentration risk. It converts "better
   positioned" into something inspectable.
7. **Segment-specific multiples in an SOTP, each peer-anchored, plus an explicit holdco
   discount.** Tata Chemicals (JM, Oct-25): 9x India EBITDA, 8x UK EBITDA, 20% holding
   discount on Rallis → INR 970 Sep'26 TP, implied 10x EV/EBITDA and 23x P/E. The implied
   blended multiples are published as a sanity check on the parts.
8. **State what is deliberately *not* in the numbers.** The behaviour
   `PROCESS_V2_REIMAGINED.md` flagged from the Emkay benchmark recurs across the corpus,
   and is the cleanest signal of an honest forecast.
9. **Use replacement cost as an acquisition *discipline*, not a valuation assertion.**
   SAMHI Hotels (Yes Securities, Sep-25): the strategy "hinges on buying an asset at a
   discount to replacement cost, which ensures robust ROCE post turnaround and
   sustainability of asset operations during downcycle." The same number — cost per key
   versus replacement cost — is a passive "it's cheap" claim when used at the valuation
   step and an operating rule when used at the acquisition step. Only the second is
   evidence of a repeatable capability.

## 8. What the corpus is *worse* at than the current agent

Keep these; they are the agent's moat, and the corpus confirms they are rare:

- **Governance and promoter analysis** — a named section in 12% of notes.
- **Earnings-quality forensics** — no note in the corpus carries anything resembling an
  adjudicated red-flag ledger.
- **Citation discipline** — broker notes cite sources per exhibit but never per number,
  and none is independently re-derivable.
- **Explicit data-gap disclosure** — essentially absent. Broker notes do not tell you what
  they could not find out.
- **Sensitivity tables** — 19% (14% as a named section).
- **Consensus referencing** — 32%, despite every one of these desks having Bloomberg.

## 9. Implications for the agent

| Finding | Change |
|---|---|
| Exhibit density ~1.3/page vs our 4 per note | Sector playbooks each specify a standard exhibit set; `prompts/41` requires it |
| "Story in charts" opens a third of notes | Add an exhibit-led summary spread to the final note |
| The multiple is the one judgment call | `prompts/33` must state and defend it explicitly, and decompose return into EPS growth vs multiple change |
| Rolled-forward valuation bases inflate targets silently | `prompts/33` must name the base year and show the un-rolled target |
| 94% of ratings are positive | Never calibrate our rating scale to broker practice; the red-team module exists to supply the missing variance |
| Re-rating arguments are usually circular | `prompts/34` enforces a banned-reasoning list and a mechanism-and-falsifier test |
| Product-level KPI granularity drives the margin story | `config/sector_registry.yaml` carries signature KPIs per sub-sector; module 03 must attempt every one |
| Notes publish disconfirming exhibits | Red-team requires at least one disconfirming exhibit in our own note |
| Peers must be compared on economically comparable multiples | `prompts/23` must adjust for minority/JV structures before ranking |

## 10. Canonical corpus passages — this file owns them

A handful of corpus passages are load-bearing across the prompt set: the same five or six
notes supply the worked example for an archetype's conditions, a sector playbook's valuation
convention, a red-team check and a findings section. Before this index existed, each of those
passages was **quoted verbatim in two or three files**, which is the same defect the sector
registry had — several shortening copies of one fact, drifting independently.

**The rule, following the pattern `prompts/34_thesis_redteam.md` already uses for the 15
opinion/analysis checks: this file owns the quotation. Everything else states the fact in its
own words and cites the anchor.** Do not paste the quote into a third file.

| Passage | Owner | Cite as |
|---|---|---|
| APAR segment-anchored SOTP (45x conductors, 20x oils, 38x blended) | §4 item 1 | `ER_CORPUS_FINDINGS §4.1` |
| Max Healthcare DCF triangulation (36x H1FY28E, 6% terminal, ~11% WACC) | §4 item 2 | `§4.2` |
| Waaree growth-adjusted (22x FY28E, implied PEG 0.5x) | §4 item 3 | `§4.3` |
| The rolled-forward valuation base | §4, closing paragraph | `§4` |
| Varun Beverages discount-narrowing ("42x FY23E PE (30% discount)") | §6 | `§6` |
| SAMHI attributable EV/EBITDA net of the GIC JV share | §7 item 1 | `§7.1` |
| SAMHI Duet India (Chennai OMR) disposal at ~20x | §7 item 2 | `§7.2` |
| HDB Exhibit 29 — grew slower than peers, inside a BUY | §7 item 3 | `§7.3` |
| Max Healthcare volume-over-ARPOB growth split | §7 item 4 | `§7.4` |
| HDB product-level ATS/tenor/sourcing granularity | §7 item 5 | `§7.5` |
| SAMHI nine-dimension qualitative peer scorecard | §7 item 6 | `§7.6` |
| Tata Chemicals SOTP + 20% Rallis holdco discount | §7 item 7 | `§7.7` |
| SAMHI replacement cost as acquisition discipline | §7 item 9 | `§7.9` |
| The 94%-positive rating distribution | §5 | `§5` |

**Sector playbooks are the one legitimate exception, and only for their own sector.**
`prompts/sector_playbooks/hospitals.md` may carry the Max Healthcare multiple because that
*is* the hospitals valuation convention and hospitals.md is the file that owns hospitals
content; likewise `prompts/sector_playbooks/hotels.md` for SAMHI,
`prompts/sector_playbooks/specialty_chemicals.md` for Tata Chemicals,
`prompts/sector_playbooks/capital_goods_electrical.md` for APAR,
`prompts/sector_playbooks/fmcg.md` for Varun Beverages and
`prompts/sector_playbooks/nbfc_diversified.md` for HDB. Each of those still carries the `§` anchor so a reader can
reach the full treatment, and none of them re-quotes a passage owned by a *different*
sector's playbook.

## 11. Reproducing this

```bash
python tools/er_corpus/discover.py --crawl
python tools/er_corpus/fetch_corpus.py --seeds reference/er_corpus/seeds/all_pending.txt
python tools/er_corpus/profile_notes.py     # regenerates every counted table above
python tools/er_corpus/digest_notes.py      # 6x-compressed reading copies
```

Two measurement caveats carry into any re-run: pdfminer drops `ti`/`fi`/`fl` ligatures,
and chart exhibits lose their titles to image conversion. Both are documented, with
mitigations, in `tools/er_corpus/README.md`. Neither is fixed — they are bounded and
disclosed.
