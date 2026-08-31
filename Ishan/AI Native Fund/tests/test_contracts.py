"""Offline tests for afund.agents.contracts — pydantic output contracts."""
from __future__ import annotations

import json

import pytest

from afund.agents.contracts import (
    ContractViolation,
    ROLE_MODELS,
    validate_output,
)

# One known-valid payload per registered role.
VALID_PAYLOADS: dict[str, dict] = {
    "news_processor": {
        "items": [
            {
                "news_item_id": 1,
                "event_scope": "MICRO",
                "tag": "TCS",
                "impact": "POSITIVE",
                "description": "TCS wins $1bn multi-year deal with a European bank.",
                "event_date": "2026-07-01",
                "source": "Economic Times",
                "url": "http://example.com/tcs-deal",
            }
        ],
        "injection_flags": [],
    },
    "idea_gen": {
        "ideas": [
            {
                "instrument": "INFY",
                "direction": "LONG",
                "entry_door": "TOP_DOWN",
                "strategy_tag": "cycle_contrarian",
                "thesis": "IT services demand upcycle with attractive valuations.",
                "invalidation_condition": "Revenue growth below 5% YoY for two consecutive quarters.",
                "confidence": 0.6,
            }
        ],
        "no_ideas_reason": None,
    },
    "synthesis": {
        "instrument": "INFY",
        "house_view": "Constructive on IT services into FY27.",
        "supporting_logic": ["Deal wins accelerating", "Rupee tailwind for margins"],
        "confidence_tier": "MEDIUM",
        "load_bearing_assumptions": ["US BFSI tech budgets recover in H2"],
    },
    "critique": {
        "instrument": "INFY",
        "narrative_critique": {
            "flaws_found": [],
            "strongest_counter_argument": "GenAI-driven deflation may permanently compress IT services pricing.",
            "circular_reasoning_flags": [],
        },
        "quant_model_critique": {
            "flaws_found": [],
            "most_aggressive_input": "FY27 margin assumption of 24%",
            "sensitivity_note": "Thesis breaks below 21% margin.",
        },
        "competing_thesis": "IT demand is structurally, not cyclically, slowing.",
        "revised_confidence": "UNCHANGED",
    },
    "risk_mgmt": {
        "instrument": "INFY",
        "verdict": "CLEARED",
        "conditions": [],
        "limit_checks": [
            {"rule": "max_single_position_pct", "status": "PASS", "detail": "proposed 4% < limit 10%"}
        ],
        "look_through_note": None,
    },
    "allocator": {
        "instrument": "INFY",
        "vehicle": "DIRECT_STOCK",
        "proposed_weight_pct": 4.0,
        "sizing_rationale": "High conviction, direct stock edge over sector ETF.",
        "cash_after_pct": 12.5,
    },
    "fund_manager": {
        "instrument": "INFY",
        "action": "NEW",
        "strategy_tag": "cycle_contrarian",
        "conviction": 0.7,
        "thesis_restatement": "Cyclical demand recovery underpriced at current multiple.",
        "strongest_counter_and_response": "GenAI deflation risk; countered by deal-win data showing net expansion.",
        "invalidation_condition": "Two consecutive quarters of sub-5% YoY revenue growth.",
        "evidence_chain": ["Q1 FY27 results", "NASSCOM sector guidance"],
        "size_or_weight_pct": 4.0,
        "calibration_note": None,
    },
    "equity_researcher": {
        "status": "NOT_IMPLEMENTED",
        "ticker": None,
        "as_of_date": None,
    },
    "sector_researcher": {
        "sector": "it_technology",
        "as_of_date": "2026-07-05",
        "cycle_phase": "expansion",
        "cycle_confidence": 0.6,
        "competitive_landscape": "Tier-1 IT services facing margin pressure from GenAI-led deal deflation.",
        "value_chain_note": "Offshore delivery cost advantage narrowing as onshore/nearshore mix rises.",
        "comparison_table": [
            {"symbol": "INFY", "pe": 24.5, "roce": 28.0, "roe": 26.0, "ret_1y": 12.0, "cycle_phase": "expansion", "note": None},
        ],
        "top_picks": ["INFY"],
        "avoid_list": [],
        "key_risks": ["US recession denting discretionary tech spend."],
        "sources": ["NASSCOM strategic review 2026"],
    },
    "buy_side": {
        "ticker": "INFY",
        "recommendation": "ACCUMULATE",
        "conviction": 0.65,
        "rerating_narrative": "Margin trough behind us; AI services mix shift supports multiple re-rating.",
        "catalysts": ["FY27 margin guidance beat", "Large deal TCV acceleration"],
        "eps_scenarios": [80.0, 85.0, 90.0, 95.0, 100.0],
        "pe_scenarios": [20.0, 22.0, 24.0, 26.0, 28.0],
        "scenario_reasoning": "Base case assumes mid-single-digit constant-currency growth with stable margins.",
        "base_target_price": 2160.0,
        "invalidation_condition": "Two consecutive quarters of sub-5% YoY constant-currency revenue growth.",
    },
    "macro_digest": {
        "publisher": "DSP_NETRA",
        "period": "2026-06",
        "macro_notes": [
            {
                "tag_value": "india_liquidity",
                "content": "Banking system liquidity surplus at 2.1 lakh crore, highest in 14 months.",
                "source_ref": "newsletter:DSP_NETRA:2026-06",
            }
        ],
        "regime_read": None,
        "injection_flags": [],
    },
    "meta_research": {
        "period": "2026-Q2",
        "patterns_found": ["Fund Manager conviction consistently 0.1 above realized hit rate."],
        "proposals": [
            {
                "target_file": ".claude/agents/fund_manager.md",
                "change_type": "PROMPT_EDIT",
                "rationale": "Overconfidence pattern vs calibration set.",
                "proposed_diff": "- conviction freely\n+ conviction anchored to calibration table",
            }
        ],
        "calibration_summary": "Brier 0.21 over 14 decisions.",
    },
    "narrative_intensity": {
        "scope": "NIFTY 50",
        "as_of_date": "2026-07-05",
        "narrative_intensity_score": 35.0,
        "permanence_narratives": ["'India's decade' framing recurring across sell-side notes."],
        "impairment_narratives": [],
        "divergence_note": "Price rising faster than earnings narrative justifies.",
        "evidence_refs": ["news_items.id=12", "knowledge_base.id=3"],
        "confidence": 0.6,
        "injection_flags": [],
    },
}


