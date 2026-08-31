"""EPS-bridge deterministic checker — zero tokens ("never ask an LLM what a
script can compute").

Ported from the fund repo (D:\\Documents\\Claude\\1Projects\\AI Native Fund,
research/equity_researcher/tools/eps_bridge_check.py) — this standalone copy
has no registry/, so thresholds are loaded from a local
config/eps_bridge_thresholds.yaml (an inlined duplicate of the fund's
registry/rules/eps_bridge.yaml; see docs/DESIGN_DECISIONS.md) instead of a
registry lookup. See prompts/60_buy_side.md for the full prose doctrine each
rule below implements (this project's self-contained copy of the fund's
knowledge/references/methodology/eps_bridge.md).

Reads the merged facts store (workspace/<TICKER>/facts/financials.json,
optionally also facts/derived_metrics.json for computed ratios such as
ebit/interest_coverage) and computes, per rule, a PASS/FAIL/NA verdict plus
the numbers behind it. Threshold resolution order:
  1. --thresholds <path>  (explicit JSON or YAML file, same keys as
     config/eps_bridge_thresholds.yaml)
  2. config/eps_bridge_thresholds.yaml (auto-discovered relative to this
     file, i.e. <project_root>/config/eps_bridge_thresholds.yaml)
  3. built-in DEFAULT_THRESHOLDS (mirrored from that yaml) — so the tool
     still runs standalone even if the config file is missing or PyYAML
     isn't installed.

Output shape (per rule_id):
    {"status": "PASS"|"FAIL"|"NA", "value": ..., "threshold": ..., "note": str}

rule_ids (fixed set, per plan):
  revenue_growth_consistency, eps_growth_20pct, gross_margin_trend,
  receivables_pct_revenue_trend, interest_vs_ebit_growth,
  dilution_consecutive, cfo_positive_expansion, dna_adjusted_eps_growth,
  interest_coverage

Every rule degrades to NA (never a fabricated PASS/FAIL) whenever its
required inputs are missing across the available periods — sparse
extractions from real documents WILL have holes; this checker must say so
honestly rather than guess.

Usage:
  python tools/eps_bridge_check.py workspace/TICKER/facts/financials.json \
      --out workspace/TICKER/state/eps_bridge_check.json \
      [--derived workspace/TICKER/facts/derived_metrics.json] \
      [--thresholds thresholds.yaml] [--sector auto_engineering]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# --- default thresholds (mirrors config/eps_bridge_thresholds.yaml values) -
# Kept here, duplicated deliberately, so this tool runs standalone (no
# registry, no fund import) even when the config file / PyYAML is
# unavailable — same self-containment posture as compute_ratios.py's
# DEFAULT_THRESHOLDS.
DEFAULT_THRESHOLDS = {
    "eps_growth_min_pct": 20.0,
    "revenue_growth_min_pct": 0.0,
    "gross_margin_trend_tolerance_pp": 0.0,
    "receivables_pct_revenue_rising_tolerance_pp": 0.0,
    "interest_vs_ebit_growth_max_ratio": 1.0,
    "dilution_consecutive_years_flag": 2,
    "cfo_positive_expansion_min": 0.0,
    "cfo_positive_capex_multiple_of_median": 1.2,
    "interest_coverage_min_x": 3.0,
    "dna_adjusted_eps_growth_min_pct": 0.0,
    "sector_overrides": {},
}

# local config default path: <project_root>/config/eps_bridge_thresholds.yaml
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "eps_bridge_thresholds.yaml"

# canonical metric names (matches compute_ratios.py's M dict / prompts/10 vocabulary)
M = dict(
    rev="revenue_from_operations", mat="cost_of_materials",
    pur="purchases_stock_in_trade", chg="changes_in_inventories",
    fin="finance_costs", dep="depreciation_amortization", pbt="pbt",
    eps="eps_diluted", shares="weighted_shares", tr="trade_receivables",
    cfo="cfo", capex="net_capex",
)


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_facts(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    recs = data.get("facts", data) if isinstance(data, dict) else data
    return [r for r in recs if isinstance(r, dict)]


def is_live(rec: dict) -> bool:
    return "superseded" not in (rec.get("flags") or [])


class Store:
    """Mirrors compute_ratios.py's Store: (metric, period, basis) -> best
    live value, preferring the level-1 (face-of-statement) record when the
    same key appears at multiple levels."""

    def __init__(self, facts: list[dict]):
        self.map: dict[tuple, tuple] = {}
        for f in facts:
            if not is_live(f):
                continue
            k = (f.get("metric"), f.get("period"), f.get("basis"))
            v = num(f.get("value"))
            if v is None:
                continue
            if k not in self.map or (f.get("level", 1) < self.map[k][2]):
                self.map[k] = (v, f.get("id"), f.get("level", 1))

    def get(self, metric, period, basis):
        return self.map.get((metric, period, basis), (None, None, None))[:2]

    def periods(self, basis):
        ps = {p for (m, p, b) in self.map if b == basis and p and p.startswith("FY") and len(p) == 6}
        return sorted(ps)

    def bases(self):
        bs = sorted({b for (_, _, b) in self.map if b in ("consolidated", "standalone")})
        return bs or ["consolidated"]


def _load_thresholds_file(path: Path) -> dict:
    """Loads a thresholds file that is either flat-value JSON/YAML or the
    {value, status, note} block shape used by config/eps_bridge_thresholds.yaml.
    Returns a flat {key: value} dict (sector_overrides kept as-is)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # PyYAML — see requirements.txt
        except ImportError as exc:
            raise RuntimeError(
                f"PyYAML is required to read {path} (pip install pyyaml), "
                "or pass a JSON file to --thresholds instead."
            ) from exc
        raw = yaml.safe_load(text) or {}
    else:
        raw = json.loads(text)

    flat: dict = {}
    for key, val in raw.items():
        if key == "sector_overrides":
            flat[key] = val or {}
        elif isinstance(val, dict) and "value" in val:
            flat[key] = val["value"]
        else:
            flat[key] = val
    return flat


