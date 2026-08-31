"""Deterministic ratio engine. Replaces LLM arithmetic for Fin_processing + threshold screens.

Usage:
  python tools/compute_ratios.py workspace/TICKER/facts/financials.json \
      --out workspace/TICKER/facts/derived_metrics.json \
      --flags workspace/TICKER/state/red_flags.json \
      [--thresholds thresholds.json]

Produces derived fact records (method=computed, formula + input ids -> audit trail preserved)
and seeds threshold-triggered red-flag CANDIDATES into the shared ledger (forensic adjudicates).
Skips gracefully whatever inputs are missing and reports what was skipped and why.
Reported-over-computed rule lives downstream: reported ratio facts (method=reported) are kept
by the renderer; these computed values serve as cross-checks and gap-fillers.
"""
import argparse, json
from pathlib import Path

DEFAULT_THRESHOLDS = {
    "cfo_to_ebitda_min_pct": 70.0,
    "other_income_share_of_cfo_max_pct": 20.0,
    "dso_yoy_increase_max_pct": 20.0,
    "asset_vs_revenue_growth_gap_pp": 20.0,
    "capex_cfo_spike_x_of_median": 1.5,
}

# canonical metric names expected from prompts/10 extraction
M = dict(
    rev="revenue_from_operations", oi="other_income", texp="total_expenses",
    mat="cost_of_materials", pur="purchases_stock_in_trade", chg="changes_in_inventories",
    emp="employee_benefits", fin="finance_costs", dep="depreciation_amortization",
    pbt="pbt", tax="tax", pat="pat", eps="eps_diluted",
    ta="total_assets", eq="total_equity", inv="inventories", tr="trade_receivables",
    tp="trade_payables", cash="cash_and_bank", bc="borrowings_current",
    bnc="borrowings_noncurrent", ca="current_assets", cl="current_liabilities",
    ada="allowance_doubtful_accounts", gr="gross_receivables",
    cfo="cfo", ppe_buy="purchase_of_ppe", int_buy="purchase_of_intangibles",
    ppe_sell="sale_of_ppe",
)


# Registry `skip_ratios` names are analyst vocabulary; this tool's metric names are its
# own. Where the two disagree about the SAME quantity, map it here rather than bending
# either side. `receivable_days` and this tool's `dso_days` are the same ratio, and token
# matching alone would never connect them — which would silently leave a lender's
# receivable-days row in the output while the registry claimed it was suppressed.
RATIO_ALIASES = {
    "receivable_days": ["dso_days"],
    "payable_days": ["dpo_days", "creditor_days"],
    "cash_conversion_cycle": ["ccc_days", "working_capital_days"],
    "ebitda_margin": ["ebitda_pct_revenue"],
    "ev_ebitda": ["ev_to_ebitda"],
}


def _ratio_tokens(name):
    """Normalised token set for matching a registry `skip_ratios` entry against an emitted
    metric name. Singularised so `receivable_days` matches `receivables_days`."""
    import re as _re
    drop = {"pct", "ratio", "x", "the", "of", "to", "per"}
    return {t.rstrip("s") for t in _re.findall(r"[a-z0-9]+", str(name).lower())
            if t not in drop} - {""}


def _skip_matchers(skip_ratios):
    """For each declared skip, the list of token-sets that should match it (the name
    itself plus any alias)."""
    out = []
    for s in skip_ratios:
        variants = [s] + RATIO_ALIASES.get(s, [])
        out.append((s, [_ratio_tokens(v) for v in variants]))
    return out