def test_valid_payload_parses_for_every_registered_role():
    assert set(VALID_PAYLOADS) == set(ROLE_MODELS)
    for role, payload in VALID_PAYLOADS.items():
        model = validate_output(role, payload)
        assert isinstance(model, ROLE_MODELS[role])


def test_valid_payload_parses_from_json_string():
    for role, payload in VALID_PAYLOADS.items():
        model = validate_output(role, json.dumps(payload))
        assert isinstance(model, ROLE_MODELS[role])


def test_candidate_idea_missing_invalidation_condition_rejected():
    payload = json.loads(json.dumps(VALID_PAYLOADS["idea_gen"]))
    del payload["ideas"][0]["invalidation_condition"]
    with pytest.raises(ContractViolation):
        validate_output("idea_gen", payload)


def test_candidate_idea_short_invalidation_condition_rejected():
    payload = json.loads(json.dumps(VALID_PAYLOADS["idea_gen"]))
    payload["ideas"][0]["invalidation_condition"] = "n/a"  # < 10 chars
    with pytest.raises(ContractViolation):
        validate_output("idea_gen", payload)


def test_fund_manager_missing_invalidation_condition_rejected():
    payload = json.loads(json.dumps(VALID_PAYLOADS["fund_manager"]))
    del payload["invalidation_condition"]
    with pytest.raises(ContractViolation):
        validate_output("fund_manager", payload)


def test_fund_manager_new_without_size_rejected():
    payload = json.loads(json.dumps(VALID_PAYLOADS["fund_manager"]))
    payload["size_or_weight_pct"] = None
    assert payload["action"] == "NEW"
    with pytest.raises(ContractViolation):
        validate_output("fund_manager", payload)


def test_fund_manager_hold_without_size_accepted():
    payload = json.loads(json.dumps(VALID_PAYLOADS["fund_manager"]))
    payload["action"] = "HOLD"
    payload["size_or_weight_pct"] = None
    model = validate_output("fund_manager", payload)
    assert model.action == "HOLD"


def test_fenced_json_block_accepted():
    payload = VALID_PAYLOADS["synthesis"]
    fenced = "```json\n" + json.dumps(payload, indent=2) + "\n```"
    model = validate_output("synthesis", fenced)
    assert model.instrument == "INFY"


def test_bare_fenced_block_accepted():
    payload = VALID_PAYLOADS["risk_mgmt"]
    fenced = "```\n" + json.dumps(payload) + "\n```"
    model = validate_output("risk_mgmt", fenced)
    assert model.verdict == "CLEARED"


def test_junk_string_raises_contract_violation():
    with pytest.raises(ContractViolation):
        validate_output("critique", "this is not json at all {{{")