def _override_chain(sector: str | None, registry_path: str | None) -> list[str]:
    """Slugs whose sector_overrides apply, least-specific first.

    `--sector` accepts EITHER a family slug or a tier-2 playbook slug from
    config/sector_registry.yaml, and the two layer: the family override is the
    base and the playbook override refines it. So `--sector life_insurance`
    picks up `bfsi`'s overrides (no gross-margin line, EBIT-based rules N/A)
    and then life_insurance's own (accounting EPS is structurally
    uninformative for a life insurer). Before this, resolution was a single
    flat lookup and the yaml never said which kind of slug the key was.

    An unrecognised slug still resolves to itself, so a caller may key an
    override on any label it likes; it simply gets no family layer.
    """
    if not sector:
        return []
    chain: list[str] = []
    reg_path = Path(registry_path) if registry_path else (
        Path(__file__).resolve().parent.parent / "config" / "sector_registry.yaml")
    if reg_path.exists():
        try:
            import yaml  # noqa: PLC0415 - optional; only needed to resolve the family
            reg = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
            pb = (reg.get("playbooks") or {}).get(sector) or {}
            fam = pb.get("family")
            if fam and fam != sector:
                chain.append(fam)
        except Exception:
            pass  # registry unreadable -> fall back to the flat lookup
    chain.append(sector)
    return chain


def _merge_thresholds(thresholds_path: str | None, sector: str | None,
                      registry_path: str | None = None) -> dict:
    th = dict(DEFAULT_THRESHOLDS)

    # resolve which file to read: explicit --thresholds, else the local
    # config/eps_bridge_thresholds.yaml if it exists, else fall back to
    # DEFAULT_THRESHOLDS only.
    resolved_path: Path | None = None
    if thresholds_path:
        resolved_path = Path(thresholds_path)
    elif DEFAULT_CONFIG_PATH.exists():
        resolved_path = DEFAULT_CONFIG_PATH

    if resolved_path and resolved_path.exists():
        loaded = _load_thresholds_file(resolved_path)
        th.update({k: v for k, v in loaded.items() if k != "sector_overrides"})
        th["sector_overrides"] = loaded.get("sector_overrides", th.get("sector_overrides", {}))

    applied: list[str] = []
    for slug in _override_chain(sector, registry_path):
        override = (th.get("sector_overrides") or {}).get(slug) or {}
        if override:
            applied.append(slug)
        for key, block in override.items():
            # sector_overrides blocks mirror the {value, status, note} shape
            # used in the yaml; a bare scalar is also accepted for callers
            # that pass a flattened thresholds dict.
            th[key] = block.get("value") if isinstance(block, dict) else block
    th["_overrides_applied"] = applied
    return th


