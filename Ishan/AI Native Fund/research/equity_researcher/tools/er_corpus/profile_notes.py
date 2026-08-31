"""Structurally profile the converted corpus. Deterministic, zero LLM tokens.

    python tools/er_corpus/profile_notes.py
    python tools/er_corpus/profile_notes.py --summary-only

Answers, by COUNTING rather than impression:
  * which sections an Indian initiation note actually contains, and in what order
  * how many exhibits it carries, and what they are called
  * which analytical apparatus is present (sensitivity, SOTP, DCF, peer table,
    supply-demand balance, cost stack, scenario cases, SWOT, value chain)
  * how the target price is derived
  * which thesis-archetype vocabulary the note leans on

This is the statistical backbone for docs/ER_CORPUS_FINDINGS.md. Claims about
"the universal skeleton" must be grounded here, not in an LLM's recollection of
a handful of notes it happened to read.

Writes reference/er_corpus/profile.json and profile_summary.md.

All matching is ligature-tolerant — see corpus_lib.contains_fuzzy for why.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from er_corpus import corpus_lib as L  # noqa: E402

# --------------------------------------------------------------------------
# Canonical section vocabulary. Key = canonical name, value = surface variants.
# Matching a controlled vocabulary (rather than scraping raw headings) is what
# makes section ORDER comparable across brokers with different house styles.
# --------------------------------------------------------------------------
SECTIONS: dict[str, list[str]] = {
    "rating_box":          ["target price", "cmp", "current market price", "reco", "recommendation"],
    "investment_thesis":   ["investment thesis", "investment rationale", "investment argument",
                            "key investment", "why we like", "investment summary", "our thesis"],
    "story_in_charts":     ["story in charts", "in charts", "chartbook", "visual summary"],
    "company_background":  ["company background", "company overview", "about the company",
                            "company profile", "business overview", "corporate profile"],
    "business_model":      ["business model", "revenue model", "how the company makes money",
                            "value chain", "business segments", "segment overview"],
    "industry_overview":   ["industry overview", "sector overview", "industry background",
                            "market overview", "industry outlook", "sector outlook",
                            "industry structure", "the industry", "market size"],
    "competitive_landscape": ["competitive landscape", "competition", "peer comparison",
                              "peer analysis", "competitive position", "market share",
                              "peer set", "comparative analysis"],
    "growth_drivers":      ["growth drivers", "key growth", "growth levers", "demand drivers",
                            "structural drivers", "triggers"],
    "capacity_expansion":  ["capacity expansion", "capex plan", "expansion plan", "capex cycle",
                            "greenfield", "brownfield", "project pipeline"],
    "financial_analysis":  ["financial analysis", "financial performance", "financial outlook",
                            "financials", "earnings outlook", "financial summary",
                            "revenue growth", "margin expansion", "profitability"],
    "estimates":           ["our estimates", "we estimate", "forecast", "projections",
                            "key assumptions", "assumptions", "estimate summary"],
    "valuation":           ["valuation", "valuation methodology", "our valuation",
                            "target price derivation", "fair value", "valuation rationale"],
    "sensitivity":         ["sensitivity analysis", "sensitivity", "scenario analysis",
                            "bull case", "bear case", "bull and bear", "scenario"],
    "risks":               ["key risks", "risks", "risk factors", "downside risks",
                            "what could go wrong", "risks to our"],
    "management":          ["management", "management team", "key management",
                            "promoter", "board of directors", "management profile"],
    "governance":          ["corporate governance", "governance", "related party",
                            "auditor", "accounting quality", "earnings quality"],
    "esg":                 ["esg", "environmental social", "sustainability"],
    "swot":                ["swot"],
    "financial_statements": ["income statement", "profit and loss", "balance sheet",
                             "cash flow statement", "ratio analysis", "key ratios",
                             "financial tables", "dupont"],
    "annexure":            ["annexure", "appendix", "exhibit index"],
    "disclaimer":          ["disclaimer", "disclosure", "analyst certification",
                            "important disclosures"],
}

# Analytical apparatus — presence/absence, the thing that separates a real note
# from a summary.
APPARATUS: dict[str, list[str]] = {
    "sensitivity_table":    ["sensitivity analysis", "sensitivity to", "1% change in",
                             "10% change in", "elasticity", "for every 1%"],
    "scenario_cases":       ["bull case", "bear case", "base case", "blue sky", "worst case"],
    "sotp":                 ["sotp", "sum of the parts", "sum-of-the-parts"],
    "dcf":                  ["discounted cash flow", "dcf", "wacc", "terminal growth",
                             "free cash flow to firm"],
    "peer_multiple_table":  ["peer comparison", "peer valuation", "comparable companies",
                             "relative valuation", "peer set", "trading comps"],
    "supply_demand_balance": ["supply demand", "demand supply", "supply-demand",
                              "capacity addition", "surplus", "deficit", "utilisation of industry"],
    "cost_stack":           ["cost breakup", "cost break-up", "cost structure", "raw material cost as",
                             "cost per tonne", "cost of production", "% of sales", "cost build"],
    "unit_economics":       ["per tonne", "per unit", "per store", "per subscriber", "per room",
                             "per bed", "per employee", "per litre", "per kg", "realisation per"],
    "value_chain_map":      ["value chain", "supply chain", "vertical integration",
                             "backward integration", "forward integration"],
    "market_share_data":    ["market share", "share of the market", "% share"],
    "capex_pipeline":       ["capex", "capital expenditure", "expansion plan", "commissioning"],
    "working_capital":      ["working capital", "cash conversion", "receivable days",
                             "inventory days", "payable days", "net working capital"],
    "roce_tree":            ["roce", "roic", "return on capital", "dupont", "return on equity"],
    "guidance_tracking":    ["management guidance", "guided", "guidance of", "company expects"],
    "consensus_reference":  ["consensus", "bloomberg estimates", "street estimates", "vs street"],
    "price_band_history":   ["1-year forward", "one year forward", "5-year average",
                             "historical average", "pe band", "p/e band", "trading range",
                             "mean multiple", "standard deviation"],
    "swot_grid":            ["swot"],
    "porter":               ["porter", "five forces"],
    "esg_section":          ["esg", "environmental social governance"],
    "promoter_pledge":      ["pledge", "pledged shares"],
    "corporate_history":    ["incorporated in", "founded in", "history", "milestones"],
}

# Vocabulary that reveals which thesis archetype the note is arguing.
ARCHETYPE_SIGNALS: dict[str, list[str]] = {
    "re_rating":         ["re-rating", "rerating", "re-rate", "multiple expansion",
                          "deserves a higher multiple", "valuation gap", "discount to peers",
                          "narrowing of the discount", "rerate"],
    "quality_compounder": ["compounder", "consistent compounding", "high quality franchise",
                           "steady compounding", "secular growth", "long runway"],
    "garp":              ["growth at a reasonable price", "garp", "peg", "reasonable valuation",
                          "attractive valuation given growth"],
    "cyclical_recovery": ["cycle upturn", "cyclical recovery", "at the bottom of the cycle",
                          "trough", "upcycle", "recovery in demand", "cycle turning"],
    "cyclical_peak":     ["peak of the cycle", "peak margins", "downcycle", "mid-cycle",
                          "normalisation of margins", "peak earnings"],
    "turnaround":        ["turnaround", "turn around", "restructuring", "revival",
                          "loss to profit", "return to profitability", "new management"],
    "capex_to_cashflow": ["capex cycle ending", "free cash flow inflection", "fcf generation",
                          "deleveraging", "debt reduction", "capex peaking"],
    "market_share_gain": ["market share gain", "gaining share", "share shift",
                          "wallet share", "consolidation of the industry"],
    "margin_expansion":  ["margin expansion", "operating leverage", "mix improvement",
                          "premiumisation", "margin tailwind"],
    "balance_sheet_repair": ["deleveraging", "debt repayment", "net debt reduction",
                             "balance sheet repair", "asset monetisation"],
    "special_situation": ["demerger", "spin-off", "spinoff", "value unlocking", "listing of",
                          "holdco discount", "merger"],
    "regulatory_tailwind": ["pli scheme", "production linked incentive", "china+1",
                            "import substitution", "anti-dumping", "policy support",
                            "government capex", "make in india"],
    "deep_value":        ["deep value", "trading below book", "replacement cost",
                          "sum of the parts discount", "nav discount"],
}

EXHIBIT_RX = re.compile(
    r"^\s*[|*#>\s]*((?:exhibit|exh\.?|fig(?:ure)?\.?|chart|table)\s*[-–—:]?\s*\d+[a-z]?)\s*[:.\-–—]?\s*(.{0,110})",
    re.I | re.M)

RATING_RX = re.compile(
    r"\b(BUY|SELL|HOLD|ADD|REDUCE|ACCUMULATE|NEUTRAL|OUTPERFORM|UNDERPERFORM|OVERWEIGHT|UNDERWEIGHT)\b")

TP_RX = re.compile(
    r"(?:target\s*price|\bTP\b|fair\s*value|price\s*target)\s*[:\-–(]?\s*"
    r"(?:of\s*)?(?:INR|Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)", re.I)

# How the target multiple is justified — the single most revealing valuation line.
VALUATION_METHOD = {
    "target_pe":        [r"\d+(?:\.\d+)?\s*x\s*(?:FY|CY)?\s*\d*\s*[EA]?\s*(?:EPS|earnings|P/?E)",
                         r"target\s*(?:P/?E|multiple)\s*of\s*\d+"],
    "target_ev_ebitda": [r"\d+(?:\.\d+)?\s*x\s*(?:FY|CY)?\s*\d*\s*[EA]?\s*EV\s*/?\s*EBITDA",
                         r"EV\s*/\s*EBITDA\s*of\s*\d+(?:\.\d+)?\s*x"],
    "target_pb":        [r"\d+(?:\.\d+)?\s*x\s*(?:FY|CY)?\s*\d*\s*[EA]?\s*(?:P/?BV?|book)",
                         r"price\s*to\s*book\s*of\s*\d"],
    "dcf":              [r"\bDCF\b", r"discounted\s*cash\s*flow", r"\bWACC\b"],
    "sotp":             [r"\bSOTP\b", r"sum[\s-]of[\s-]the[\s-]parts"],
    "ddm":              [r"\bDDM\b", r"dividend\s*discount"],
    "ev_sales":         [r"\d+(?:\.\d+)?\s*x\s*(?:FY|CY)?\s*\d*\s*[EA]?\s*EV\s*/?\s*(?:sales|revenue)"],
    "embedded_value":   [r"embedded\s*value", r"\bEV\b\s*multiple.*insur", r"\bVNB\b"],
}


def profile_one(md_path: Path, meta: dict) -> dict:
    text = md_path.read_text(encoding="utf-8", errors="replace")
    sq = L.squash(text)
    n_pages = text.count("<!-- page ")
    words = len(text.split())

    lowered = text.lower()

    # --- section sequence.
    # Substring search over the whole document does NOT work: every broker note
    # carries "Please refer to important disclosures at the end of this report"
    # on page 1, which put `disclaimer` at position 2 in early runs, and running
    # headers/footers repeat on every page. A section only counts when it appears
    # as a HEADING: a short standalone line that is mostly the section name.
    first_at: dict[str, int] = {}
    offset = 0
    for raw_line in text.splitlines():
        line = re.sub(r"^[|*#>\s]+|[|*\s]+$", "", raw_line).strip()
        offset += len(raw_line) + 1
        if not line or len(line) > 60:
            continue
        low = line.lower()
        lsq = L.squash(line)
        if not lsq:
            continue
        for canon, variants in SECTIONS.items():
            if canon in first_at:
                continue
            for v in variants:
                vsq = L.squash(v)
                hit = (vsq and vsq in lsq) or (L.delig(vsq) and L.delig(vsq) in lsq)
                # the variant must dominate the line, so "risks" matches a "Key risks"
                # heading but not "Risks to our estimates include a slowdown in ..."
                if hit and len(vsq) / len(lsq) >= 0.55:
                    first_at[canon] = offset
                    break
        # cheap early exit once everything plausible has been seen
        if len(first_at) == len(SECTIONS):
            break
    section_sequence = [k for k, _ in sorted(first_at.items(), key=lambda kv: kv[1])]

    # --- exhibits
    exhibits = []
    for label, caption in EXHIBIT_RX.findall(text):
        cap = re.sub(r"\s+", " ", caption).strip(" |*:-–—")
        exhibits.append({"label": re.sub(r"\s+", " ", label).strip(), "caption": cap[:110]})
    exhibit_labels = {e["label"].lower() for e in exhibits}

    # Exhibit count is systematically UNDERSTATED for brokers whose exhibits are
    # chart images — markitdown extracts no text from a rendered chart, so the
    # "Exhibit 12: EBITDA/tonne trend" title vanishes with it. Nearly every
    # broker exhibit does, however, carry a "Source: ..." attribution line in
    # real text beneath it, so that count is the better proxy for exhibit
    # density. Both are reported; neither alone is trustworthy.
    n_source_lines = len(re.findall(r"^\s*[|*>\s]*sources?\s*:", text, re.I | re.M))

    # --- apparatus / archetype signals (counts, not booleans — intensity matters)
    # Word boundaries are mandatory: bare `re.escape("esg")` / `"dcf"` / `"car"`
    # match inside longer words and inflate presence rates. Substring matching is
    # the same mistake that once sent a transmission-conductor note to BFSI on the
    # strength of "ape"/"apex" — see fetch_corpus.SECTOR_KEYWORDS.
    def _count(terms: list[str]) -> int:
        total = 0
        for t in terms:
            total += len(re.findall(r"\b" + re.escape(t) + r"\b", lowered))
        return total

    apparatus = {}
    for k, terms in APPARATUS.items():
        n = _count(terms)
        if n == 0:
            # Ligature-damaged fallback, but ONLY for terms long enough to be safe.
            # squash() strips spaces, so a 3-letter term like "esg" matches inside
            # "char[ges g]rew" — that false positive alone put esg_section at 91%.
            n = sum(1 for t in terms
                    if len(L.squash(t)) >= 10 and L.contains_fuzzy(sq, t))
        apparatus[k] = n

    archetypes = {k: _count(terms) for k, terms in ARCHETYPE_SIGNALS.items()}

    # --- rating / target price
    head = text[:9000]
    ratings = RATING_RX.findall(head)
    rating = Counter(ratings).most_common(1)[0][0] if ratings else ""
    tp = TP_RX.search(text)

    val_methods = [k for k, pats in VALUATION_METHOD.items()
                   if any(re.search(p, text, re.I) for p in pats)]

    return {
        "note_id": meta.get("note_id", md_path.stem),
        "broker": meta.get("broker", ""),
        "broker_slug": meta.get("broker_slug", md_path.parent.name),
        "company": meta.get("company", ""),
        "sector_guess": meta.get("sector_guess", ""),
        "date": meta.get("date", ""),
        "pages": n_pages,
        "words": words,
        "rating": rating,
        "target_price": tp.group(1) if tp else "",
        "valuation_methods": val_methods,
        "section_sequence": section_sequence,
        "n_exhibits": len(exhibit_labels),
        "n_source_lines": n_source_lines,
        "exhibits": exhibits[:60],
        "apparatus": apparatus,
        "archetype_signals": archetypes,
        "md_path": str(md_path.relative_to(L.REPO_ROOT)),
    }


def summarise(profiles: list[dict]) -> str:
    n = len(profiles)
    if not n:
        return "# Corpus profile\n\nNo notes profiled yet.\n"

    out: list[str] = []
    add = out.append
    add("# ER initiation-note corpus — structural profile")
    add("")
    add(f"Generated by `tools/er_corpus/profile_notes.py` over **{n} initiation notes**. ")
    add("Every figure below is counted from the converted text, not estimated.")
    add("")

    brokers = Counter(p["broker"] for p in profiles)
    sectors = Counter(p["sector_guess"] for p in profiles)
    add(f"**Brokers ({len(brokers)}):** " + ", ".join(f"{b} ({c})" for b, c in brokers.most_common()))
    add("")
    add(f"**Sector guesses:** " + ", ".join(f"{s} ({c})" for s, c in sectors.most_common()))
    add("")

    pages = sorted(p["pages"] for p in profiles)
    exh = sorted(p["n_exhibits"] for p in profiles)
    src = sorted(p.get("n_source_lines", 0) for p in profiles)
    words = sorted(p["words"] for p in profiles)

    def med(xs):
        return xs[len(xs) // 2] if xs else 0

    add("## Size")
    add("")
    add("| Metric | Min | Median | Max |")
    add("|---|---|---|---|")
    add(f"| Pages | {pages[0]} | {med(pages)} | {pages[-1]} |")
    add(f"| Words | {words[0]:,} | {med(words):,} | {words[-1]:,} |")
    add(f"| Labelled exhibits (text) | {exh[0]} | {med(exh)} | {exh[-1]} |")
    add(f"| `Source:` attributions | {src[0]} | {med(src)} | {src[-1]} |")
    add("")
    add("*Read the two exhibit rows together. Labelled-exhibit counts are understated ")
    add("because markitdown recovers no text from a chart rendered as an image — the ")
    add("`Exhibit 12: EBITDA/tonne` title disappears with the picture. The `Source:` ")
    add("attribution line beneath each exhibit survives as real text, so it is the ")
    add("better density proxy. A note showing 0 labelled exhibits and 40 source lines ")
    add("is chart-heavy, not exhibit-free.*")
    add("")

    add("## Section presence and typical position")
    add("")
    add("`Present` = share of notes containing the section. `Median position` = its median ")
    add("rank in the note's section order (1 = earliest).")
    add("")
    add("| Section | Present | Median position |")
    add("|---|---|---|")
    pos: dict[str, list[int]] = defaultdict(list)
    for p in profiles:
        for i, s in enumerate(p["section_sequence"], 1):
            pos[s].append(i)
    rows = []
    for sec in SECTIONS:
        hits = pos.get(sec, [])
        if not hits:
            rows.append((sec, 0.0, 99))
            continue
        rows.append((sec, len(hits) / n, med(sorted(hits))))
    for sec, share, mp in sorted(rows, key=lambda r: (-r[1], r[2])):
        add(f"| {sec} | {share*100:.0f}% | {mp if share else '—'} |")
    add("")

    add("## Analytical apparatus")
    add("")
    add("Share of notes where the feature appears at all, and the median number of ")
    add("mentions among notes that have it — intensity separates a real treatment from ")
    add("a passing reference.")
    add("")
    add("| Feature | Present | Median mentions (when present) |")
    add("|---|---|---|")
    for k in APPARATUS:
        vals = [p["apparatus"].get(k, 0) for p in profiles]
        present = [v for v in vals if v > 0]
        share = len(present) / n
        add(f"| {k} | {share*100:.0f}% | {med(sorted(present)) if present else '—'} |")
    add("")

    add("## Valuation method")
    add("")
    add("| Method | Share of notes |")
    add("|---|---|")
    vm = Counter()
    for p in profiles:
        for m in p["valuation_methods"]:
            vm[m] += 1
    for m, c in vm.most_common():
        add(f"| {m} | {c/n*100:.0f}% |")
    add("")

    add("## Rating distribution")
    add("")
    rt = Counter(p["rating"] for p in profiles if p["rating"])
    add("| Rating | Notes | Share |")
    add("|---|---|---|")
    for r, c in rt.most_common():
        add(f"| {r} | {c} | {c/max(1,sum(rt.values()))*100:.0f}% |")
    add("")
    add("*A heavily BUY-skewed distribution is itself a finding about sell-side opinion — ")
    add("see docs/OPINION_VS_ANALYSIS.md.*")
    add("")

    add("## Thesis-archetype vocabulary")
    add("")
    add("Share of notes using each archetype's language, and median intensity when used.")
    add("")
    add("| Archetype signal | Present | Median mentions (when present) |")
    add("|---|---|---|")
    for k in ARCHETYPE_SIGNALS:
        vals = [p["archetype_signals"].get(k, 0) for p in profiles]
        present = [v for v in vals if v > 0]
        add(f"| {k} | {len(present)/n*100:.0f}% | {med(sorted(present)) if present else '—'} |")
    add("")

    add("## Per-broker fingerprint")
    add("")
    add("| Broker | Notes | Median pages | Median exhibits | Sensitivity | Peer table | Scenarios |")
    add("|---|---|---|---|---|---|---|")
    by_broker: dict[str, list[dict]] = defaultdict(list)
    for p in profiles:
        by_broker[p["broker"] or "Unknown"].append(p)
    for b, ps in sorted(by_broker.items(), key=lambda kv: -len(kv[1])):
        pg = med(sorted(x["pages"] for x in ps))
        ex = med(sorted(x["n_exhibits"] for x in ps))
        sn = sum(1 for x in ps if x["apparatus"].get("sensitivity_table", 0)) / len(ps)
        pt = sum(1 for x in ps if x["apparatus"].get("peer_multiple_table", 0)) / len(ps)
        sc = sum(1 for x in ps if x["apparatus"].get("scenario_cases", 0)) / len(ps)
        add(f"| {b} | {len(ps)} | {pg} | {ex} | {sn*100:.0f}% | {pt*100:.0f}% | {sc*100:.0f}% |")
    add("")

    add("## Most common exhibit captions")
    add("")
    caps = Counter()
    for p in profiles:
        for e in p["exhibits"]:
            c = re.sub(r"[\d,.%()]+", "", e["caption"]).strip().lower()
            if len(c) > 8:
                caps[c] += 1
    for c, k in caps.most_common(40):
        add(f"- {k}× — {c}")
    add("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary-only", action="store_true",
                    help="rebuild profile_summary.md from an existing profile.json")
    a = ap.parse_args()

    L.ensure_dirs()
    prof_path = L.CORPUS_ROOT / "profile.json"

    if a.summary_only and prof_path.exists():
        profiles = json.loads(prof_path.read_text(encoding="utf-8"))
    else:
        by_id = {r.get("note_id", ""): r for r in L.read_manifest()}
        profiles = []
        for r in L.read_manifest():
            if r.get("status") != "ok" or not r.get("md_path"):
                continue
            p = L.REPO_ROOT / r["md_path"]
            if not p.exists():
                continue
            try:
                profiles.append(profile_one(p, by_id.get(r.get("note_id", ""), r)))
            except Exception as e:  # never let one bad note kill the profiling pass
                print(f"WARN {p.name}: {type(e).__name__}: {e}", file=sys.stderr)
        prof_path.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = summarise(profiles)
    (L.CORPUS_ROOT / "profile_summary.md").write_text(summary, encoding="utf-8")
    print(f"profiled {len(profiles)} note(s)")
    print(f"  {prof_path}")
    print(f"  {L.CORPUS_ROOT / 'profile_summary.md'}")


if __name__ == "__main__":
    main()