def test_wrong_shape_dict_raises_contract_violation():
    with pytest.raises(ContractViolation):
        validate_output("allocator", {"totally": "wrong"})


def test_unknown_role_raises_contract_violation():
    with pytest.raises(ContractViolation):
        validate_output("not_a_role", VALID_PAYLOADS["synthesis"])


def test_news_processor_event_scope_na_rejected():
    payload = json.loads(json.dumps(VALID_PAYLOADS["news_processor"]))
    payload["items"][0]["event_scope"] = "NA"
    with pytest.raises(ContractViolation):
        validate_output("news_processor", payload)


def test_macro_digest_requires_at_least_one_note():
    payload = json.loads(json.dumps(VALID_PAYLOADS["macro_digest"]))
    payload["macro_notes"] = []
    with pytest.raises(ContractViolation):
        validate_output("macro_digest", payload)


def test_buy_side_eps_scenarios_must_be_ascending():
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["eps_scenarios"] = [100.0, 95.0, 90.0, 85.0, 80.0]  # descending
    with pytest.raises(ContractViolation):
        validate_output("buy_side", payload)


def test_buy_side_pe_scenarios_must_be_ascending():
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["pe_scenarios"] = [28.0, 26.0, 24.0, 22.0, 20.0]  # descending
    with pytest.raises(ContractViolation):
        validate_output("buy_side", payload)


def test_buy_side_requires_exactly_five_scenarios():
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["eps_scenarios"] = [80.0, 85.0, 90.0]  # only 3
    with pytest.raises(ContractViolation):
        validate_output("buy_side", payload)


def test_buy_side_short_invalidation_condition_rejected():
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["invalidation_condition"] = "n/a"  # < 10 chars
    with pytest.raises(ContractViolation):
        validate_output("buy_side", payload)


def test_buy_side_eps_bridge_summary_defaults_to_none():
    # Phase 11 -- EPS-bridge doctrine: optional field, must not be required
    # for older/base payloads that predate it.
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    assert "eps_bridge_summary" not in payload
    model = validate_output("buy_side", payload)
    assert model.eps_bridge_summary is None


def test_buy_side_eps_bridge_summary_accepts_valid_verdicts():
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["eps_bridge_summary"] = {
        "eps_growth_20pct": "PASS",
        "dilution_consecutive": "FAIL",
        "interest_coverage": "NA",
    }
    model = validate_output("buy_side", payload)
    assert model.eps_bridge_summary["eps_growth_20pct"] == "PASS"
    assert model.eps_bridge_summary["dilution_consecutive"] == "FAIL"


def test_buy_side_eps_bridge_summary_rejects_invalid_verdict():
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["eps_bridge_summary"] = {"eps_growth_20pct": "MAYBE"}  # not PASS/FAIL/NA
    with pytest.raises(ContractViolation):
        validate_output("buy_side", payload)


def test_critique_premortem_defaults_to_none():
    payload = json.loads(json.dumps(VALID_PAYLOADS["critique"]))
    assert "premortem" not in payload
    model = validate_output("critique", payload)
    assert model.premortem is None


def test_critique_premortem_round_trips():
    payload = json.loads(json.dumps(VALID_PAYLOADS["critique"]))
    payload["premortem"] = {
        "failure_modes": ["Mean reversion never plays out due to a structural break in the sector."],
        "most_plausible_failure": "GenAI-led pricing deflation is structural, not cyclical, so the historical valuation band no longer applies.",
        "probability_qualitative": "MEDIUM",
        "kill_conditions": ["Realized pricing per deal down >10% YoY for two consecutive quarters."],
    }
    model = validate_output("critique", payload)
    assert model.premortem is not None
    assert model.premortem.probability_qualitative == "MEDIUM"
    assert model.premortem.most_plausible_failure.startswith("GenAI-led")


def test_critique_premortem_requires_most_plausible_failure_min_length():
    payload = json.loads(json.dumps(VALID_PAYLOADS["critique"]))
    payload["premortem"] = {
        "failure_modes": [],
        "most_plausible_failure": "n/a",  # < 10 chars
        "probability_qualitative": "LOW",
        "kill_conditions": [],
    }
    with pytest.raises(ContractViolation):
        validate_output("critique", payload)


def test_critique_premortem_rejects_bad_probability_enum():
    payload = json.loads(json.dumps(VALID_PAYLOADS["critique"]))
    payload["premortem"] = {
        "failure_modes": [],
        "most_plausible_failure": "Structural pricing deflation not captured by historical valuation bands.",
        "probability_qualitative": "VERY_HIGH",  # not a valid enum value
        "kill_conditions": [],
    }
    with pytest.raises(ContractViolation):
        validate_output("critique", payload)