def na(note: str, threshold=None) -> dict:
    return {"status": "NA", "value": None, "threshold": threshold, "note": note}


def _series_for_basis(store: Store, basis: str) -> dict[str, dict]:
    """One row of raw metric values per FY period, for a given basis."""
    out = {}
    for fy in store.periods(basis):
        row = {}
        for key, metric in M.items():
            row[key] = store.get(metric, fy, basis)[0]
        out[fy] = row
    return out


# --- individual rules -------------------------------------------------------

def check_revenue_growth_consistency(series: dict, fys: list[str], th: dict) -> dict:
    floor = th["revenue_growth_min_pct"]
    growths = []
    for i in range(1, len(fys)):
        prev, cur = series[fys[i - 1]]["rev"], series[fys[i]]["rev"]
        if prev in (None, 0) or cur is None:
            continue
        growths.append((fys[i], (cur / prev - 1) * 100))
    if len(growths) == 0:
        return na("insufficient revenue data across periods to assess growth consistency", floor)
    failing = [(fy, g) for fy, g in growths if g < floor]
    status = "FAIL" if failing else "PASS"
    return {
        "status": status,
        "value": {fy: round(g, 2) for fy, g in growths},
        "threshold": floor,
        "note": (
            f"revenue YoY growth below {floor}% floor in {', '.join(fy for fy, _ in failing)}"
            if failing else f"revenue YoY growth >= {floor}% in every period with data"
        ),
    }


def check_eps_growth_20pct(series: dict, fys: list[str], th: dict) -> dict:
    floor = th["eps_growth_min_pct"]
    growths = []
    for i in range(1, len(fys)):
        prev, cur = series[fys[i - 1]]["eps"], series[fys[i]]["eps"]
        if prev in (None, 0) or cur is None:
            continue
        growths.append((fys[i], (cur / prev - 1) * 100))
    if len(growths) == 0:
        return na("insufficient EPS data across periods to assess growth consistency", floor)
    failing = [(fy, g) for fy, g in growths if g < floor]
    status = "FAIL" if failing else "PASS"
    return {
        "status": status,
        "value": {fy: round(g, 2) for fy, g in growths},
        "threshold": floor,
        "note": (
            f"EPS YoY growth below {floor}% in {', '.join(fy for fy, _ in failing)} — "
            "consistency requirement not met (EPS-bridge doctrine section i)"
            if failing else f"EPS YoY growth >= {floor}% in every period with data — consistent rerating candidate"
        ),
    }


def _gross_margin(row: dict) -> float | None:
    rev, mat, pur, chg = row["rev"], row["mat"], row["pur"], row["chg"]
    if rev in (None, 0) or None in (mat, pur, chg):
        return None
    return (rev - mat - pur - chg) / rev * 100


def check_gross_margin_trend(series: dict, fys: list[str], th: dict) -> dict:
    tol = th["gross_margin_trend_tolerance_pp"]
    margins = {fy: _gross_margin(series[fy]) for fy in fys}
    pairs = [(fys[i - 1], fys[i]) for i in range(1, len(fys))
             if margins[fys[i - 1]] is not None and margins[fys[i]] is not None]
    if not pairs:
        return na("insufficient cost-of-materials/purchases/inventory-change data to compute gross margin trend", tol)
    deltas = {b: round(margins[b] - margins[a], 2) for a, b in pairs}
    failing = {fy: d for fy, d in deltas.items() if d < tol}
    status = "FAIL" if failing else "PASS"
    return {
        "status": status,
        "value": deltas,
        "threshold": tol,
        "note": (
            f"gross margin fell (or rose < {tol}pp) YoY in {', '.join(failing)}"
            if failing else "gross margin flat-or-rising in every period with data"
        ),
    }


