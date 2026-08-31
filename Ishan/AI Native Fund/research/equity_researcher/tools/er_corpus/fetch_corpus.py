"""Download initiation-note PDFs and convert them to markdown. Zero LLM tokens.

    python tools/er_corpus/fetch_corpus.py --seeds reference/er_corpus/seeds/all.txt
    python tools/er_corpus/fetch_corpus.py --url <one-url>
    python tools/er_corpus/fetch_corpus.py --seeds ... --limit 40 --keep-updates

Each line of a seed file is either a bare URL or `URL<TAB>company<TAB>sector<TAB>date`
(extra fields optional — they are hints; anything missing is inferred from the PDF).

Reuses tools/convert_docs.py's `convert_markdown()` so the corpus is converted by
exactly the same code path as a real run's step 0.5 CONVERT.

By default, notes that do not look like initiations are downloaded, profiled, and
recorded with status=not_initiation but their markdown is kept (cheap, and useful
as a contrast set). Use --initiations-only to delete non-initiation markdown.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tools/ on path

import requests  # noqa: E402

import convert_docs as cd  # noqa: E402
from er_corpus import corpus_lib as L  # noqa: E402

# Phrases that mark a note as an initiation of coverage. Matched ligature-tolerantly.
INITIATION_MARKERS = [
    "initiating coverage", "initiate coverage", "we initiate coverage",
    "initiation of coverage", "coverage initiation", "initiating with",
    "re-initiating coverage", "reinitiating coverage", "initiating on",
]

# Phrases that mark a note as something else (used only to explain a negative).
UPDATE_MARKERS = [
    "result update", "q1fy", "q2fy", "q3fy", "q4fy", "earnings update",
    "company update", "event update", "quarterly review",
]

# HIGH-PRECISION phrases only. Bare words are a trap: an early version used
# `\bapex?\b` for BFSI's "APE" (annualised premium equivalent) and matched
# "ape"/"apex" 44 times inside a transmission-conductor note, and `tower` sent
# the same note to telecom. Every entry below must be a phrase that essentially
# only occurs in its own sector.
SECTOR_KEYWORDS: list[tuple[str, str]] = [
    ("bfsi", r"net interest income|net interest margin|gross npa|\bgnpa\b|\bnnpa\b|casa ratio|"
             r"provision coverage ratio|credit cost|capital adequacy|\bcar\b ratio|\bcet\s?1\b|"
             r"slippage|disbursement|loan book|assets under management|cost of funds|"
             r"vnb margin|annualised premium equivalent|persistency|solvency ratio|combined ratio|"
             r"claims ratio|net stable funding|priority sector lending"),
    ("it_technology", r"constant currency|\btcv\b|large deal|book.to.bill.{0,12}(quarter|IT)|"
                      r"offshore mix|onsite mix|revenue per employee|attrition rate|utili[sz]ation.{0,8}(rate|excl)|"
                      r"\bsaas\b|net revenue retention|annual recurring revenue|rule of 40|deal pipeline|\bgenai\b"),
    ("pharma_healthcare", r"\busfda\b|\bcdmo\b|\bcramp?s\b|abbreviated new drug|\banda\b filing|"
                          r"para\s*iv|first.to.file|import alert|warning letter|\boai\b|\bvai\b|"
                          r"\bnlem\b|price erosion|chronic therapy|acute therapy|\barpob\b|"
                          r"average length of stay|occupied bed|bed addition|test volume|patient footfall"),
    ("chemicals", r"specialty chemical|agrochemical|caustic soda|soda ash|fluorochemical|"
                  r"\bktpa\b|custom synthesis|china\+1|import substitution.{0,20}chemical|"
                  r"backward integrat.{0,25}(ksm|intermediate)|technical grade"),
    ("consumer_retail", r"\bsssg\b|same.store sales|like.for.like sales|distribution reach|"
                        r"direct reach|\ba&p spend|advertising and promotion|premiumi[sz]ation|"
                        r"store count|store addition|average daily sales|revenue per square|"
                        r"general trade|modern trade|quick commerce|rural growth"),
    ("auto_engineering", r"\bsiam\b|\bfada\b|\bvahan\b|content per vehicle|dealer inventory|"
                         r"tractor volume|two.wheeler volume|passenger vehicle volume|"
                         r"commercial vehicle volume|kit value|platform win|scrappage"),
    ("infra_capital_goods", r"order book|order inflow|order backlog|book.to.bill|"
                            r"\bepc\b|\bham\b project|\bbot\b project|\bl1\b position|"
                            r"execution rate|bid pipeline|contingent liabilit"),
    ("commodities_energy", r"ebitda per tonne|realisation per tonne|cost of production per|"
                           r"\blme\b|clinker|grinding capacity|lead distance|blended realisation|"
                           r"\bplf\b|\bmmbtu\b|gross refining margin|crack spread|cost curve|"
                           r"captive (coal|power|mine)|merchant tariff|\bppa\b tenure"),
    ("real_estate", r"pre.?sales|booking value|saleable area|launch pipeline|unsold inventory|"
                    r"land bank|per square feet realisation|collection efficiency.{0,20}project|"
                    r"\bgav\b|\bnav\b per share.{0,20}(realty|property)"),
    ("telecom_media", r"\barpu\b|subscriber base|subscriber net add|churn rate|spectrum (auction|liability|renewal)|"
                      r"data usage per|minutes of usage|advertising revenue|subscription revenue|"
                      r"content amorti[sz]ation|viewership share"),
    ("hotels", r"\brevpar\b|average room rate|room nights|occupancy.{0,15}(rate|%).{0,25}(hotel|room)|"
               r"managed (keys|rooms)|owned (keys|rooms)|\bf&b\b revenue|management fee income"),
    ("logistics", r"tonne.?km|fleet utili[sz]ation|revenue per truck|warehousing (space|occupancy)|"
                  r"\bteu\b|cargo volume|sorting cent|express (parcel|logistics)|"
                  r"freight rate|rail coefficient"),
    ("textiles", r"spindle|yarn (price|spread|realisation)|cotton (price|spread)|"
                 r"garment(ing)? capacity|\brosctl\b|fabric capacity|count mix"),
    ("sugar_agri", r"sugarcane|cane crushing|recovery rate.{0,15}(sugar|cane)|ethanol blend|"
                   r"distillery capacity|\bfrp\b|\bsap\b price.{0,10}cane|bagasse"),
]

# A note must beat the runner-up by this ratio before we trust the guess.
_SECTOR_MARGIN = 1.5
_SECTOR_MIN_HITS = 5


def guess_sector(text_squashed: str, raw: str) -> str:
    scores: Counter[str] = Counter()
    for sector, pattern in SECTOR_KEYWORDS:
        scores[sector] = len(re.findall(pattern, raw, re.I))
    ranked = scores.most_common(2)
    if not ranked or ranked[0][1] < _SECTOR_MIN_HITS:
        return "unknown"
    top, n = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0
    if runner and n < runner * _SECTOR_MARGIN:
        return "ambiguous"
    return top


er_corpus_GENERIC_TERMS = [
    # broker boilerplate / running furniture
    r"india\s+equity\s+research", r"equity\s+research", r"institutional\s+(equities|research)",
    r"ini?\s*t?i?\s*a\s*t?i?\s*ng\s+coverage",  # ligature-tolerant "initiating coverage"
    r"company\s+(report|update|background|profile|overview)", r"result\s+update",
    r"please\s+refer", r"exhibit", r"source\s*:", r"table\s*\d", r"figure\s*\d",
    r"www\.", r"page\s*\d", r"research\s+analyst", r"disclaimer", r"key\s+data",
    r"stock\s+data", r"market\s+data", r"price\s+performance", r"shareholding",
    # section headings that masquerade as running headers
    r"investment\s+(summary|rationale|thesis|argument|highlights)",
    r"financial\s+(summary|snapshot|statements|highlights|performance)",
    r"key\s+(financials|risks|assumptions|highlights|charts|metrics)",
    r"valuation(\s+and\s+\w+)?$", r"outlook", r"business\s+model", r"peer\s+compar",
    r"income\s+statement", r"balance\s+sheet", r"cash\s+flow", r"ratio\s+analysis",
    r"about\s+the\s+company", r"executive\s+summary", r"story\s+in\s+charts",
    r"swot", r"annexure", r"appendix", r"management\s+(team|profile)",
    r"we\s+(initiate|expect|believe|estimate)", r"target\s+price", r"rating",
]
_GENERIC_HEADER = re.compile(r"^\s*(" + "|".join(er_corpus_GENERIC_TERMS) + r")|^\d+$", re.I)


_CORP_SUFFIX = re.compile(
    r"\b(ltd|limited|inds|industries|industry|corp|corporation|company|"
    r"bank|finance|financial|financials|services|motors|pharma|pharmaceuticals|"
    r"cement|cements|steel|power|energy|chemicals|technologies|tech|systems|"
    r"labs|laboratories|healthcare|hospitals|infra|infrastructure|projects|"
    r"enterprises|holdings|foods|beverages|textiles|mills|paper|logistics|"
    r"hotels|resorts|realty|estates|developers|electricals|electronics|"
    r"engineering|auto|automobiles|insurance|life|general|capital|securities)\b", re.I)

# Anchors that sit right next to the company name on a broker note's cover page.
_COVER_ANCHOR = re.compile(
    r"^\s*(rating|reco(mmendation)?|target\s*price|tp\s*[:(]|cmp|current\s*market\s*price|"
    r"buy|sell|hold|add|reduce|accumulate|outperform|underperform)\b", re.I)


def _clean_line(ln: str) -> str:
    ln = re.sub(r"^[|#*>\s]+|[|*\s]+$", "", ln)
    return re.sub(r"\s{2,}", " ", ln).strip()


def _plausible_name(ln: str, broker_slug: str) -> bool:
    if not (3 <= len(ln) <= 55):
        return False
    if _GENERIC_HEADER.match(ln):
        return False
    bslug = L.squash(broker_slug)
    if bslug and len(bslug) >= 5 and bslug[:6] in L.squash(ln):
        return False
    if sum(c.isdigit() for c in ln) > 4 or ln.count("|") > 1:
        return False
    if len(ln.split()) > 7:
        return False
    return bool(re.match(r"^[A-Z][A-Za-z0-9&.,'()\-/ ]+$", ln))


def pdf_title(pdf_path: Path) -> str:
    """Many brokers set a usable /Title in the PDF metadata."""
    try:
        from pypdf import PdfReader
        t = (PdfReader(str(pdf_path)).metadata or {}).get("/Title") or ""
        t = _clean_line(str(t))
        return t if _plausible_name(t, "") and _CORP_SUFFIX.search(t) else ""
    except Exception:
        return ""


def guess_company(md_text: str, broker_slug: str, pdf_path: Path | None = None) -> str:
    """Three strategies, scored together — no single one is reliable across brokers.

    A. PDF metadata /Title (when it names a company).
    B. A cover-page line adjacent to a Rating / Target Price / CMP anchor. This is
       what rescues layouts like Anand Rathi's, where pages 2+ carry the *section*
       name as the running header and the company appears only on page 1.
    C. The most frequent non-generic running header (Nuvama, JM, BOB style).
    """
    pages = md_text.split("<!-- page ")
    scores: Counter[str] = Counter()

    if pdf_path is not None:
        t = pdf_title(pdf_path)
        if t:
            scores[t] += 6

    # B — cover page (first two pages), extra weight next to a rating/TP anchor
    for pg in pages[1:3]:
        body = pg.split("-->", 1)[-1]
        lines = [_clean_line(x) for x in body.splitlines()]
        lines = [x for x in lines if x][:30]
        for i, ln in enumerate(lines):
            if not _plausible_name(ln, broker_slug):
                continue
            near = any(_COVER_ANCHOR.match(lines[j])
                       for j in range(max(0, i - 3), min(len(lines), i + 4)) if j != i)
            scores[ln] += 5 if near else 2
            if _CORP_SUFFIX.search(ln):
                scores[ln] += 3

    # C — running header frequency, normalised so long docs don't swamp B
    n_pages = max(1, len(pages) - 1)
    running: Counter[str] = Counter()
    for pg in pages[1:]:
        body = pg.split("-->", 1)[-1]
        for ln in [_clean_line(x) for x in body.splitlines() if x.strip()][:3]:
            if _plausible_name(ln, broker_slug):
                running[ln] += 1
    for ln, n in running.items():
        frac = n / n_pages
        if frac >= 0.30:
            scores[ln] += 5
        elif frac >= 0.15:
            scores[ln] += 2
        if _CORP_SUFFIX.search(ln):
            scores[ln] += 1

    if not scores:
        return "Unknown"
    return max(scores.items(), key=lambda kv: (kv[1], _CORP_SUFFIX.search(kv[0]) is not None))[0]


_DATE_RX = [
    re.compile(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+(20\d\d)\b", re.I),
    re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d\d)\b", re.I),
    re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(20\d\d)\b", re.I),
]
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def guess_date(md_text: str, url: str) -> str:
    m = re.search(r"/(20\d\d)-(\d{2})/", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    head = md_text[:6000]
    for rx in _DATE_RX:
        m = rx.search(head)
        if not m:
            continue
        g = m.groups()
        if len(g) == 3 and g[0].isdigit():
            return f"{g[2]}-{_MONTHS[g[1][:3].lower()]:02d}-{int(g[0]):02d}"
        if len(g) == 3:
            return f"{g[2]}-{_MONTHS[g[0][:3].lower()]:02d}-{int(g[1]):02d}"
        return f"{g[1]}-{_MONTHS[g[0][:3].lower()]:02d}"
    return ""


def classify_initiation(squashed: str) -> tuple[bool, str]:
    for m in INITIATION_MARKERS:
        if L.contains_fuzzy(squashed, m):
            return True, m
    for m in UPDATE_MARKERS:
        if L.contains_fuzzy(squashed, m):
            return False, f"looks like an update ({m})"
    return False, "no initiation marker found"


def fetch_one(url: str, hints: dict, session: requests.Session,
              initiations_only: bool = False) -> dict:
    row = {"url": url, "status": "", "note": "", **{k: hints.get(k, "") for k in
           ("company", "sector_guess", "date", "broker")}}
    try:
        r = session.get(url, headers=L.HTTP_HEADERS, timeout=90, allow_redirects=True)
    except Exception as e:
        row["status"] = "fetch_error"
        row["note"] = f"{type(e).__name__}: {str(e)[:120]}"
        return row

    if r.status_code != 200:
        row["status"] = "http_error"
        row["note"] = f"HTTP {r.status_code}"
        return row
    if r.content[:4] != b"%PDF":
        row["status"] = "not_pdf"
        row["note"] = f"content-type={r.headers.get('content-type','?')[:40]}"
        return row
    if len(r.content) > L.MAX_PDF_BYTES:
        row["status"] = "too_large"
        row["note"] = f"{len(r.content)} bytes"
        return row

    data = r.content
    display, slug = L.infer_broker(hints.get("broker", ""), url)
    tmp_id = L.note_id_for(url, slug, hints.get("company"), hints.get("date"))
    pdf_path = L.PDF_DIR / slug / f"{tmp_id}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(data)

    md_path = L.MD_DIR / slug / f"{tmp_id}.md"
    try:
        pages = cd.convert_markdown(pdf_path, md_path)
    except Exception as e:
        row["status"] = "convert_error"
        row["note"] = f"{type(e).__name__}: {str(e)[:120]}"
        row["pdf_path"] = str(pdf_path.relative_to(L.REPO_ROOT))
        return row

    text = md_path.read_text(encoding="utf-8")
    squashed = L.squash(text)

    # Broker is far more reliably identified from the document body than the URL.
    display, slug = L.infer_broker(hints.get("broker", ""), text[:8000], text[-6000:], url)
    if slug in L.EXCLUDED_BROKERS:
        pdf_path.unlink(missing_ok=True)
        md_path.unlink(missing_ok=True)
        row.update(broker=display, broker_slug=slug, status="excluded_broker",
                   note="Motilal Oswal excluded by instruction")
        return row

    is_init, why = classify_initiation(squashed)
    company = hints.get("company") or guess_company(text, slug, pdf_path)
    date = hints.get("date") or guess_date(text, url)
    sector = hints.get("sector_guess") or guess_sector(squashed, text)

    # Re-key the files now that broker/company/date are known.
    final_id = L.note_id_for(url, slug, company, date)
    if final_id != tmp_id:
        for src, dst in ((pdf_path, L.PDF_DIR / slug / f"{final_id}.pdf"),
                         (md_path, L.MD_DIR / slug / f"{final_id}.md")):
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                src.replace(dst)
        pdf_path = L.PDF_DIR / slug / f"{final_id}.pdf"
        md_path = L.MD_DIR / slug / f"{final_id}.md"

    if initiations_only and not is_init:
        pdf_path.unlink(missing_ok=True)
        md_path.unlink(missing_ok=True)

    row.update(
        note_id=final_id, broker=display, broker_slug=slug, company=company,
        sector_guess=sector, date=date, is_initiation="yes" if is_init else "no",
        pages=pages, words=len(text.split()), bytes=len(data),
        sha256=L.sha256_bytes(data), url=url,
        pdf_path="" if (initiations_only and not is_init) else str(pdf_path.relative_to(L.REPO_ROOT)),
        md_path="" if (initiations_only and not is_init) else str(md_path.relative_to(L.REPO_ROOT)),
        status="ok" if is_init else "not_initiation", note=why,
    )
    return row


def load_seeds(paths: list[Path]) -> list[dict]:
    out, seen = [], set()
    for p in paths:
        if not p.exists():
            print(f"WARN seed file missing: {p}", file=sys.stderr)
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [x.strip() for x in line.split("\t")]
            url = parts[0]
            if not url.lower().startswith("http") or url in seen:
                continue
            seen.add(url)
            out.append({
                "url": url,
                "company": parts[1] if len(parts) > 1 else "",
                "sector_guess": parts[2] if len(parts) > 2 else "",
                "date": parts[3] if len(parts) > 3 else "",
                "broker": parts[4] if len(parts) > 4 else "",
            })
    return out


def refresh_meta() -> None:
    """Re-derive broker/company/sector/date for rows whose markdown is already on
    disk, without re-downloading anything. Used after improving a heuristic — the
    early rows of a long fetch would otherwise keep whatever the older, worse
    extractor produced."""
    rows = L.read_manifest()
    changed = 0
    for r in rows:
        if not r.get("md_path"):
            continue
        md = L.REPO_ROOT / r["md_path"]
        if not md.exists():
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        pdf = L.REPO_ROOT / r["pdf_path"] if r.get("pdf_path") else None
        slug = r.get("broker_slug") or md.parent.name
        new_company = guess_company(text, slug, pdf if pdf and pdf.exists() else None)
        new_sector = guess_sector(L.squash(text), text)
        new_date = r.get("date") or guess_date(text, r.get("url", ""))
        if (new_company, new_sector, new_date) != (r.get("company"), r.get("sector_guess"), r.get("date")):
            print(f"  {r.get('broker',''):16} {str(r.get('company'))[:28]:28} -> {new_company[:28]:28} "
                  f"[{r.get('sector_guess','')} -> {new_sector}]")
            r["company"], r["sector_guess"], r["date"] = new_company, new_sector, new_date
            changed += 1
    L.write_manifest(rows)
    print(f"refreshed metadata on {changed} row(s)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="*", default=[], help="seed file(s) of URLs")
    ap.add_argument("--url", nargs="*", default=[], help="one-off URL(s)")
    ap.add_argument("--limit", type=int, default=0, help="max NEW downloads this run")
    ap.add_argument("--initiations-only", action="store_true",
                    help="delete pdf/md for notes that are not initiations")
    ap.add_argument("--redo", action="store_true", help="re-fetch URLs already in the manifest")
    ap.add_argument("--refresh-meta", action="store_true",
                    help="re-derive company/sector/date from cached markdown; no downloads")
    a = ap.parse_args()

    L.ensure_dirs()
    if a.refresh_meta:
        refresh_meta()
        return
    rows = L.read_manifest()
    done = {r["url"] for r in rows if r.get("url")} if not a.redo else set()

    todo = load_seeds([Path(s) for s in a.seeds]) + [{"url": u} for u in a.url]
    todo = [t for t in todo if t["url"] not in done]
    if a.limit:
        todo = todo[: a.limit]

    if not todo:
        print("nothing to do (all seed URLs already in manifest; use --redo to force)")
        return

    print(f"fetching {len(todo)} new URL(s); {len(done)} already in manifest")
    session = requests.Session()
    ok = 0
    for i, hint in enumerate(todo, 1):
        row = fetch_one(hint["url"], hint, session, a.initiations_only)
        rows = [r for r in rows if r.get("url") != row["url"]] + [row]
        L.write_manifest(rows)  # checkpoint after EVERY note — resumable by design
        flag = {"ok": "OK ", "not_initiation": "-- "}.get(row["status"], "!! ")
        print(f"{flag}[{i}/{len(todo)}] {row.get('broker','?'):22} "
              f"{str(row.get('company','?'))[:34]:34} {row.get('pages','') or '':>4}p "
              f"{row['status']}"
              + (f" ({row['note'][:60]})" if row["status"] not in ("ok",) else ""))
        if row["status"] == "ok":
            ok += 1
        time.sleep(L.POLITENESS_SECONDS)

    total_init = sum(1 for r in rows if r.get("status") == "ok")
    print(f"\ndone: +{ok} initiations this run; corpus now holds {total_init} "
          f"initiation notes across {len({r['broker_slug'] for r in rows if r.get('status')=='ok'})} brokers")
    print(f"manifest: {L.MANIFEST}")


if __name__ == "__main__":
    main()
