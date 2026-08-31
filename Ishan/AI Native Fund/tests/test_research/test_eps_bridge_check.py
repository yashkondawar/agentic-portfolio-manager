"""Golden tests for research/equity_researcher/tools/eps_bridge_check.py —
the deterministic (zero-token) EPS-bridge checker implementing
knowledge/references/methodology/eps_bridge.md, thresholds from
registry/rules/eps_bridge.yaml.

Not an importable package under src/, so the module is loaded directly by
file path (mirrors tests/test_research/test_convert_and_statement.py's
pattern for build_comprehensive_statement.py).

Each of the 9 rule_ids gets an engineered PASS + FAIL + NA fixture (NA via
either missing metrics entirely or too few periods to establish a trend/
median), built directly against DEFAULT_THRESHOLDS so the goldens don't
silently drift if registry/rules/eps_bridge.yaml's values change without a
matching test update. Fact records use the same shape as
build_comprehensive_statement's fixtures (id/metric/value/period/basis/
level/...); only fields eps_bridge_check.py actually reads
(metric/period/basis/value/flags/level) are populated.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ER_TOOLS_DIR = REPO_ROOT / "research" / "equity_researcher" / "tools"
CHECK_PATH = ER_TOOLS_DIR / "eps_bridge_check.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ebc():
    return _load_module("eps_bridge_check", CHECK_PATH)


def fact(metric, period, value, basis="consolidated", level=1, flags=None):
    return {
        "id": f"F-{metric}-{period}",
        "metric": metric,
        "value": value,
        "period": period,
        "period_type": "FY",
        "basis": basis,
        "level": level,
        "flags": flags or [],
    }


def th(ebc):
    return dict(ebc.DEFAULT_THRESHOLDS)


# ---------------------------------------------------------------------------
# revenue_growth_consistency
# ---------------------------------------------------------------------------


def test_revenue_growth_consistency_pass(ebc):
    facts = [
        fact("revenue_from_operations", "FY2023", 1000),
        fact("revenue_from_operations", "FY2024", 1100),
        fact("revenue_from_operations", "FY2025", 1250),
    ]
    result = ebc.run_checks(facts, th(ebc))
    assert result["revenue_growth_consistency"]["status"] == "PASS"


def test_revenue_growth_consistency_fail(ebc):
    facts = [
        fact("revenue_from_operations", "FY2023", 1000),
        fact("revenue_from_operations", "FY2024", 1100),
        fact("revenue_from_operations", "FY2025", 900),  # YoY decline < 0.0 floor
    ]
    result = ebc.run_checks(facts, th(ebc))
    r = result["revenue_growth_consistency"]
    assert r["status"] == "FAIL"
    assert "FY2025" in r["note"]


def test_revenue_growth_consistency_na_no_data(ebc):
    facts = [fact("cfo", "FY2024", 100)]  # no revenue facts at all
    result = ebc.run_checks(facts, th(ebc))
    assert result["revenue_growth_consistency"]["status"] == "NA"


# ---------------------------------------------------------------------------
# eps_growth_20pct
# ---------------------------------------------------------------------------


def test_eps_growth_20pct_pass(ebc):
    facts = [
        fact("eps_diluted", "FY2023", 10.0),
        fact("eps_diluted", "FY2024", 12.5),  # +25%
        fact("eps_diluted", "FY2025", 16.0),  # +28%
    ]
    result = ebc.run_checks(facts, th(ebc))
    assert result["eps_growth_20pct"]["status"] == "PASS"


def test_eps_growth_20pct_fail(ebc):
    facts = [
        fact("eps_diluted", "FY2023", 10.0),
        fact("eps_diluted", "FY2024", 11.0),  # +10%, below 20% floor
        fact("eps_diluted", "FY2025", 13.5),  # +22.7%, single strong print isn't enough
    ]
    result = ebc.run_checks(facts, th(ebc))
    r = result["eps_growth_20pct"]
    assert r["status"] == "FAIL"
    assert "FY2024" in r["note"]


def test_eps_growth_20pct_na_single_period(ebc):
    facts = [fact("eps_diluted", "FY2024", 10.0)]  # only one period -> no YoY possible
    result = ebc.run_checks(facts, th(ebc))
    assert result["eps_growth_20pct"]["status"] == "NA"


# ---------------------------------------------------------------------------
# gross_margin_trend
# ---------------------------------------------------------------------------


def _gm_facts(rev_a, mat_a, rev_b, mat_b, pa="FY2024", pb="FY2025"):
    return [
        fact("revenue_from_operations", pa, rev_a),
        fact("cost_of_materials", pa, mat_a),
        fact("purchases_stock_in_trade", pa, 0),
        fact("changes_in_inventories", pa, 0),
        fact("revenue_from_operations", pb, rev_b),
        fact("cost_of_materials", pb, mat_b),
        fact("purchases_stock_in_trade", pb, 0),
        fact("changes_in_inventories", pb, 0),
    ]


def test_gross_margin_trend_pass(ebc):
    # FY2024 margin: (1000-600)/1000=40%; FY2025: (1200-660)/1200=45% -> rising
    facts = _gm_facts(1000, 600, 1200, 660)
    result = ebc.run_checks(facts, th(ebc))
    assert result["gross_margin_trend"]["status"] == "PASS"


def test_gross_margin_trend_fail(ebc):
    # FY2024 margin 40%; FY2025: (1200-800)/1200=33.3% -> falling
    facts = _gm_facts(1000, 600, 1200, 800)
    result = ebc.run_checks(facts, th(ebc))
    assert result["gross_margin_trend"]["status"] == "FAIL"


def test_gross_margin_trend_na_missing_cost_data(ebc):
    facts = [
        fact("revenue_from_operations", "FY2024", 1000),
        fact("revenue_from_operations", "FY2025", 1200),
        # no cost_of_materials/purchases/changes_in_inventories at all
    ]
    result = ebc.run_checks(facts, th(ebc))
    assert result["gross_margin_trend"]["status"] == "NA"


# ---------------------------------------------------------------------------
# receivables_pct_revenue_trend (esp. rising flag)
# ---------------------------------------------------------------------------


def test_receivables_pct_revenue_trend_pass_flat(ebc):
    facts = [
        fact("revenue_from_operations", "FY2023", 1000),
        fact("trade_receivables", "FY2023", 100),  # 10%
        fact("revenue_from_operations", "FY2024", 1100),
        fact("trade_receivables", "FY2024", 110),  # 10%
        fact("revenue_from_operations", "FY2025", 1200),
        fact("trade_receivables", "FY2025", 108),  # 9% -> improving
    ]
    result = ebc.run_checks(facts, th(ebc))
    assert result["receivables_pct_revenue_trend"]["status"] == "PASS"


def test_receivables_pct_revenue_trend_fail_rising(ebc):
    facts = [
        fact("revenue_from_operations", "FY2023", 1000),
        fact("trade_receivables", "FY2023", 100),  # 10.0%
        fact("revenue_from_operations", "FY2024", 1100),
        fact("trade_receivables", "FY2024", 150),  # 13.6% -- rising
        fact("revenue_from_operations", "FY2025", 1200),
        fact("trade_receivables", "FY2025", 220),  # 18.3% -- rising again
    ]
    result = ebc.run_checks(facts, th(ebc))
    r = result["receivables_pct_revenue_trend"]
    assert r["status"] == "FAIL"
    assert "FY2024" in r["note"] and "FY2025" in r["note"]


def test_receivables_pct_revenue_trend_na_insufficient_data(ebc):
    facts = [
        fact("revenue_from_operations", "FY2025", 1200),
        fact("trade_receivables", "FY2025", 220),  # only one period with both
    ]
    result = ebc.run_checks(facts, th(ebc))
    assert result["receivables_pct_revenue_trend"]["status"] == "NA"


# ---------------------------------------------------------------------------
# interest_vs_ebit_growth (both directions)
# ---------------------------------------------------------------------------


def _ebit_int_facts(pbt_a, fin_a, pbt_b, fin_b, pa="FY2024", pb="FY2025"):
    return [
        fact("pbt", pa, pbt_a),
        fact("finance_costs", pa, fin_a),
        fact("pbt", pb, pbt_b),
        fact("finance_costs", pb, fin_b),
    ]


def test_interest_vs_ebit_growth_pass(ebc):
    # EBIT_a = 800+50=850; EBIT_b=1000+60=1060 -> ebit_growth=210
    # interest_growth = 60-50=10; ratio=10/210=0.048 < 1.0 -> PASS
    facts = _ebit_int_facts(pbt_a=800, fin_a=50, pbt_b=1000, fin_b=60)
    result = ebc.run_checks(facts, th(ebc))
    assert result["interest_vs_ebit_growth"]["status"] == "PASS"


def test_interest_vs_ebit_growth_fail(ebc):
    # EBIT_a = pbt_a+fin_a = 800+50 = 850
    # EBIT_b = pbt_b+fin_b = 795+200 = 995 -> ebit_growth = 145
    # interest_growth = 200-50 = 150 -> ratio = 150/145 = 1.034 >= 1.0 -> FAIL
    facts = _ebit_int_facts(pbt_a=800, fin_a=50, pbt_b=795, fin_b=200)
    result = ebc.run_checks(facts, th(ebc))
    r = result["interest_vs_ebit_growth"]
    assert r["status"] == "FAIL"
    assert "FY2025" in r["note"]


def test_interest_vs_ebit_growth_na_shrinking_ebit(ebc):
    # EBIT shrinking (pbt+fin lower in FY2025 than FY2024) with interest
    # also shrinking -> both legs skipped (rule only applies to co-growth
    # years) -> NA.
    facts = _ebit_int_facts(pbt_a=800, fin_a=100, pbt_b=700, fin_b=80)
    result = ebc.run_checks(facts, th(ebc))
    assert result["interest_vs_ebit_growth"]["status"] == "NA"


# ---------------------------------------------------------------------------
# dilution_consecutive (esp. consecutive vs isolated)
# ---------------------------------------------------------------------------


def test_dilution_consecutive_pass_isolated_dilution(ebc):
    facts = [
        fact("weighted_shares", "FY2022", 100),
        fact("weighted_shares", "FY2023", 110),  # dilution year 1
        fact("weighted_shares", "FY2024", 110),  # flat -- breaks the run
        fact("weighted_shares", "FY2025", 120),  # dilution year 2, isolated
    ]
    result = ebc.run_checks(facts, th(ebc))
    r = result["dilution_consecutive"]
    assert r["status"] == "PASS"
    assert r["value"]["longest_consecutive_run"] == 1


def test_dilution_consecutive_fail_back_to_back(ebc):
    facts = [
        fact("weighted_shares", "FY2022", 100),
        fact("weighted_shares", "FY2023", 110),  # dilution
        fact("weighted_shares", "FY2024", 125),  # dilution again -- consecutive
        fact("weighted_shares", "FY2025", 130),  # and again
    ]
    result = ebc.run_checks(facts, th(ebc))
    r = result["dilution_consecutive"]
    assert r["status"] == "FAIL"
    assert r["value"]["longest_consecutive_run"] == 3


def test_dilution_consecutive_na_insufficient_data(ebc):
    facts = [fact("weighted_shares", "FY2025", 100)]  # only one period
    result = ebc.run_checks(facts, th(ebc))
    assert result["dilution_consecutive"]["status"] == "NA"


# ---------------------------------------------------------------------------
# cfo_positive_expansion
# ---------------------------------------------------------------------------


def _cfo_capex_facts(capexes, cfos, start_year=2021):
    facts = []
    for i, (capex, cfo) in enumerate(zip(capexes, cfos)):
        period = f"FY{start_year + i}"
        facts.append(fact("net_capex", period, capex))
        if cfo is not None:
            facts.append(fact("cfo", period, cfo))
    return facts


def test_cfo_positive_expansion_pass(ebc):
    # median capex of [100,110,105,300] (sorted: 100,105,110,300 -> median idx2=110)
    # expansion year: capex > 1.2*110=132 -> FY2024 (300) is expansion; CFO positive there
    facts = _cfo_capex_facts(
        capexes=[100, 110, 105, 300], cfos=[50, 55, 52, 80]
    )
    result = ebc.run_checks(facts, th(ebc))
    assert result["cfo_positive_expansion"]["status"] == "PASS"


def test_cfo_positive_expansion_fail_negative_cfo_during_expansion(ebc):
    facts = _cfo_capex_facts(
        capexes=[100, 110, 105, 300], cfos=[50, 55, 52, -20]
    )
    result = ebc.run_checks(facts, th(ebc))
    r = result["cfo_positive_expansion"]
    assert r["status"] == "FAIL"


def test_cfo_positive_expansion_na_too_few_capex_periods(ebc):
    facts = _cfo_capex_facts(capexes=[100, 300], cfos=[50, 80])  # only 2 periods
    result = ebc.run_checks(facts, th(ebc))
    assert result["cfo_positive_expansion"]["status"] == "NA"


# ---------------------------------------------------------------------------
# dna_adjusted_eps_growth
# ---------------------------------------------------------------------------


def _dna_facts(eps_a, dep_a, shares_a, eps_b, dep_b, shares_b, pa="FY2024", pb="FY2025"):
    return [
        fact("eps_diluted", pa, eps_a),
        fact("depreciation_amortization", pa, dep_a),
        fact("weighted_shares", pa, shares_a),
        fact("eps_diluted", pb, eps_b),
        fact("depreciation_amortization", pb, dep_b),
        fact("weighted_shares", pb, shares_b),
    ]


def test_dna_adjusted_eps_growth_pass(ebc):
    # adj_a = 10 + 50/100 = 10.5; adj_b = 13 + 55/100 = 13.55 -> +29% growth
    facts = _dna_facts(10.0, 50.0, 100.0, 13.0, 55.0, 100.0)
    result = ebc.run_checks(facts, th(ebc))
    assert result["dna_adjusted_eps_growth"]["status"] == "PASS"


def test_dna_adjusted_eps_growth_fail(ebc):
    # EPS looks flat-to-up nominally but D&A add-back shows a real decline:
    # adj_a = 10 + 80/100 = 10.8; adj_b = 9 + 70/100 = 9.7 -> -10.2% growth
    facts = _dna_facts(10.0, 80.0, 100.0, 9.0, 70.0, 100.0)
    result = ebc.run_checks(facts, th(ebc))
    assert result["dna_adjusted_eps_growth"]["status"] == "FAIL"


def test_dna_adjusted_eps_growth_na_missing_dep(ebc):
    facts = [
        fact("eps_diluted", "FY2024", 10.0),
        fact("weighted_shares", "FY2024", 100.0),
        fact("eps_diluted", "FY2025", 13.0),
        fact("weighted_shares", "FY2025", 100.0),
        # no depreciation_amortization facts at all
    ]
    result = ebc.run_checks(facts, th(ebc))
    assert result["dna_adjusted_eps_growth"]["status"] == "NA"


# ---------------------------------------------------------------------------
# interest_coverage
# ---------------------------------------------------------------------------


def test_interest_coverage_pass(ebc):
    # latest FY: EBIT = pbt+fin = 900+50=950; coverage=950/50=19x >= 3.0
    facts = [
        fact("pbt", "FY2024", 800),
        fact("finance_costs", "FY2024", 60),
        fact("pbt", "FY2025", 900),
        fact("finance_costs", "FY2025", 50),
    ]
    result = ebc.run_checks(facts, th(ebc))
    r = result["interest_coverage"]
    assert r["status"] == "PASS"
    assert r["value"]["FY2025"] == pytest.approx(19.0)


def test_interest_coverage_fail(ebc):
    # latest FY: EBIT = 100+80=180; coverage=180/80=2.25x < 3.0
    facts = [
        fact("pbt", "FY2024", 800),
        fact("finance_costs", "FY2024", 60),
        fact("pbt", "FY2025", 100),
        fact("finance_costs", "FY2025", 80),
    ]
    result = ebc.run_checks(facts, th(ebc))
    r = result["interest_coverage"]
    assert r["status"] == "FAIL"
    assert r["value"]["FY2025"] == pytest.approx(2.25)


def test_interest_coverage_na_no_finance_costs(ebc):
    facts = [fact("pbt", "FY2025", 900)]  # no finance_costs at all
    result = ebc.run_checks(facts, th(ebc))
    assert result["interest_coverage"]["status"] == "NA"


# ---------------------------------------------------------------------------
# whole-run shape / basis / sector-override / CLI plumbing
# ---------------------------------------------------------------------------


def test_run_checks_returns_all_nine_rule_ids_plus_metadata(ebc):
    facts = [fact("revenue_from_operations", "FY2025", 1000)]
    result = ebc.run_checks(facts, th(ebc))
    for rule_id in ebc.RULES:
        assert rule_id in result
    assert set(ebc.RULES) == {
        "revenue_growth_consistency", "eps_growth_20pct", "gross_margin_trend",
        "receivables_pct_revenue_trend", "interest_vs_ebit_growth",
        "dilution_consecutive", "cfo_positive_expansion",
        "dna_adjusted_eps_growth", "interest_coverage",
    }
    assert result["_basis"] == "consolidated"
    assert result["_periods"] == ["FY2025"]


def test_run_checks_no_periods_all_na(ebc):
    result = ebc.run_checks([], th(ebc))
    assert all(result[rule_id]["status"] == "NA" for rule_id in ebc.RULES)
    assert result["_periods"] == []


def test_run_checks_prefers_consolidated_over_standalone(ebc):
    facts = [
        fact("revenue_from_operations", "FY2025", 1000, basis="standalone"),
        fact("revenue_from_operations", "FY2025", 1200, basis="consolidated"),
    ]
    result = ebc.run_checks(facts, th(ebc))
    assert result["_basis"] == "consolidated"


def test_run_checks_respects_explicit_basis_override(ebc):
    facts = [
        fact("revenue_from_operations", "FY2025", 1000, basis="standalone"),
        fact("revenue_from_operations", "FY2025", 1200, basis="consolidated"),
    ]
    result = ebc.run_checks(facts, th(ebc), basis="standalone")
    assert result["_basis"] == "standalone"


def test_superseded_facts_are_ignored(ebc):
    facts = [
        fact("revenue_from_operations", "FY2025", 9999, flags=["superseded"]),
        fact("revenue_from_operations", "FY2025", 1000),
    ]
    result = ebc.run_checks(facts, th(ebc))
    # only the live (non-superseded) fact should be used for FY2025
    assert result["_periods"] == ["FY2025"]


def test_merge_thresholds_applies_sector_override(ebc):
    thresholds_with_override = dict(ebc.DEFAULT_THRESHOLDS)
    thresholds_with_override["sector_overrides"] = {
        "bfsi": {"eps_growth_min_pct": {"value": 15.0, "status": "DRAFT", "note": "bfsi lower bar"}}
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(thresholds_with_override, f)
        path = f.name
    merged = ebc._merge_thresholds(path, "bfsi")
    assert merged["eps_growth_min_pct"] == 15.0
    merged_no_sector = ebc._merge_thresholds(path, None)
    assert merged_no_sector["eps_growth_min_pct"] == 20.0  # base value unaffected


def test_cli_writes_output_json(ebc, tmp_path):
    facts_file = tmp_path / "financials.json"
    facts_file.write_text(json.dumps({"facts": [
        fact("eps_diluted", "FY2024", 10.0),
        fact("eps_diluted", "FY2025", 13.0),
    ]}), encoding="utf-8")
    out_file = tmp_path / "state" / "eps_bridge_check.json"

    import sys
    argv_backup = sys.argv
    sys.argv = ["eps_bridge_check.py", str(facts_file), "--out", str(out_file)]
    try:
        ebc.main()
    finally:
        sys.argv = argv_backup

    assert out_file.exists()
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["eps_growth_20pct"]["status"] == "PASS"
    assert payload["_basis"] == "consolidated"