def check_receivables_pct_revenue_trend(series: dict, fys: list[str], th: dict) -> dict:
    tol = th["receivables_pct_revenue_rising_tolerance_pp"]
    pct = {}
    for fy in fys:
        rev, tr = series[fy]["rev"], series[fy]["tr"]
        if rev not in (None, 0) and tr is not None:
            pct[fy] = tr / rev * 100
    fys_with_data = [fy for fy in fys if fy in pct]
    if len(fys_with_data) < 2:
        return na("insufficient trade_receivables/revenue data to assess trend", tol)
    deltas = {}
    for i in range(1, len(fys_with_data)):
        a, b = fys_with_data[i - 1], fys_with_data[i]
        deltas[b] = round(pct[b] - pct[a], 2)
    rising = {fy: d for fy, d in deltas.items() if d > tol}
    status = "FAIL" if rising else "PASS"
    return {
        "status": status,
        "value": deltas,
        "threshold": tol,
        "note": (
            f"receivables/revenue rose > {tol}pp YoY in {', '.join(rising)} — working-capital flag (EPS-bridge doctrine section iv)"
            if rising else "receivables/revenue flat-or-improving in every period with data"
        ),
    }


def _ebit(row: dict) -> float | None:
    pbt, fin = row["pbt"], row["fin"]
    if None in (pbt, fin):
        return None
    return pbt + fin


def check_interest_vs_ebit_growth(series: dict, fys: list[str], th: dict) -> dict:
    max_ratio = th["interest_vs_ebit_growth_max_ratio"]
    evaluated = {}
    skipped = []
    for i in range(1, len(fys)):
        a, b = fys[i - 1], fys[i]
        ebit_a, ebit_b = _ebit(series[a]), _ebit(series[b])
        fin_a, fin_b = series[a]["fin"], series[b]["fin"]
        if None in (ebit_a, ebit_b, fin_a, fin_b):
            continue
        ebit_growth = ebit_b - ebit_a
        interest_growth = fin_b - fin_a
        if ebit_growth <= 0 or interest_growth <= 0:
            # rule only applies to debt-funded expansion years — both EBIT
            # and interest must be growing for the comparison to be
            # meaningful (EPS-bridge doctrine section iii); a shrinking EBIT
            # or a falling interest bill isn't the scenario this rule
            # targets.
            skipped.append(b)
            continue
        evaluated[b] = round(abs(interest_growth) / abs(ebit_growth), 4)
    if not evaluated:
        note = "no year with both EBIT and finance-cost growth data present to evaluate debt-funding discipline"
        if skipped:
            note += f" (periods with data but not a co-growth year, so out of scope: {', '.join(skipped)})"
        return na(note, max_ratio)
    failing = {fy: r for fy, r in evaluated.items() if r >= max_ratio}
    status = "FAIL" if failing else "PASS"
    return {
        "status": status,
        "value": evaluated,
        "threshold": max_ratio,
        "note": (
            f"absolute interest growth >= absolute EBIT growth (ratio >= {max_ratio}) in {', '.join(failing)} — "
            "debt-funded expansion failing the net-positive-EPS test (EPS-bridge doctrine section iii)"
            if failing else "interest growth stayed below EBIT growth in every co-growth year evaluated"
        ),
    }


def check_dilution_consecutive(series: dict, fys: list[str], th: dict) -> dict:
    consecutive_flag_at = int(th["dilution_consecutive_years_flag"])
    fys_with_shares = [fy for fy in fys if series[fy]["shares"] is not None]
    if len(fys_with_shares) < 2:
        return na("insufficient weighted_shares data to assess dilution history", consecutive_flag_at)
    is_dilution_year = {}
    for i in range(1, len(fys_with_shares)):
        a, b = fys_with_shares[i - 1], fys_with_shares[i]
        is_dilution_year[b] = series[b]["shares"] > series[a]["shares"]
    # find the longest run of consecutive True values
    longest_run = 0
    run = 0
    run_periods: list[str] = []
    longest_run_periods: list[str] = []
    for fy in fys_with_shares[1:]:
        if is_dilution_year[fy]:
            run += 1
            run_periods.append(fy)
        else:
            run = 0
            run_periods = []
        if run > longest_run:
            longest_run = run
            longest_run_periods = list(run_periods)
    dilution_years = [fy for fy, v in is_dilution_year.items() if v]
    status = "FAIL" if longest_run >= consecutive_flag_at else "PASS"
    return {
        "status": status,
        "value": {"dilution_years": dilution_years, "longest_consecutive_run": longest_run},
        "threshold": consecutive_flag_at,
        "note": (
            f"share count rose in {longest_run} consecutive years ({', '.join(longest_run_periods)}) — "
            f">= {consecutive_flag_at} triggers the consecutive-dilution flag (EPS-bridge doctrine section iii)"
            if status == "FAIL"
            else (
                f"dilution occurred in {len(dilution_years)} year(s) but never {consecutive_flag_at}+ consecutively — acceptable per doctrine"
                if dilution_years else "no YoY increase in share count in any period with data"
            )
        ),
    }


