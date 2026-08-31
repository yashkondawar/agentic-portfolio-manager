"""Deterministic operating-KPI & unit-economics engine (v2 process, step 3b COMPUTE).

`compute_ratios.py` does accounting ratios off the P&L/BS/CF. It cannot do PER-UNIT
economics because those need OPERATING VOLUMES (production/sales quantities, capacity)
joined to SEGMENT financials — data that lives in different facts. This tool does that
join and emits the operating-KPI trend tables a real research note carries (see
docs/PROCESS_V2_REIMAGINED.md §4). Zero LLM tokens.

It is driven, when available, by `state/business_model.json` (the KPI tree + unit-economics
map from prompt 03): each KPI names its input metrics, and we divide them period by period.
When the map is absent or an input doesn't resolve, it falls back to a keyword library for
the common patterns (segment margins, realization, utilization) and reports what it could
NOT resolve, so the extraction-feedback loop can fill the gap.

Outputs:
  facts/kpis.json      — KPI fact records (method=computed, formula + input ids)
  state/kpi_trends.md  — rendered trend tables (KPI x periods, with YoY on FY)

It also enforces the SIGNATURE-KPI CONTRACT. `config/sector_registry.yaml` declares, per
tier-2 playbook, the 3-5 KPIs that define that sub-sector, and `prompts/03` instructs
module 03 to put every one of them in the KPI tree (or mark it `computable:false` naming
the missing input). Nothing used to check that. Pass `--playbook` and this tool records a
named skip for every signature KPI the run failed to produce, so the gap is visible in
`facts/kpis.json` instead of being discovered by a reader of the final note.

Usage:
  python tools/compute_kpis.py workspace/TICKER/facts/financials.json \
      --out workspace/TICKER/facts/kpis.json \
      --out-md workspace/TICKER/state/kpi_trends.md \
      [--business-model workspace/TICKER/state/business_model.json] \
      [--playbook nbfc_diversified] [--sector-registry config/sector_registry.yaml]

Design: match-tolerant (metric names vary across extractors), never crashes on missing
inputs, always reports what it resolved vs skipped. A missing business-model map or
registry degrades the run but is always REPORTED — never silently.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def norm(s):
    """Normalize a metric name for fuzzy matching: lowercase alnum tokens."""
    return set(re.findall(r"[a-z0-9]+", str(s).lower()))


class FactStore:
    """Indexes non-superseded numeric facts by (metric, period, basis), and keeps the raw
    list for fuzzy keyword resolution."""

    def __init__(self, facts):
        self.rows = []
        self.exact = {}
        for f in facts:
            if "superseded" in (f.get("flags") or []):
                continue
            v = num(f.get("value"))
            if v is None:
                continue
            metric = f.get("metric") or f.get("label") or ""
            period = f.get("period")
            basis = f.get("basis") or "na"
            row = {"metric": metric, "tokens": norm(metric) | norm(f.get("label")),
                   "period": period, "basis": basis, "value": v,
                   "id": f.get("id"), "unit": f.get("unit"), "level": f.get("level", 1)}
            self.rows.append(row)
            key = (metric, period, basis)
            if key not in self.exact or row["level"] < self.exact[key]["level"]:
                self.exact[key] = row

    def bases(self):
        b = sorted({r["basis"] for r in self.rows if r["basis"] in ("standalone", "consolidated")})
        return b or sorted({r["basis"] for r in self.rows}) or ["na"]

    def periods(self, basis, kind="FY"):
        out = set()
        for r in self.rows:
            if r["basis"] != basis:
                continue
            p = r["period"] or ""
            if kind == "FY" and re.fullmatch(r"FY\d{4}", p):
                out.add(p)
            elif kind == "Q" and re.search(r"Q[1-4]", p):
                out.add(p)
        return sorted(out)

    def get_exact(self, metric, period, basis):
        r = self.exact.get((metric, period, basis))
        return (r["value"], r["id"]) if r else (None, None)

    def find(self, must, any_of=None, period=None, basis=None):
        """Fuzzy: return (value, id, metric) whose tokens are a SUPERSET of `must` and
        intersect `any_of`, for a given period/basis. Prefer the lowest-level, shortest name."""
        must = set(must)
        cands = []
        for r in self.rows:
            if period is not None and r["period"] != period:
                continue
            if basis is not None and r["basis"] != basis:
                continue
            if not must.issubset(r["tokens"]):
                continue
            if any_of and not (set(any_of) & r["tokens"]):
                continue
            cands.append(r)
        if not cands:
            return (None, None, None)
        cands.sort(key=lambda r: (r["level"], len(r["tokens"])))
        return (cands[0]["value"], cands[0]["id"], cands[0]["metric"])


class Emitter:
    def __init__(self):
        self.facts = []
        self.skipped = []
        self._seq = 0

    def emit(self, metric, period, basis, value, unit, formula, inputs):
        if value is None:
            return None
        self._seq += 1
        rid = f"K-{re.sub(r'[^A-Z0-9]', '', metric.upper())[:20]}-{period}-{basis[:4].upper()}-{self._seq:03d}"
        self.facts.append({
            "id": rid, "metric": metric, "label": metric, "value": round(value, 4),
            "unit": unit, "period": period, "period_type": "Q" if re.search(r"Q[1-4]", period) else "FY",
            "basis": basis, "level": 2, "parent": None,
            "source": {"src_id": "DERIVED-KPI", "quote": None}, "method": "computed",
            "formula": formula, "inputs": [i for i in inputs if i],
            "confidence": "high", "load_bearing": False, "flags": ["operating_kpi"]})
        return value

    def skip(self, why):
        self.skipped.append(why)


# ---- keyword-library KPIs (fallback when business_model.json is absent/incomplete) -------
# The library is DELIBERATELY LIMITED to segment margins & EBIT-contribution, and it is
# sanity-bounded: it emits only values in a plausible range. Per-unit economics
# (realization/tonne, EBIT/tonne, utilization) are NOT attempted here because they need
# unit-matched inputs (₹cr vs '000t vs MTPA) that only the business_model.json kpi_tree
# supplies reliably — when the map is absent, those are recorded as skips, not guessed.
# Segment detection is generic: it reads any "... segment ... revenue/result/ebit" fact and
# groups by the descriptive token, so it works whatever a company calls its segments
# (e.g. NALCO's alumina segment is reported as "Chemical").
SEG_VALUE = {"revenue", "sales", "turnover", "income"}
SEG_EBIT = {"ebit", "result", "results", "profit", "pbit"}
NON_SEG_TOKENS = {"segment", "reportable", "total", "unallocated", "reconciliation", "inter",
                  "segmental", "inr", "cr", "mn", "rs", "fy", "q", "for", "the", "of", "and",
                  "before", "after", "exceptional", "interest", "items", "tax", "year"}
# comparative-year facts (extractors emit the base-period fact separately; these double-count
# and mislabel the series) — drop them from the segment scan.
COMPARATIVE = {"prior", "previous", "comparative", "py", "restated"}


def _canon_segment(tokens):
    """Short, canonical segment label from descriptive tokens; None if not a clean segment."""
    label_tokens = sorted(t.rstrip("s") for t in (tokens - NON_SEG_TOKENS - SEG_VALUE - SEG_EBIT))
    stop = {"all", "other", "othe", "misc", "various", "each", "any", "net", "gross"}
    label_tokens = [t for t in label_tokens if len(t) > 2 and t not in stop]
    # collapse duplicates like {"chemical","chemicals"} -> {"chemical"}
    label_tokens = sorted(set(label_tokens))
    if not label_tokens or len(label_tokens) > 2:   # >2 tokens => descriptive junk, not a segment
        return None
    return "_".join(label_tokens)


def _segment_facts(st, period, basis, want):
    """Return {segment_label: (value, id)} for clean, base-period segment facts carrying a
    `want` token. Works whatever a company names its segments (NALCO's alumina = 'Chemical')."""
    out = {}
    for r in st.rows:
        if r["period"] != period or r["basis"] != basis:
            continue
        t = r["tokens"]
        if ("segment" not in t and "segmental" not in t) or not (t & want) or (t & COMPARATIVE):
            continue
        label = _canon_segment(t)
        if label and label not in out:
            out[label] = (r["value"], r["id"])
    return out


def library_kpis(st, em):
    """Segment EBIT margin + EBIT contribution only, sanity-bounded, requiring >=2 segments
    for contribution so it can't be trivially 100%."""
    attempted_unit_econ = False
    for basis in st.bases():
        for kind in ("FY", "Q"):
            for period in st.periods(basis, kind):
                revs = _segment_facts(st, period, basis, SEG_VALUE)
                ebits = _segment_facts(st, period, basis, SEG_EBIT)

                # A period with SOME segment data but not enough to compute anything used to
                # vanish: no fact, no skip, no mention. NALCO's FY2023 disappeared exactly this
                # way — it carries segment REVENUE (`segment_revenue_chemical`, singular) but no
                # `segment_result_*` at all, so no margin could be formed and the year silently
                # left the trend table between FY2022 and FY2024. A gap in a trend series has to
                # be visible, or the reader assumes continuity that isn't there.
                if revs and not ebits:
                    em.skip(f"segment analytics {period} {basis}: {len(revs)} segment revenue "
                            f"fact(s) ({', '.join(sorted(revs))}) but NO segment EBIT/result fact "
                            f"— margin and contribution not computable, so this period is ABSENT "
                            f"from the segment series. Extract segment results for {period}.")
                elif ebits and not revs:
                    em.skip(f"segment analytics {period} {basis}: segment EBIT present but no "
                            f"segment revenue — margin not computable; period absent from the "
                            f"margin series.")
                elif revs and ebits:
                    unmatched = sorted(set(ebits) - set(revs))
                    if unmatched:
                        em.skip(f"segment analytics {period} {basis}: segment(s) {unmatched} have "
                                f"EBIT but no revenue under a matching label (revenue labels: "
                                f"{sorted(revs)}) — check for a naming drift between years, e.g. "
                                f"'chemical' vs 'chemicals'.")

                total_ebit = sum(v for v, _ in ebits.values()) if ebits else None
                for seg, (ev, eid) in ebits.items():
                    rv, rid = revs.get(seg, (None, None))
                    if rv:
                        margin = ev / rv * 100
                        if -100 <= margin <= 100:   # sanity bound; else likely a row/unit mismatch
                            em.emit(f"{seg}_segment_ebit_margin", period, basis, margin, "pct",
                                    f"{seg} segment ebit / {seg} segment revenue * 100", [eid, rid])
                        else:
                            em.skip(f"{seg} ebit_margin {period} {basis}: {margin:.0f}% out of range "
                                    f"(row/unit mismatch — needs business_model.json kpi_tree)")
                    if total_ebit not in (None, 0) and len(ebits) >= 2:
                        em.emit(f"{seg}_ebit_contribution", period, basis, ev / total_ebit * 100, "pct",
                                f"{seg} segment ebit / total segment ebit * 100", [eid])
                # note the per-unit economics we are deliberately NOT guessing
                if not attempted_unit_econ:
                    em.skip("per-unit economics (realization/tonne, EBIT/tonne, utilization) not "
                            "computed from the keyword library — provide state/business_model.json "
                            "kpi_tree with unit-matched inputs so these compute reliably")
                    attempted_unit_econ = True


# ---- business-model-driven KPIs (preferred path) ----------------------------------------
def tree_kpis(st, em, bm):
    """Compute each computable kpi_tree entry whose two named inputs resolve. Ratio KPIs
    with a 'pct'/'%' unit are *100; per-unit KPIs are a raw quotient.

    Returns (total_resolved, computed_kpi_names) — the names feed the signature-KPI
    coverage check in main()."""
    tree = (bm or {}).get("kpi_tree", [])
    # unit_economics.denominator is the per-unit lens prompt 03 §6 authors ("per tonne",
    # "per bed", "per key"). Used below to label per-unit KPIs whose unit the tree left
    # blank, so a quotient never renders as a bare "ratio".
    ue = (bm or {}).get("unit_economics", {}) or {}
    denom = str(ue.get("denominator") or "").strip()

    total_resolved, computed = 0, set()
    for k in tree:
        kpi = k.get("kpi") or "kpi"
        if not k.get("computable", True):
            missing = k.get("missing_input") or k.get("source_of_inputs") or "input not named"
            em.skip(f"kpi_tree '{kpi}': marked computable:false ({missing})")
            continue
        ins = k.get("inputs") or []
        if len(ins) != 2:
            # Previously a silent `continue` — a 1- or 3-input KPI vanished without trace.
            em.skip(f"kpi_tree '{kpi}': needs exactly 2 inputs to divide, got {len(ins)} "
                    f"({ins}) — split it into two-input KPIs or compute it upstream")
            continue
        unit = (k.get("unit") or "").lower()
        as_pct = ("%" in unit) or ("pct" in unit) or ("percent" in unit)
        fallback_unit = "pct" if as_pct else (denom or "ratio")

        # Optional explicit unit reconciliation. A raw quotient of two facts recorded in
        # different units is meaningless: NALCO's segment revenue is INR_cr and its production is
        # tonnes, so revenue/volume is 0.0221 of nothing — the honest INR/tonne needs x1e7.
        # `scale` makes that conversion a declared part of the business model rather than a
        # silent assumption, and it is echoed into the emitted formula so the reader sees it.
        scale = num(k.get("scale"))
        if k.get("scale") is not None and scale is None:
            em.skip(f"kpi_tree '{kpi}': scale={k.get('scale')!r} is not a number — ignored")
        if scale in (None, 0):
            scale = 1.0
        if as_pct and scale != 1.0:
            em.skip(f"kpi_tree '{kpi}': both a percent unit and scale={scale} are set; "
                    f"applying both (x100 then x{scale}) — check this is intended")

        # Per-KPI counter. This was a running total across the whole tree, so the
        # "did not resolve" skip only ever fired for the FIRST unresolvable KPI and
        # every later failure was silent.
        k_resolved = 0
        for basis in st.bases():
            for kind in ("FY", "Q"):
                for period in st.periods(basis, kind):
                    n = st.get_exact(ins[0], period, basis)
                    d = st.get_exact(ins[1], period, basis)
                    nv, nid = n if n[0] is not None else st.find(norm(ins[0]), period=period, basis=basis)[:2]
                    dv, did = d if d[0] is not None else st.find(norm(ins[1]), period=period, basis=basis)[:2]
                    if nv is not None and dv:
                        val = nv / dv * (100 if as_pct else 1) * scale
                        formula = f"{ins[0]} / {ins[1]}"
                        if as_pct:
                            formula += " * 100"
                        if scale != 1.0:
                            formula += f" * {scale:g}   [unit reconciliation, declared in kpi_tree]"
                        em.emit(kpi, period, basis, val, k.get("unit") or fallback_unit,
                                formula, [nid, did])
                        k_resolved += 1
        if k_resolved:
            total_resolved += k_resolved
            computed.add(kpi)
        else:
            em.skip(f"kpi_tree '{kpi}': inputs {ins} did not resolve in any period")
    return total_resolved, computed


# ---- signature-KPI coverage (the enforcement prompts/03 promises) ------------------------
# prompts/03 tells module 03 that "every signature KPI must appear in your kpi_tree —
# either computable:true with its inputs named, or computable:false naming the missing
# input. Silently omitting one is a defect." Nothing checked that. This does.
_UNIT_SUFFIXES = {"pct", "inr", "usd", "x", "days", "count", "bps", "mn", "cr", "kwh",
                  "tonne", "sqft", "scm", "bbl", "gw", "mw", "watt", "msf"}


def _kpi_tokens(name):
    """Token set for a KPI name, minus unit suffixes and filler, singularised, so
    `ebitda_per_tonne_inr` matches an emitted `ebitda_per_tonne` and the tree's
    `chemicals_segment_ebit_margin` matches the library's `chemical_segment_ebit_margin`.
    Singularisation mirrors `_canon_segment`, which already does `rstrip("s")`."""
    drop = _UNIT_SUFFIXES | {"per", "of", "to", "the", "and"}
    return {t.rstrip("s") for t in norm(name) if t not in drop} - {""}


def signature_coverage(em, signature_kpis, computed, playbook):
    """Record a named skip for every registry signature KPI the run did not produce.
    Returns (n_covered, n_missing)."""
    if not signature_kpis:
        return (0, 0)
    emitted = {f["metric"] for f in em.facts} | set(computed)
    emitted_tokens = [(m, _kpi_tokens(m)) for m in emitted]
    covered = 0
    for sig in signature_kpis:
        want = _kpi_tokens(sig)
        if not want:
            continue
        if any(want and want.issubset(toks) for _, toks in emitted_tokens):
            covered += 1
        else:
            em.skip(f"signature KPI '{sig}' (playbook '{playbook}') not computed — "
                    f"prompts/03 must place it in the kpi_tree with named inputs, or mark it "
                    f"computable:false naming the missing input")
    return (covered, len(signature_kpis) - covered)


def load_signature_kpis(registry_path, playbook):
    """Read `playbooks.<slug>.signature_kpis` from config/sector_registry.yaml.
    Returns (list, note). Never raises — a missing registry degrades to no check."""
    if not playbook:
        return ([], "no playbook slug supplied (pass --playbook, from state/triage.json)")
    p = Path(registry_path)
    if not p.exists():
        return ([], f"registry not found at {registry_path}")
    try:
        import yaml
    except ImportError:
        return ([], "pyyaml not installed — signature-KPI coverage check skipped")
    try:
        reg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001 - never crash the KPI run on a bad registry
        return ([], f"registry unreadable ({type(e).__name__}: {e})")
    entry = ((reg.get("playbooks") or {}).get(playbook)) or {}
    if not entry:
        return ([], f"playbook '{playbook}' not declared in the registry")
    return (list(entry.get("signature_kpis") or []), "")


# ---- rendering --------------------------------------------------------------------------
def render_md(em, ticker, st=None):
    """Group KPI facts into trend tables: one table per basis, metric rows x period columns,
    FY first then quarters, with a trailing YoY column on FY tables.

    GAP VISIBILITY: a fiscal year for which no KPI resolved used to vanish from the header
    entirely, so a FY2020-FY2025 series printed as five columns and read as complete. The
    NALCO run shipped exactly that — FY2023 absent with no acknowledgement. We now include
    every FY the facts store knows about *within the span of the computed series*, so a
    missing year shows as a row of em-dashes instead of disappearing. Years outside the
    span (e.g. an FY2030 capex projection) are still excluded."""
    by_basis = {}
    for f in em.facts:
        by_basis.setdefault(f["basis"], []).append(f)
    out = [f"# {ticker} — operating KPI trends", "",
           "*Computed by tools/compute_kpis.py from extracted volume/segment facts. "
           "Interpretation (why a KPI moved) is the analyst's job — this is the data, not the read.*", "",
           "*An all-`—` column means the facts store has that period but no KPI input resolved "
           "for it. That is a disclosed gap, not an absent year.*", ""]
    for basis in sorted(by_basis):
        rows = by_basis[basis]
        metrics = sorted({r["metric"] for r in rows})
        fys = sorted({r["period"] for r in rows if r["period_type"] == "FY"})
        qs = sorted({r["period"] for r in rows if r["period_type"] == "Q"})
        if st is not None and fys:
            known = [p for p in st.periods(basis, "FY") if fys[0] <= p <= fys[-1]]
            fys = sorted(set(fys) | set(known))
        cols = fys + qs
        if not cols:
            continue
        out.append(f"## {basis.title()} — {len(metrics)} KPIs x {len(cols)} periods")
        out.append("")
        header = ["KPI", "unit"] + cols + (["YoY (last FY)"] if len(fys) >= 2 else [])
        out.append("| " + " | ".join(header) + " |")
        out.append("|" + "---|" * len(header))
        idx = {(r["metric"], r["period"]): r for r in rows}
        for m in metrics:
            unit = next((r["unit"] for r in rows if r["metric"] == m), "")
            cells = []
            for c in cols:
                r = idx.get((m, c))
                cells.append(f"{r['value']:.2f}" if r else "—")
            yoy = ""
            if len(fys) >= 2:
                a = idx.get((m, fys[-2])); b = idx.get((m, fys[-1]))
                if a and b and a["value"]:
                    yoy = f"{(b['value']/a['value']-1)*100:+.1f}%"
            row = [m, unit] + cells + ([yoy] if len(fys) >= 2 else [])
            out.append("| " + " | ".join(row) + " |")
        out.append("")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("facts_file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--business-model", default=None)
    ap.add_argument("--ticker", default="TICKER")
    ap.add_argument("--sector-registry", default="config/sector_registry.yaml",
                    help="registry to read signature_kpis from for the coverage check")
    ap.add_argument("--playbook", default=None,
                    help="tier-2 playbook slug (from state/triage.json). Enables the "
                         "signature-KPI coverage check.")
    a = ap.parse_args()

    data = json.loads(Path(a.facts_file).read_text(encoding="utf-8"))
    facts = data["facts"] if isinstance(data, dict) else data
    st = FactStore(facts)
    em = Emitter()

    bm, computed = None, set()
    if a.business_model:
        bmp = Path(a.business_model)
        if bmp.exists():
            bm = json.loads(bmp.read_text(encoding="utf-8"))
        else:
            # Previously a silent fall-through to the keyword library — a typo'd path
            # produced a degraded run with no indication anything was wrong. This is
            # exactly how the NALCO run ended up with 4 segment ratios and no per-unit
            # economics while looking successful.
            em.skip(f"--business-model path does not exist: {a.business_model} — "
                    f"ran the keyword library only; per-unit economics NOT computed")
            print(f"WARN business-model map not found at {a.business_model}; "
                  f"degrading to the keyword library", file=sys.stderr)
    if bm is None and not a.business_model:
        em.skip("no --business-model supplied — keyword library only; per-unit economics "
                "need state/business_model.json's kpi_tree (prompts/03)")

    n_tree = 0
    if bm:
        n_tree, computed = tree_kpis(st, em, bm)
    # Always also run the library — it fills what the tree missed. Dedup was exact-name,
    # which let the library re-emit a quantity the tree had already computed under a
    # slightly different label (`chemical_segment_ebit_margin` vs the tree's
    # `chemicals_segment_ebit_margin`), putting two rows for one thing in the note.
    # Dedup on the unit-stripped token set instead, per (period, basis). Tree wins.
    before = len(em.facts)
    # MERGE the library into the tree rather than choosing between them.
    #
    # Two earlier attempts were both wrong. Exact-name dedup let the library re-emit a
    # quantity the tree already had under a near-identical label
    # (`chemical_segment_ebit_margin` vs `chemicals_...`), giving two rows for one thing.
    # Dropping every colliding library fact then *lost* values the library could resolve
    # and the tree could not, turning a real FY2022 print into an em-dash.
    #
    # So: match on metric IDENTITY (unit-stripped, singularised tokens); where the library
    # duplicates a tree quantity, RENAME it to the tree's label and keep it only for
    # periods the tree left empty. One complete row per quantity, tree-preferred, no data
    # discarded. The `formula` field still records which path produced each cell.
    tree_name_by_id = {frozenset(_kpi_tokens(f["metric"])): f["metric"] for f in em.facts}
    filled = {(f["metric"], f["period"], f["basis"]) for f in em.facts}
    library_kpis(st, em)
    kept, merged, dropped = [], 0, 0
    for f in em.facts[before:]:
        ident = frozenset(_kpi_tokens(f["metric"]))
        tree_name = tree_name_by_id.get(ident)
        if tree_name:
            key = (tree_name, f["period"], f["basis"])
            if key in filled:
                dropped += 1
                continue
            f["metric"], f["label"] = tree_name, tree_name
            f["formula"] += "  [keyword library — tree inputs unresolved for this period]"
            merged += 1
        key = (f["metric"], f["period"], f["basis"])
        if key in filled:
            dropped += 1
            continue
        filled.add(key)
        kept.append(f)
    em.facts = em.facts[:before] + kept
    if merged or dropped:
        em.skip(f"library/tree merge: {merged} library fact(s) folded into a tree KPI to "
                f"fill periods the tree could not resolve; {dropped} exact duplicate(s) dropped")

    # Signature-KPI coverage against the sector registry.
    sig, note = load_signature_kpis(a.sector_registry, a.playbook)
    if note:
        em.skip(f"signature-KPI coverage check not run: {note}")
    n_cov, n_missing = signature_coverage(em, sig, computed, a.playbook or "?")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"facts": em.facts, "skipped": em.skipped,
         "signature_kpi_coverage": {"playbook": a.playbook, "declared": len(sig),
                                    "covered": n_cov, "missing": n_missing}},
        indent=2, ensure_ascii=False), encoding="utf-8")
    Path(a.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out_md).write_text(render_md(em, a.ticker, st), encoding="utf-8")

    cov = (f"; signature KPIs {n_cov}/{len(sig)} covered" if sig else "")
    print(f"OK: {len(em.facts)} KPI facts ({n_tree} from business-model tree, rest from library) "
          f"-> {a.out}; trends -> {a.out_md}; {len(em.skipped)} unresolved (see out file){cov}")
    if sig and n_missing:
        print(f"WARN {n_missing} signature KPI(s) for playbook '{a.playbook}' were not "
              f"computed — see `skipped` in {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
