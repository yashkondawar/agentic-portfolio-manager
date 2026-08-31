# Broker calibration — whose analysis to trust, and how far

*Used by `prompts/31_deep_research_sector_peers.md` when it ingests competitor research,
and by `prompts/34_thesis_redteam.md` when a broker note is cited as evidence.*

## The governing rule

From `docs/OPINION_VS_ANALYSIS.md`: across 152 rated initiations in the corpus, **85% BUY,
6% ADD, 3% ACCUMULATE, 3% REDUCE, 2% SELL, 1% HOLD** — 94% positive.

> **Take the analysis. Discard the verdict. Never calibrate our rating scale to theirs.**

Broker-specific adjustment applies to *how much of the analysis to trust and where the
house's tilt shows*, not to whether the rating is usable. No rating in this genre is
usable.

## House-level instructions

### Motilal Oswal — EXCLUDED
Excluded from the corpus and from citation, by standing instruction. `fetch_corpus.py`
detects the broker from the **document body** (not the URL, which is opaque on the
Business Standard mirror) and drops the note with `status=excluded_broker`. Sixteen were
caught this way during corpus construction. If a Motilal note surfaces in research, do
not cite it.

### Kotak Institutional Equities — INCLUDE, with a stated adjustment
The user's standing characterisation, which matches the house's reputation: **conclusions
run structurally pessimistic; the underlying numbers work is strong and disciplined.**

How to use them:
- **Take at full weight:** the financial modelling, segment build-ups, the estimate
  driver tables, the peer data, and the accounting/quality observations. Kotak's numbers
  are among the most reliable in the Indian market.
- **Discount the conclusion**, and specifically the target multiple — a conservative
  house sets a conservative multiple, which is an editorial choice, not a finding.
- **Treat the divergence as a signal in its own right.** Where Kotak's own analysis
  supports a better outcome than its rating concedes, that gap is usually the most
  honest bear case available on the name — and it is the single most useful thing to
  extract. Record it explicitly as
  `broker_divergence: {broker, what_the_analysis_shows, what_the_rating_says}`.
- **Never treat a Kotak REDUCE as corroboration of our own bearish view** without
  checking whether their analysis actually supports it. Two pessimists agreeing is not
  independent evidence.

*Corpus coverage caveat:* six Kotak notes reached the corpus — enough to confirm the house
style, not enough to measure its rating tilt against its own analysis. This instruction
therefore still rests mainly on the user's domain judgement rather than on counted evidence.
Flagged rather than dressed up.

### Everyone else — observed characteristics

These come from the corpus and are descriptive, not moral judgements. Sample sizes are
small for most houses; regenerate the per-broker table with
`python tools/er_corpus/profile_notes.py` (see `reference/er_corpus/profile_summary.md`
§ Per-broker fingerprint for the current counts).

| Broker | Notes | Observed character |
|---|---|---|
| **ICICI Securities** | 20 | The most exhibit-dense in the corpus (HDB Financial: 103 labelled exhibits over 66pp). Strong on product-level granularity — average ticket size and tenor per product, sourcing mix, branch-tier distribution. Cites the widest external evidence base (RBI, NHB, MFIN, CRIF, CRISIL Intelligence, Bloomberg, SES ESG). Willing to publish disconfirming exhibits inside a BUY. Watch for RHP/DRHP reliance on recently listed names. |
| **JM Financial** | 27 | Cleanest valuation discipline in the sample. SOTP work is properly constructed — segment multiples individually peer-anchored, explicit holdco discounts, and the implied blended multiple published as a sanity check (Tata Chemicals, Oct-25). Uses ADD/BUY distinctions more readily than most. |
| **Nuvama** | 11 | Chart-led, heavy "story in charts" opener; exhibits are images, so text-based tooling under-counts them badly (APAR: 0 labelled exhibits, 95 `Source:` lines). Strong segment-level SOTP. Most prone in this sample to discount-narrowing language as a valuation justifier (Varun Beverages, Sep-21). |
| **Yes Securities** | 3 | Long, thorough notes (SAMHI: 64pp). Good at qualitative peer scorecards (High/Moderate/Low grids across 8-9 dimensions) and at economically-adjusted multiples (attributable EV/EBITDA net of JV share). Leans on re-rating language. |
| **Anand Rathi** | 5 | Compact, section-led layout. Note the layout quirk: running headers carry the *section* name rather than the company, which breaks naive company-extraction. |
| **Axis Capital (11), Emkay (11), Nirmal Bang (9), BOB Capital (6), HDFC Securities (6), Choice (6), Sushil Finance (5), Equirus (4), Ambit (4), Elara (3), plus LKP, Arihant, Centrum, Sharekhan, IDBI, Keynote, KRChoksey, Systematix** | 1-11 each | Shorter notes (13-40pp), generally single-method valuation, fewer external sources. Useful for structural facts and KPI definitions; thin on industry balance and sensitivity work. Sample too small for a house characterisation — do not generalise from one note. |

## Sourcing hierarchy for external facts

When two broker notes disagree on an industry number, prefer in this order:

1. The regulator or industry association directly (RBI/NHB/IRDAI, PPAC/CEA/JPC, SIAM/FADA,
   NPPA/USFDA) — always go to the primary source the note cites rather than the note.
2. A paid-research house cited by name (CRISIL Intelligence, CRIF, NielsenIQ, IQVIA) —
   attribute to them, not to the broker.
3. The company's own disclosure, tagged `company_claim` and routed to
   `prompts/31` Step 4 for independent verification.
4. The broker's own estimate — lowest tier, always attributed, never load-bearing alone.

A number that appears in a broker note with no `Source:` line is the broker's estimate,
whatever it looks like. Tag it accordingly.

## Recording divergence

Whenever a broker note is used as evidence, `prompts/31` records:

```json
{ "broker": "...", "note_date": "...", "rating": "...",
  "analysis_taken": ["what we used and why it is checkable"],
  "verdict_discarded": true,
  "divergence": "where their own analysis points somewhere other than their rating",
  "conflict_signals": ["recent listing / RHP reliance / syndicate membership, if visible"] }
```

The `divergence` field is the highest-value output of reading competitor research. It is
where commercial pressure and analytical honesty pull apart, and it usually points
straight at the real bear case.
