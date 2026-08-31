"""Compress each corpus note into an analytically-dense digest. Zero LLM tokens.

    python tools/er_corpus/digest_notes.py
    python tools/er_corpus/digest_notes.py --max-chars 30000

WHY THIS EXISTS
A converted initiation note runs 20k-40k words (~30-50k tokens). Handing six
agents four whole notes each costs well over a million tokens — which is exactly
how the first attempt at this research died on the session cap. But most of that
bulk is boilerplate: disclaimers, repeated running headers, full financial
statement appendices, and analyst-certification pages.

The analytically load-bearing parts of a broker note are small and locatable by
regex: the cover tearsheet, the section headings, the exhibit inventory, the
valuation paragraphs, the risk section, and the driver/KPI lines. This script
pulls exactly those into a ~20-25k character digest — roughly a 5-8x reduction —
so an agent can read four notes for the cost of one.

Digests are a READING AID, not a replacement. Each digest header carries the path
to the full note so an agent can open specific pages when the digest is thin.
(Same relationship as cache/markdown vs. the original PDF in a real run.)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from er_corpus import corpus_lib as L  # noqa: E402
from er_corpus.profile_notes import EXHIBIT_RX, SECTIONS  # noqa: E402

DIGEST_DIR = L.CORPUS_ROOT / "digest"

# Lines worth keeping verbatim wherever they appear in the note.
VALUATION_RX = re.compile(
    r"(target price|price target|fair value|we value|valuing|valuation of|"
    r"\d+(?:\.\d+)?\s*x\s*(?:FY|CY)|assign a|ascribe|multiple of|"
    r"discount to|premium to|re-?rat|de-?rat|implied|upside of|downside of|"
    r"\bDCF\b|\bWACC\b|\bSOTP\b|\bDDM\b|terminal (growth|value)|cost of equity)", re.I)

RISK_RX = re.compile(
    r"(key risk|risks? to (our|the)|downside risk|what could go wrong|"
    r"we could be wrong|bear case|adverse|headwind|threat of|vulnerab)", re.I)

THESIS_RX = re.compile(
    r"(we initiate|we like|our thesis|investment (thesis|rationale|argument)|"
    r"we believe|we expect|key (reasons|drivers|pillars)|three reasons|"
    r"why we|structural|moat|competitive advantage|entry barrier)", re.I)

# Driver / KPI-shaped lines: a metric name plus a number, or a per-unit measure.
KPI_RX = re.compile(
    r"(per tonne|/tonne|per unit|per store|per subscriber|per room|per bed|"
    r"per employee|per kg|per litre|realisation|utili[sz]ation|occupancy|"
    r"\bARPU\b|\bSSSG\b|\bNIM\b|\bGNPA\b|\bCASA\b|\bRevPAR\b|\bARPOB\b|"
    r"\bROCE\b|\bROE\b|\bROA\b|book.to.bill|order (book|inflow)|"
    r"market share|volume growth|EBITDA margin|gross margin|"
    r"attrition|book value|credit cost|cost of funds|"
    r"CAGR|bps|yoy|y-o-y)", re.I)

ASSUMPTION_RX = re.compile(
    r"(we (assume|forecast|estimate|model|build in|factor)|"
    r"our (assumption|estimate|forecast|model)|assumes? a|"
    r"not factor|not built in|not in our (numbers|estimates)|"
    r"upside risk to our|conservative(ly)?)", re.I)

BOILERPLATE_RX = re.compile(
    r"(analyst certification|disclaimer|disclosure|registered office|"
    r"sebi registration|research analyst regulation|this report is|"
    r"no part of this|distributed in the united states|"
    r"telephone|e-?mail|@[a-z]+\.(com|in)|www\.|"
    r"^\s*\|\s*-+\s*\|)", re.I)


def _pages(text: str) -> list[tuple[int, str]]:
    out = []
    for chunk in text.split("<!-- page ")[1:]:
        num, _, body = chunk.partition("-->")
        try:
            out.append((int(num.strip()), body))
        except ValueError:
            continue
    return out


def _dedupe_keep_order(lines: list[str], limit: int) -> list[str]:
    seen, out = set(), []
    for ln in lines:
        key = re.sub(r"[\d,.\s]+", "", ln.lower())[:80]
        if key in seen or len(key) < 8:
            continue
        seen.add(key)
        out.append(ln)
        if len(out) >= limit:
            break
    return out


def _clean(ln: str) -> str:
    return re.sub(r"\s{2,}", " ", ln.strip())


def digest_one(md_path: Path, prof: dict, max_chars: int) -> str:
    text = md_path.read_text(encoding="utf-8", errors="replace")
    pages = _pages(text)
    parts: list[str] = []
    add = parts.append

    add(f"# DIGEST — {prof.get('broker','?')} · {prof.get('company','?')} · {prof.get('date','?')}")
    add("")
    add(f"- **Full note (open this for anything the digest truncates):** `{prof.get('md_path','')}`")
    add(f"- Pages: {prof.get('pages')} · words: {prof.get('words')} · "
        f"labelled exhibits: {prof.get('n_exhibits')} · `Source:` lines: {prof.get('n_source_lines')}")
    add(f"- Rating (regex): {prof.get('rating') or 'n/a'} · Target price (regex): {prof.get('target_price') or 'n/a'}")
    add(f"- Valuation methods detected: {', '.join(prof.get('valuation_methods') or []) or 'none detected'}")
    add(f"- Section order detected: {' > '.join(prof.get('section_sequence') or [])}")
    add("")
    add("> This is a deterministic extract, not a summary. Nothing here is paraphrased. "
        "Financial-statement appendices, disclaimers and repeated running headers are dropped.")
    add("")

    # --- 1. Cover + tearsheet: the densest two pages in any broker note.
    add("## [1] COVER / TEARSHEET (pages 1-2, verbatim)")
    add("")
    for pno, body in pages[:2]:
        add(f"<!-- page {pno} -->")
        add(body.strip()[:6000])
        add("")

    # --- 2. Section headings in order, with the opening of each section.
    add("## [2] SECTION HEADINGS IN ORDER (with opening lines)")
    add("")
    variants = {v: canon for canon, vs in SECTIONS.items() for v in vs}
    lines = text.splitlines()
    hits = 0
    for i, raw in enumerate(lines):
        line = re.sub(r"^[|*#>\s]+|[|*\s]+$", "", raw).strip()
        if not line or len(line) > 60:
            continue
        lsq = L.squash(line)
        if not lsq:
            continue
        matched = None
        for v, canon in variants.items():
            vsq = L.squash(v)
            if vsq and vsq in lsq and len(vsq) / len(lsq) >= 0.55:
                matched = canon
                break
        if not matched:
            continue
        follow = " ".join(_clean(x) for x in lines[i + 1:i + 9] if x.strip())[:420]
        add(f"**{line}**  _[{matched}]_")
        add(f"    {follow}")
        add("")
        hits += 1
        if hits >= 40:
            break

    # --- 3. Exhibit inventory: what the analyst chose to show.
    add("## [3] EXHIBIT INVENTORY")
    add("")
    exh = [f"{lab}: {cap}".strip(" :") for lab, cap in EXHIBIT_RX.findall(text)]
    exh = _dedupe_keep_order([_clean(e) for e in exh], 70)
    if exh:
        for e in exh:
            add(f"- {e}")
    else:
        add("_No text-labelled exhibits. This broker renders exhibits as chart images, "
            "whose titles markitdown cannot recover — see the `Source:` attributions below "
            "for true exhibit density._")
    add("")
    srcs = _dedupe_keep_order(
        [_clean(x) for x in lines if re.match(r"^\s*[|*>\s]*sources?\s*:", x, re.I)], 30)
    if srcs:
        add("**`Source:` attributions (one per exhibit — reveals which data vendors "
            "and primary sources the analyst relies on):**")
        for s in srcs:
            add(f"- {s}")
    add("")

    # --- 4-7. Themed line pulls.
    for title, rx, cap in (
        ("[4] THESIS / ARGUMENT LINES", THESIS_RX, 60),
        ("[5] VALUATION LINES (how the target is derived and justified)", VALUATION_RX, 55),
        ("[6] ESTIMATE / ASSUMPTION LINES (incl. what is deliberately NOT in the numbers)",
         ASSUMPTION_RX, 40),
        ("[7] RISK LINES", RISK_RX, 30),
    ):
        add(f"## {title}")
        add("")
        picked = []
        for raw in lines:
            ln = _clean(raw)
            if not (25 <= len(ln) <= 400):
                continue
            if BOILERPLATE_RX.search(ln):
                continue
            if rx.search(ln):
                picked.append(ln)
        for ln in _dedupe_keep_order(picked, cap):
            add(f"- {ln}")
        add("")

    # --- 8. KPI-bearing tables: where the sector's signature numbers live.
    add("## [8] KPI / DRIVER TABLE ROWS")
    add("")
    tbl = []
    for raw in lines:
        ln = _clean(raw)
        if not ln.startswith("|") or ln.count("|") < 3:
            continue
        if BOILERPLATE_RX.search(ln) or re.match(r"^\|[\s\-:|]+\|$", ln):
            continue
        if KPI_RX.search(ln) and re.search(r"\d", ln):
            tbl.append(ln[:300])
    for ln in _dedupe_keep_order(tbl, 90):
        add(ln)
    add("")

    out = "\n".join(parts)
    if len(out) > max_chars:
        out = out[:max_chars] + (
            f"\n\n_[digest truncated at {max_chars} chars — open the full note at "
            f"`{prof.get('md_path','')}` for the remainder]_\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-chars", type=int, default=26000)
    a = ap.parse_args()

    prof_path = L.CORPUS_ROOT / "profile.json"
    if not prof_path.exists():
        sys.exit("run profile_notes.py first")
    profiles = {p["note_id"]: p for p in json.loads(prof_path.read_text(encoding="utf-8"))}

    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    n, total_in, total_out = 0, 0, 0
    for prof in profiles.values():
        md = L.REPO_ROOT / prof["md_path"]
        if not md.exists():
            continue
        d = digest_one(md, prof, a.max_chars)
        (DIGEST_DIR / f"{prof['note_id']}.md").write_text(d, encoding="utf-8")
        total_in += md.stat().st_size
        total_out += len(d)
        n += 1
    ratio = total_in / total_out if total_out else 0
    print(f"digested {n} note(s) -> {DIGEST_DIR}")
    print(f"  {total_in/1e6:.1f} MB of markdown -> {total_out/1e6:.2f} MB of digest ({ratio:.1f}x reduction)")


if __name__ == "__main__":
    main()