def check_cfo_positive_expansion(series: dict, fys: list[str], th: dict) -> dict:
    cfo_floor = th["cfo_positive_expansion_min"]
    capex_mult = th["cfo_positive_capex_multiple_of_median"]
    capexes = [series[fy]["capex"] for fy in fys if series[fy]["capex"] is not None and series[fy]["capex"] > 0]
    if len(capexes) < 3:
        return na("fewer than 3 periods of net_capex data — cannot establish a median to identify expansion years", cfo_floor)
    median_capex = sorted(capexes)[len(capexes) // 2]
    expansion_fys = [
        fy for fy in fys
        if series[fy]["capex"] is not None and median_capex and series[fy]["capex"] > capex_mult * median_capex
    ]
    if not expansion_fys:
        return na(
            f"no period's net_capex exceeded {capex_mult}x the multi-year median ({median_capex:.1f}) — no expansion phase detected",
            cfo_floor,
        )
    cfo_by_fy = {}
    unknown = []
    for fy in expansion_fys:
        cfo = series[fy]["cfo"]
        if cfo is None:
            unknown.append(fy)
        else:
            cfo_by_fy[fy] = cfo
    if not cfo_by_fy:
        return na(f"expansion year(s) identified ({', '.join(expansion_fys)}) but CFO data missing for all of them", cfo_floor)
    failing = {fy: v for fy, v in cfo_by_fy.items() if v < cfo_floor}
    status = "FAIL" if failing else "PASS"
    note = (
        f"CFO negative during expansion year(s) {', '.join(failing)} (capex > {capex_mult}x median) — "
        "operating cashflow must stay positive through expansion (EPS-bridge doctrine section iv)"
        if failing else f"CFO stayed >= {cfo_floor} in every identified expansion year ({', '.join(cfo_by_fy)})"
    )
    if unknown:
        note += f"; CFO unavailable for expansion year(s) {', '.join(unknown)} — not counted either way"
    return {"status": status, "value": cfo_by_fy, "threshold": cfo_floor, "note": note}


def check_dna_adjusted_eps_growth(series: dict, fys: list[str], th: dict) -> dict:
    floor = th["dna_adjusted_eps_growth_min_pct"]
    # D&A-adjusted EPS: eps + (dep / shares) roughly restates EPS as if D&A
    # were added back per share, so a swing in D&A doesn't mechanically
    # drive the YoY delta — EPS-bridge doctrine section ii, D&A rung.
    adjusted = {}
    for fy in fys:
        row = series[fy]
        eps, dep, shares = row["eps"], row["dep"], row["shares"]
        if None in (eps, dep, shares) or shares == 0:
            continue
        adjusted[fy] = eps + dep / shares
    fys_adj = [fy for fy in fys if fy in adjusted]
    if len(fys_adj) < 2:
        return na("insufficient eps_diluted/depreciation_amortization/weighted_shares data to compute a D&A-adjusted EPS series", floor)
    growths = {}
    for i in range(1, len(fys_adj)):
        a, b = fys_adj[i - 1], fys_adj[i]
        if adjusted[a] in (None, 0):
            continue
        growths[b] = round((adjusted[b] / adjusted[a] - 1) * 100, 2)
    if not growths:
        return na("D&A-adjusted EPS series available but no valid non-zero base period to compute YoY growth", floor)
    failing = {fy: g for fy, g in growths.items() if g < floor}
    status = "FAIL" if failing else "PASS"
    return {
        "status": status,
        "value": growths,
        "threshold": floor,
        "note": (
            f"D&A-adjusted EPS growth below {floor}% in {', '.join(failing)} — "
            "underlying growth doesn't survive the D&A add-back (EPS-bridge doctrine section ii)"
            if failing else f"D&A-adjusted EPS growth >= {floor}% in every period with data"
        ),
    }


def check_interest_coverage(series: dict, fys: list[str], th: dict) -> dict:
    min_x = th["interest_coverage_min_x"]
    fys_with_data = [fy for fy in fys if _ebit(series[fy]) is not None and series[fy]["fin"]]
    if not fys_with_data:
        return na("insufficient pbt/finance_costs data to compute interest coverage", min_x)
    latest = fys_with_data[-1]
    ebit = _ebit(series[latest])
    fin = series[latest]["fin"]
    coverage = round(ebit / fin, 2)
    status = "FAIL" if coverage < min_x else "PASS"
    return {
        "status": status,
        "value": {latest: coverage},
        "threshold": min_x,
        "note": (
            f"interest coverage {coverage}x in {latest} below {min_x}x floor"
            if status == "FAIL" else f"interest coverage {coverage}x in {latest} clears the {min_x}x floor"
        ),
    }


RULES = {
    "revenue_growth_consistency": check_revenue_growth_consistency,
    "eps_growth_20pct": check_eps_growth_20pct,
    "gross_margin_trend": check_gross_margin_trend,
    "receivables_pct_revenue_trend": check_receivables_pct_revenue_trend,
    "interest_vs_ebit_growth": check_interest_vs_ebit_growth,
    "dilution_consecutive": check_dilution_consecutive,
    "cfo_positive_expansion": check_cfo_positive_expansion,
    "dna_adjusted_eps_growth": check_dna_adjusted_eps_growth,
    "interest_coverage": check_interest_coverage,
}


def run_checks(facts: list[dict], thresholds: dict, basis: str | None = None) -> dict:
    """Runs every rule for the given (or best-available) basis. Returns
    {rule_id: {status, value, threshold, note}, ...} plus a top-level
    "_basis" key recording which basis (consolidated/standalone) was used —
    consolidated preferred when both are present, matching compute_ratios.py's
    convention of iterating st.bases()."""
    store = Store(facts)
    bases = store.bases()
    if basis and basis in bases:
        chosen_basis = basis
    elif "consolidated" in bases:
        chosen_basis = "consolidated"
    else:
        chosen_basis = bases[0] if bases else "consolidated"

    fys = store.periods(chosen_basis)
    series = _series_for_basis(store, chosen_basis)

    if not fys:
        result = {rule_id: na(f"no fiscal-year data found for basis={chosen_basis!r}") for rule_id in RULES}
        result["_basis"] = chosen_basis
        result["_periods"] = []
        return result

    result = {rule_id: fn(series, fys, thresholds) for rule_id, fn in RULES.items()}
    result["_basis"] = chosen_basis
    result["_periods"] = fys
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("facts_file", help="merged facts store, e.g. workspace/TICKER/facts/financials.json")
    ap.add_argument("--derived", default=None, help="optional derived_metrics.json (currently informational; rules compute from raw facts directly)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--thresholds", default=None, help="JSON or YAML file overriding config/eps_bridge_thresholds.yaml (auto-loaded if this flag is omitted and the file exists)")
    ap.add_argument("--sector", default=None,
                    help="family OR tier-2 playbook slug from config/sector_registry.yaml. Both "
                         "layer: the family override is the base, the playbook override refines it "
                         "(see sector_overrides in config/eps_bridge_thresholds.yaml)")
    ap.add_argument("--sector-registry", default=None,
                    help="registry used to resolve a playbook slug to its family "
                         "(default: config/sector_registry.yaml)")
    ap.add_argument("--basis", default=None, choices=["consolidated", "standalone"])
    a = ap.parse_args()

    facts = load_facts(Path(a.facts_file))
    if a.derived:
        facts += load_facts(Path(a.derived))

    thresholds = _merge_thresholds(a.thresholds, a.sector, a.sector_registry)
    result = run_checks(facts, thresholds, basis=a.basis)

    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    counts = {}
    for rule_id in RULES:
        counts[result[rule_id]["status"]] = counts.get(result[rule_id]["status"], 0) + 1
    applied = thresholds.get("_overrides_applied") or []
    ov = f"; sector_overrides applied: {applied}" if applied else (
        f"; no sector_overrides for {a.sector!r}" if a.sector else "")
    print(f"OK: eps_bridge_check -> {out_path}; basis={result['_basis']}; rule verdicts: {counts}{ov}")


if __name__ == "__main__":
    main()
