# Archetype — Re-rating

**Skepticism weight: 5 (highest). Treat as assertion until every condition below is met.**

## Definition
The claim that the stock's *multiple* is too low and will rise, independently of (or on
top of) growth in earnings. The return comes from other investors changing their minds.

## Return source
Change in P/E, EV/EBITDA, P/B or the SOTP discount. Triggered automatically whenever the
return decomposition attributes **>40%** of expected return to multiple change, whatever
the note calls itself.

## Why this archetype is different from all the others
Every other archetype makes a claim about the *business* — one the filings will
eventually adjudicate. This one makes a claim about *the market's opinion of the
business*. There is no internal evidence that can ever confirm it, and being right
requires other people to agree with you. That asymmetry, not pessimism about the outcome,
is why it carries the highest bar.

## `must_be_true` — all five, or the archetype is rejected

1. **The current discount is measured, not asserted.**
   Quantify it: against what peer set, over what period, and how far from its own mean in
   standard-deviation terms. "Trades below peers" is not a measurement.
   *Establishes with:* a peer multiple table on a comparability-adjusted basis
   (see `docs/OPINION_VS_ANALYSIS.md` §3) plus the target's own 5-year band.

2. **The cause of the discount is named.**
   Markets discount things for reasons: leverage, governance, cyclicality, promoter
   overhang, low float, poor disclosure, customer concentration, a past accident,
   regulated returns, holdco structure. If you cannot name why the discount exists, you
   cannot argue it will close.
   *Fails on:* "a myriad of factors" (SAMHI Hotels, Yes Securities, Sep-2025).

3. **A mechanism closes it, and the mechanism is company-specific.**
   Not "sentiment improves". Something that changes the named cause: leverage crosses a
   threshold, the disputed segment is sold, the governance finding is remediated, the
   contract is renewed, index inclusion forces buying, the holdco discount is collapsed
   by an actual demerger.
   *Fails on:* "we expect the discount to narrow" — the assumed outcome used as its own
   justification (Varun Beverages, Nuvama, Sep-2021).

4. **The mechanism is dated and observable.**
   A quarter, an event, or a disclosed threshold — something a reader can check on a
   calendar. Re-rating claims without a date are unfalsifiable and therefore untestable.

5. **What the market currently believes, and why it is wrong, is stated explicitly.**
   A re-rating thesis is by construction a disagreement with the marginal buyer. Name the
   disagreement. If our own numbers are in line with consensus and guidance, there is no
   variant view and hence no reason for the multiple to move.

## Standard evidence pattern (when done well)
Peer multiple table on a like-for-like basis → the target's own multiple band with the
dates of the band extremes and what caused them → the specific impairment being priced →
the event that removes it, dated → the multiple that then applies, anchored to the peer
that most resembles the post-event company.

## Standard failure mode
**Circularity.** Observe a discount → assert it is unwarranted → assume it narrows → and
the assumed narrowing *is* the target multiple. Nothing is falsifiable and no mechanism
is offered. This is the single most common defective argument in the corpus.

Secondary failure: **borrowing a peer's multiple without borrowing its economics** —
applying a compounder's multiple to a business with half its ROCE and twice its
cyclicality.

## Falsifiers (record as monitorables with thresholds)
- The dated catalyst passes and the multiple does not move → the discount was structural,
  not cyclical. Downgrade the archetype, do not extend the date.
- The named cause of the discount recurs (leverage rises again, governance repeats).
- The peer set itself de-rates — the gap closes with no gain, which means the thesis was
  a sector call wearing a stock-specific costume.
- Earnings deliver but the multiple compresses → the market disagrees about durability,
  not about the level.

## A caution that cuts both ways
Varun Beverages, whose printed re-rating logic is the most circular in the corpus, went
on to perform very well. **A correct outcome does not validate unsound reasoning, and
unsound reasoning does not predict a bad outcome.** Judge the argument. When the
checklist fails, the correct action is not "this stock will fall" — it is *"our expected
return has no evidentiary support beyond the earnings case"*, and the rating should be
struck on the earnings case alone with the multiple held flat.

## Sectors where it recurs
Most common in: hotels and real estate (asset-value discounts), holdcos and
conglomerates (SOTP discounts), PSUs (governance and disinvestment overhangs), recently
listed names (float and track-record discounts), and any sector after a de-rating event.

## Corpus examples
- **Varun Beverages** (Nuvama, Sep-2021) — fails conditions 2, 3, 5: the assumed narrowing
  of the FMCG discount *is* the target multiple, with no mechanism and no falsifier. Quoted
  in full at `docs/ER_CORPUS_FINDINGS.md` §6, which also records that the call was right
  while the printed reasoning was unsound — the reason this archetype needs a structural
  test rather than an outcome check.
- **SAMHI Hotels** (Yes Securities, Sep-2025) — titled *"The Turnaround Story with
  Re-rating Potential"*; pillar 5 is the discount itself. Fails condition 2 explicitly
  ("a myriad of factors"). Passes 1 (attributable EV/EBITDA, adjusted for the GIC JV
  share) and partially 3 (deleveraging plan with a dated net-debt path).
- **APAR Industries** (Nuvama, Jan-2025) — "ample re-rating potential given GoI's
  singular focus on T&D". Names a mechanism (policy-driven T&D capex) but it is
  sector-wide, not company-specific: fails condition 3's specificity test even though the
  segment-anchored SOTP underneath is rigorous.
- **Waaree Energies** (Yes Securities, Sep-2025) — "WEL trades at lower valuation
  multiples, suggesting rerating potential as scale…". Condition 2 unaddressed.