def test_fund_manager_checklist_status_defaults_to_none():
    payload = json.loads(json.dumps(VALID_PAYLOADS["fund_manager"]))
    assert "checklist_status" not in payload
    model = validate_output("fund_manager", payload)
    assert model.checklist_status is None


def test_fund_manager_checklist_status_round_trips():
    payload = json.loads(json.dumps(VALID_PAYLOADS["fund_manager"]))
    payload["checklist_status"] = {
        "lookback_structural_break": "PASS",
        "currency_domestic_consistency": "NA",
        "implementation_tax_layer": "FAIL",
    }
    model = validate_output("fund_manager", payload)
    assert model.checklist_status["implementation_tax_layer"] == "FAIL"
    assert model.checklist_status["currency_domestic_consistency"] == "NA"


def test_fund_manager_checklist_status_rejects_bad_enum_value():
    payload = json.loads(json.dumps(VALID_PAYLOADS["fund_manager"]))
    payload["checklist_status"] = {"lookback_structural_break": "MAYBE"}
    with pytest.raises(ContractViolation):
        validate_output("fund_manager", payload)


# --- facts/interpretation layer ---------------------------------------------
#
# The whole layer is additive and optional: every payload above predates it and
# must keep validating. What is NOT optional is the closed vocabulary and the
# resolved/discriminator rule -- a free-text conditioning variable, or a
# divergence declared settled with nothing settling it, are exactly the two
# moves these models exist to reject.

_READING_A = {
    "verdict": "expensive",
    "conditioning_variable": "own_history_anchor",
    "reasoning": "30.2x against a 10-year median of 18x.",
}
_READING_B = {
    "verdict": "cheap",
    "conditioning_variable": "growth_rate",
    "reasoning": "PEG of 1.0 on 30% forward EPS growth.",
}


def _divergence(**overrides) -> dict:
    case = {
        "fact": "Trailing P/E is 30.2 on FY25 consolidated EPS.",
        "fact_source": "FY25 annual report p. 84",
        "readings": [dict(_READING_A), dict(_READING_B)],
        "our_reading": "Cheap only if the 30% growth holds five years.",
        "materiality": "high",
    }
    case.update(overrides)
    return case


def test_buy_side_interpretation_fields_default_to_empty():
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    assert "interpretation_ledger" not in payload
    model = validate_output("buy_side", payload)
    assert model.interpretation_ledger == []
    assert model.multiple_conditioner is None
    assert model.sector_playbook is None
    # None, not {} -- an empty dict would read as "audited, nothing found".
    assert model.opinion_audit is None


def test_buy_side_multiple_conditioner_accepts_vocabulary_token():
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["sector_playbook"] = "it_services"
    payload["primary_multiple"] = "pe_forward"
    payload["multiple_conditioner"] = "growth_durability"
    model = validate_output("buy_side", payload)
    assert model.multiple_conditioner == "growth_durability"


def test_buy_side_multiple_conditioner_rejects_free_text():
    # "because the story is good" is the failure mode a str field would accept.
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["multiple_conditioner"] = "market_is_wrong"
    with pytest.raises(ContractViolation):
        validate_output("buy_side", payload)


def test_buy_side_ledger_entry_round_trips():
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["interpretation_ledger"] = [
        _divergence(
            discriminator_type="historical_distribution",
            discriminator="Only 3 of 22 Indian IT companies sustained 20%+ cc growth for 5 years (FY05-FY25).",
            resolved=True,
        )
    ]
    model = validate_output("buy_side", payload)
    entry = model.interpretation_ledger[0]
    assert entry.resolved is True
    assert entry.discriminator_type == "historical_distribution"
    assert [r.conditioning_variable for r in entry.readings] == [
        "own_history_anchor",
        "growth_rate",
    ]


def test_divergence_case_needs_at_least_two_readings():
    # One reading is not a divergence -- it is the bull case with no opponent
    # on record (ER audit check 17).
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["interpretation_ledger"] = [_divergence(readings=[dict(_READING_A)])]
    with pytest.raises(ContractViolation):
        validate_output("buy_side", payload)


def test_divergence_resolved_without_discriminator_rejected():
    # Check 18: claiming a divergence is settled while naming nothing that
    # settles it is resolution by assertion.
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["interpretation_ledger"] = [_divergence(resolved=True)]
    with pytest.raises(ContractViolation):
        validate_output("buy_side", payload)


def test_divergence_resolved_with_none_available_rejected():
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["interpretation_ledger"] = [
        _divergence(resolved=True, discriminator_type="none_available", discriminator="nothing found")
    ]
    with pytest.raises(ContractViolation):
        validate_output("buy_side", payload)