def load_skip_ratios(registry_path, family):
    """Read `families.<family>.skip_ratios` from config/sector_registry.yaml.
    Returns (list, note). Never raises — a missing registry simply suppresses nothing."""
    if not family:
        return ([], "no --family supplied (pass the family slug from state/triage.json)")
    p = Path(registry_path)
    if not p.exists():
        return ([], f"registry not found at {registry_path}")
    try:
        import yaml
    except ImportError:
        return ([], "pyyaml not installed")
    try:
        reg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001 - never crash the ratio run on a bad registry
        return ([], f"registry unreadable ({type(e).__name__}: {e})")
    fam = (reg.get("families") or {}).get(family)
    if fam is None:
        return ([], f"family '{family}' not declared in the registry")
    return (list(fam.get("skip_ratios") or []), "")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class Store:
    def __init__(self, facts):
        self.map = {}
        for f in facts:
            if "superseded" in (f.get("flags") or []):
                continue
            k = (f.get("metric"), f.get("period"), f.get("basis"))
            v = num(f.get("value"))
            if v is None:
                continue
            # level-1 record wins if duplicate metric key at different levels
            if k not in self.map or (f.get("level", 1) < self.map[k][2]):
                self.map[k] = (v, f.get("id"), f.get("level", 1), f.get("unit"))

    def get(self, metric, period, basis):
        return self.map.get((metric, period, basis), (None, None, None, None))[:2]

    def periods(self, basis, period_type="FY"):
        ps = {p for (m, p, b) in self.map if b == basis and p.startswith("FY") and len(p) == 6}
        return sorted(ps)

    def bases(self):
        return sorted({b for (_, _, b) in self.map if b in ("consolidated", "standalone")})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("facts_file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--flags", default=None)
    ap.add_argument("--thresholds", default=None)
    ap.add_argument("--sector-registry", default="config/sector_registry.yaml",
                    help="registry to read families.<family>.skip_ratios from")
    ap.add_argument("--family", default=None,
                    help="sector family slug (from state/triage.json). Enables the "
                         "sector ratio suppression T2 documents.")
    a = ap.parse_args()

    th = dict(DEFAULT_THRESHOLDS)
    if a.thresholds:
        th.update(json.loads(Path(a.thresholds).read_text(encoding="utf-8")))

    data = json.loads(Path(a.facts_file).read_text(encoding="utf-8"))
    facts = data["facts"] if isinstance(data, dict) else data
    st = Store(facts)

    derived, skipped, candidates = [], [], []
    seq = [0]

    # Sector-driven ratio suppression. `prompts/02_triage_rules.md` T2 states that
    # "compute_ratios.py skips the ratios named in the registry's skip_ratios" — that was
    # true of nothing until this block existed. A lender has no inventory days and no
    # EBITDA margin; emitting them produces confident nonsense that then flows into the
    # peer table. Gating inside the single emit() closure means every ratio is covered.
    skip_ratios, skip_note = load_skip_ratios(a.sector_registry, a.family)
    if skip_note:
        skipped.append(f"sector ratio-suppression not applied: {skip_note}")
    matchers = _skip_matchers(skip_ratios)
    suppressed = {}

    def emit(metric, period, basis, value, formula, inputs, unit="pct"):
        if value is None:
            return None
        toks = _ratio_tokens(metric)
        for name, variants in matchers:
            if any(v and v.issubset(toks) for v in variants):
                suppressed[name] = suppressed.get(name, 0) + 1
                return None
        seq[0] += 1
        rid = f"D-{metric.upper()}-{period}-{basis[:4].upper()}-{seq[0]:03d}"
        derived.append({"id": rid, "metric": metric, "label": metric, "value": round(value, 4),
                        "unit": unit, "period": period, "period_type": "FY", "basis": basis,
                        "level": 1, "parent": None,
                        "source": {"src_id": "DERIVED", "quote": None}, "method": "computed",
                        "formula": formula, "inputs": [i for i in inputs if i],
                        "confidence": "high", "load_bearing": False, "flags": []})
        return value

    def flag(category, text, threshold, evidence, period, basis):
        candidates.append({"id": None, "category": category,
                           "flag": f"{text} ({period}, {basis})",
                           "metric_evidence": [e for e in evidence if e],
                           "threshold": threshold, "why_chain": [], "management_story": None,
                           "status": "candidate", "severity": "medium", "confidence": "high",
                           "owner": "compute_ratios", "open_question_ids": []})

    for basis in st.bases() or ["consolidated"]:
        fys = st.periods(basis)
        prev = {}
        series = {}
        for fy in fys:
            g = lambda m: st.get(M[m], fy, basis)
            rev, rev_id = g("rev"); oi, oi_id = g("oi"); pbt, pbt_id = g("pbt")
            fin, fin_id = g("fin"); dep, dep_id = g("dep"); pat, pat_id = g("pat")
            texp, texp_id = g("texp"); ta, ta_id = g("ta"); eq, eq_id = g("eq")
            invv, inv_id = g("inv"); tr, tr_id = g("tr"); tp, tp_id = g("tp")
            cash, cash_id = g("cash"); bc, bc_id = g("bc"); bnc, bnc_id = g("bnc")
            cfo, cfo_id = g("cfo"); pb, pb_id = g("ppe_buy"); ib, ib_id = g("int_buy")
            ps, ps_id = g("ppe_sell"); mat, mat_id = g("mat"); pur, pur_id = g("pur")
            chg, chg_id = g("chg"); ca, ca_id = g("ca"); cl, cl_id = g("cl")
            ada, ada_id = g("ada"); gr, gr_id = g("gr")

            # EBITDA: two routes, prefer the P&L-bottom-up one
            ebitda = None; ebitda_f = None; ebitda_in = []
            if None not in (pbt, dep, fin) and oi is not None:
                ebitda = pbt + dep + fin - oi
                ebitda_f = "pbt + dep + finance_costs - other_income"
                ebitda_in = [pbt_id, dep_id, fin_id, oi_id]
            elif None not in (rev, texp, fin, dep):
                ebitda = rev - (texp - fin - dep)
                ebitda_f = "revenue - (total_expenses - finance_costs - dep)"
                ebitda_in = [rev_id, texp_id, fin_id, dep_id]
            if ebitda is not None:
                emit("ebitda", fy, basis, ebitda, ebitda_f, ebitda_in, unit="INR_cr")
                if rev:
                    emit("ebitda_margin", fy, basis, ebitda / rev * 100, f"({ebitda_f})/revenue*100", ebitda_in + [rev_id])
            else:
                skipped.append(f"ebitda {fy} {basis}: missing pbt/dep/fin/oi and texp route")

            if rev and pat is not None:
                emit("net_margin", fy, basis, pat / rev * 100, "pat/revenue*100", [pat_id, rev_id])
            if rev is not None and None not in (mat, pur, chg):
                gm = (rev - mat - pur - chg) / rev * 100
                emit("gross_margin", fy, basis, gm, "(rev-materials-purchases-inv_change)/rev*100",
                     [rev_id, mat_id, pur_id, chg_id])

            debt = (bc or 0) + (bnc or 0) if (bc is not None or bnc is not None) else None
            ebit = (pbt + fin) if None not in (pbt, fin) else None
            p = prev
            avg_eq = (eq + p["eq"]) / 2 if (eq is not None and p.get("eq") is not None) else eq
            avg_ta = (ta + p["ta"]) / 2 if (ta is not None and p.get("ta") is not None) else ta
            if pat is not None and avg_eq:
                emit("roe", fy, basis, pat / avg_eq * 100, "pat/avg_equity*100", [pat_id, eq_id])
            if ebit is not None and (eq is not None or debt is not None):
                ce = (eq or 0) + (debt or 0)
                pce = (p.get("eq") or 0) + (p.get("debt") or 0) if p else None
                avg_ce = (ce + pce) / 2 if pce else ce
                if avg_ce:
                    emit("roce", fy, basis, ebit / avg_ce * 100, "(pbt+fin)/avg(equity+debt)*100",
                         [pbt_id, fin_id, eq_id, bc_id, bnc_id])
            if rev and avg_ta:
                emit("asset_turnover", fy, basis, rev / avg_ta, "revenue/avg_total_assets", [rev_id, ta_id], unit="x")

            dso = inv_d = pay_d = None
            if rev:
                if tr is not None:
                    dso = emit("dso_days", fy, basis, tr / rev * 365, "receivables/revenue*365", [tr_id, rev_id], unit="days")
                if invv is not None:
                    inv_d = emit("inventory_days", fy, basis, invv / rev * 365, "inventory/revenue*365", [inv_id, rev_id], unit="days")
                if tp is not None:
                    pay_d = emit("payable_days", fy, basis, tp / rev * 365, "payables/revenue*365", [tp_id, rev_id], unit="days")
            if None not in (dso, inv_d, pay_d):
                emit("ccc_days", fy, basis, dso + inv_d - pay_d, "dso+doh-dpo", [], unit="days")

            if ca is not None and cl:
                emit("current_ratio", fy, basis, ca / cl, "current_assets/current_liabilities", [ca_id, cl_id], unit="x")
            if debt is not None and eq:
                emit("debt_equity", fy, basis, debt / eq, "total_borrowings/equity", [bc_id, bnc_id, eq_id], unit="x")
            if ebit is not None and fin:
                emit("interest_coverage", fy, basis, ebit / fin, "(pbt+fin)/finance_costs", [pbt_id, fin_id], unit="x")
            net_debt = (debt - cash) if (debt is not None and cash is not None) else None
            if net_debt is not None:
                emit("net_debt", fy, basis, net_debt, "borrowings-cash", [bc_id, bnc_id, cash_id], unit="INR_cr")
                if ebitda:
                    emit("net_debt_ebitda", fy, basis, net_debt / ebitda, "net_debt/ebitda", [], unit="x")

            capex = None
            if pb is not None:
                capex = pb + (ib or 0) - (ps or 0)
                emit("net_capex", fy, basis, capex, "ppe_purchase+intangibles-ppe_sale (fin. investments excluded)",
                     [pb_id, ib_id, ps_id], unit="INR_cr")
            if cfo is not None and capex is not None:
                emit("fcf", fy, basis, cfo - capex, "cfo-net_capex", [cfo_id], unit="INR_cr")
            if cfo is not None and ebitda:
                ratio = cfo / ebitda * 100
                emit("cfo_to_ebitda", fy, basis, ratio, "cfo/ebitda*100", [cfo_id])
                if ratio < th["cfo_to_ebitda_min_pct"]:
                    flag("cash_flow", f"CFO/EBITDA {ratio:.1f}% below {th['cfo_to_ebitda_min_pct']}% floor",
                         f"cfo_to_ebitda_min_pct={th['cfo_to_ebitda_min_pct']}", [cfo_id], fy, basis)
            if cfo and oi is not None and cfo != 0:
                share = oi / cfo * 100
                emit("other_income_share_of_cfo", fy, basis, share, "other_income/cfo*100", [oi_id, cfo_id])
                if share > th["other_income_share_of_cfo_max_pct"]:
                    flag("earnings_quality", f"Other income {share:.1f}% of CFO exceeds {th['other_income_share_of_cfo_max_pct']}%",
                         f"other_income_share_of_cfo_max_pct={th['other_income_share_of_cfo_max_pct']}", [oi_id, cfo_id], fy, basis)
            if ada is not None and gr:
                emit("ada_pct_gross_receivables", fy, basis, ada / gr * 100, "ada/gross_receivables*100", [])

            # YoY growth + common-size for core lines
            for mkey, mid, val in (("revenue_from_operations", rev_id, rev), ("pat", pat_id, pat),
                                   ("total_assets", ta_id, ta), ("cfo", cfo_id, cfo),
                                   ("ebitda", None, ebitda)):
                if val is not None and p.get(mkey) not in (None, 0):
                    emit(f"{mkey}_yoy", fy, basis, (val / p[mkey] - 1) * 100, f"{mkey} yoy", [mid])
            if rev:
                for mkey, mid, val in (("other_income", oi_id, oi), ("employee_benefits", None, st.get(M["emp"], fy, basis)[0]),
                                       ("finance_costs", fin_id, fin), ("depreciation_amortization", dep_id, dep)):
                    if val is not None:
                        emit(f"{mkey}_pct_revenue", fy, basis, val / rev * 100, f"{mkey}/revenue*100", [mid, rev_id])

            series[fy] = {"rev": rev, "ta": ta, "dso": dso, "capex": capex, "cfo": cfo}
            prev = {"eq": eq, "ta": ta, "debt": debt,
                    "revenue_from_operations": rev, "pat": pat, "total_assets": ta,
                    "cfo": cfo, "ebitda": ebitda}

        # multi-year screens
        fylist = [fy for fy in fys if series[fy]["rev"] is not None]
        if len(fylist) >= 3:
            f0, fN = fylist[0], fylist[-1]
            if series[f0]["rev"] and series[f0]["ta"] and series[fN]["ta"]:
                rev_g = (series[fN]["rev"] / series[f0]["rev"] - 1) * 100
                ta_g = (series[fN]["ta"] / series[f0]["ta"] - 1) * 100
                if ta_g - rev_g > th["asset_vs_revenue_growth_gap_pp"]:
                    flag("balance_sheet",
                         f"Total assets grew {ta_g:.0f}% vs revenue {rev_g:.0f}% over {f0}-{fN} "
                         f"(gap > {th['asset_vs_revenue_growth_gap_pp']}pp)",
                         f"asset_vs_revenue_growth_gap_pp={th['asset_vs_revenue_growth_gap_pp']}", [], fN, basis)
        for i in range(1, len(fylist)):
            d0, d1 = series[fylist[i - 1]]["dso"], series[fylist[i]]["dso"]
            if d0 and d1 and (d1 / d0 - 1) * 100 > th["dso_yoy_increase_max_pct"]:
                flag("working_capital", f"DSO rose {(d1 / d0 - 1) * 100:.0f}% YoY ({d0:.0f}->{d1:.0f} days)",
                     f"dso_yoy_increase_max_pct={th['dso_yoy_increase_max_pct']}", [], fylist[i], basis)
        capexes = [series[fy]["capex"] for fy in fylist if series[fy]["capex"]]
        if len(capexes) >= 3:
            med = sorted(capexes)[len(capexes) // 2]
            for fy in fylist:
                c, cf = series[fy]["capex"], series[fy]["cfo"]
                if c and med and c > th["capex_cfo_spike_x_of_median"] * med:
                    flag("balance_sheet", f"Capex {c:.0f} is >{th['capex_cfo_spike_x_of_median']}x multi-year median {med:.0f}"
                         + (f"; capex/CFO={c / cf:.1f}x" if cf else ""),
                         f"capex_cfo_spike_x_of_median={th['capex_cfo_spike_x_of_median']}", [], fy, basis)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    # Record what sector suppression removed, so a reader of kpis/ratios can tell
    # "not applicable to this sector" apart from "we failed to compute it".
    for name, n in sorted(suppressed.items()):
        skipped.append(f"ratio '{name}' suppressed for family '{a.family}' "
                       f"({n} period/basis combination(s)) — not applicable to this sector "
                       f"per config/sector_registry.yaml families.{a.family}.skip_ratios")

    # A declared skip that never matched is either a ratio this tool doesn't compute (fine,
    # but then the registry over-claims) or a naming mismatch needing a RATIO_ALIASES entry
    # (a real defect — the ratio is still in the output while the registry says it isn't).
    # Either way the reader should be told which it is, not left to assume suppression worked.
    unmatched = [s for s in skip_ratios if s not in suppressed]
    if unmatched:
        skipped.append(
            f"declared skip_ratios that matched nothing this tool emits: {unmatched} — "
            f"either compute_ratios.py does not compute them (registry over-claims), or the "
            f"name differs from this tool's metric name and needs a RATIO_ALIASES entry")

    Path(a.out).write_text(json.dumps(
        {"facts": derived, "skipped": skipped,
         "sector_suppression": {"family": a.family, "declared": skip_ratios,
                                "suppressed_counts": suppressed, "unmatched": unmatched}},
        indent=2), encoding="utf-8")

    if suppressed:
        print(f"     sector suppression ({a.family}): "
              + ", ".join(f"{k}x{v}" for k, v in sorted(suppressed.items())))

    if a.flags:
        fp = Path(a.flags)
        ledger = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else []
        existing = {(e.get("category"), e.get("flag")) for e in ledger}
        nxt = len(ledger)
        added = 0
        for c in candidates:
            if (c["category"], c["flag"]) in existing:
                continue
            nxt += 1
            c["id"] = f"RF-{nxt:03d}"
            ledger.append(c); added += 1
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        print(f"OK: {len(derived)} derived facts -> {a.out}; {added} new flag candidates -> {a.flags}; "
              f"{len(skipped)} skipped (see out file)")
    else:
        print(f"OK: {len(derived)} derived facts -> {a.out}; {len(candidates)} candidates (no --flags given); "
              f"{len(skipped)} skipped")


if __name__ == "__main__":
    main()