def test_divergence_resolved_with_blank_evidence_rejected():
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["interpretation_ledger"] = [
        _divergence(resolved=True, discriminator_type="peer_distribution", discriminator="   ")
    ]
    with pytest.raises(ContractViolation):
        validate_output("buy_side", payload)


def test_divergence_unresolved_none_available_is_legal():
    # The honest outcome, and the one the no-fabrication rule requires when the
    # evidence is not there: recorded, not deleted, not quietly resolved.
    payload = json.loads(json.dumps(VALID_PAYLOADS["buy_side"]))
    payload["interpretation_ledger"] = [
        _divergence(discriminator_type="none_available", resolved=False)
    ]
    model = validate_output("buy_side", payload)
    assert model.interpretation_ledger[0].resolved is False


def test_sector_note_interpretation_fields_default_to_empty():
    payload = json.loads(json.dumps(VALID_PAYLOADS["sector_researcher"]))
    model = validate_output("sector_researcher", payload)
    assert model.facts == []
    assert model.interpretations == []
    assert model.divergence_cases == []
    # The narrative fields keep their role -- the split is additive.
    assert model.competitive_landscape


def test_sector_note_facts_and_interpretations_round_trip():
    payload = json.loads(json.dumps(VALID_PAYLOADS["sector_researcher"]))
    payload["facts"] = [
        {
            "claim": "Sector median trailing P/E is 26.4x.",
            "source": "derived_ratios, packet comparison_table",
            "as_of": "2026-07-05",
        }
    ]
    payload["interpretations"] = [dict(_READING_A)]
    payload["divergence_cases"] = [_divergence()]
    model = validate_output("sector_researcher", payload)
    assert model.facts[0].source
    assert model.interpretations[0].conditioning_variable == "own_history_anchor"
    assert model.divergence_cases[0].materiality == "high"


def test_fact_claim_requires_a_source():
    payload = json.loads(json.dumps(VALID_PAYLOADS["sector_researcher"]))
    payload["facts"] = [{"claim": "Sector median trailing P/E is 26.4x."}]
    with pytest.raises(ContractViolation):
        validate_output("sector_researcher", payload)


def test_synthesis_interpretation_fields_default_to_empty():
    payload = json.loads(json.dumps(VALID_PAYLOADS["synthesis"]))
    model = validate_output("synthesis", payload)
    assert model.facts_relied_on == []
    assert model.interpretations == []
    assert model.supporting_logic  # untouched by the split


def test_critique_opinion_audit_and_divergences_round_trip():
    payload = json.loads(json.dumps(VALID_PAYLOADS["critique"]))
    payload["opinion_audit"] = {"4": "PASS", "16": "FAIL", "17": "NA"}
    payload["banned_reasoning_hits"] = ["deserves a higher multiple because peers trade higher"]
    payload["unresolved_divergences"] = [
        {
            "fact": "Trailing P/E is 30.2 on FY25 consolidated EPS.",
            "our_reading": "Cheap only if the 30% growth holds five years.",
            "why_unresolved": "No published base rate for 5-year growth persistence in this sub-sector.",
            "what_would_settle_it": "FY05-FY25 persistence distribution across the 22-name peer set.",
            "materiality": "high",
        }
    ]
    model = validate_output("critique", payload)
    assert model.opinion_audit["16"] == "FAIL"
    assert model.banned_reasoning_hits
    assert model.unresolved_divergences[0].materiality == "high"


def test_critique_opinion_audit_defaults_to_none_not_empty_dict():
    payload = json.loads(json.dumps(VALID_PAYLOADS["critique"]))
    model = validate_output("critique", payload)
    assert model.opinion_audit is None
    assert model.banned_reasoning_hits == []
    assert model.unresolved_divergences == []


def test_critique_opinion_audit_rejects_bad_verdict():
    payload = json.loads(json.dumps(VALID_PAYLOADS["critique"]))
    payload["opinion_audit"] = {"16": "PROBABLY"}
    with pytest.raises(ContractViolation):
        validate_output("critique", payload)


def test_equity_research_placeholder_role_no_longer_registered():
    # Phase 9 retired the placeholder role entirely (both the .claude/agents/
    # file and any contract) in favor of the real equity_researcher bridge
    # (afund.research.er_adapter) -> a stale caller trying the old role name
    # must fail loudly, not silently resolve to something else.
    assert "equity_research_placeholder" not in ROLE_MODELS
    with pytest.raises(ContractViolation):
        validate_output("equity_research_placeholder", VALID_PAYLOADS["equity_researcher"])
