"""End-to-end assess tests against a seeded temp DB: both tables written,
UNIQUE upsert idempotency, data_pending honesty, regime UNKNOWN while macro
cycles are pending, EVI partial disclosure in the persisted row, and the DXY
anchor MOCKED (the test suite never makes a live yfinance network call)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from afund.cycles import anchors, assess
from afund.cycles.anchors import AnchorSeries
from afund.cycles.framework import load as load_framework

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"

AS_OF = "2026-07-05"

# 42 monthly points, 2023-01 .. 2026-06 — enough history for percentile +
# 3/6/12m RoC on every seeded series.
MONTH_DATES = [
    f"{y}-{m:02d}-15"
    for y in (2023, 2024, 2025, 2026)
    for m in range(1, 13)
    if not (y == 2026 and m > 6)
]


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "afund_cycles_test.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    # NIFTY 50 index_data: PE rising 10 -> 30.5, close rising 100 -> 305,
    # PB rising 2.0 -> 6.1 (pb seeded so the EVI's index_pb component is
    # exercised — anchors.index_pb_percentile needs >=10 in-window points).
    for i, d in enumerate(MONTH_DATES):
        connection.execute(
            "INSERT INTO index_data (index_name, date, close, pe, pb) VALUES (?, ?, ?, ?, ?)",
            ("NIFTY 50", d, 100.0 + 5.0 * i, 10.0 + 0.5 * i, 2.0 + 0.1 * i),
        )

    # GOLDBEES / SILVERBEES ETFs with prices on the same dates (commodity
    # ratio anchors need overlapping dates with NIFTY 50 index_data).
    connection.execute(
        "INSERT INTO instruments (id, symbol, instrument_type) VALUES (101, 'GOLDBEES', 'ETF')"
    )
    connection.execute(
        "INSERT INTO instruments (id, symbol, instrument_type) VALUES (102, 'SILVERBEES', 'ETF')"
    )
    for i, d in enumerate(MONTH_DATES):
        connection.execute(
            "INSERT INTO daily_prices (instrument_id, date, close) VALUES (101, ?, ?)",
            (d, 50.0 + 0.2 * i),
        )
        connection.execute(
            "INSERT INTO daily_prices (instrument_id, date, close) VALUES (102, ?, ?)",
            (d, 75.0 - 0.1 * i),
        )
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture()
def mocked_dxy(monkeypatch):
    """Replace the live-yfinance DXY anchor with a synthetic series. The
    test suite must NEVER hit the network — this fixture also records calls
    so tests can assert the mock (not the real fetch) was used."""
    calls: list[dict] = []

    def fake_global_risk_dollar_anchor(scope="market", as_of=None, years=10):
        calls.append({"scope": scope, "as_of": as_of})
        history = [(d, 95.0 + 0.3 * i) for i, d in enumerate(MONTH_DATES)]
        return AnchorSeries(
            cycle_id="global_risk_appetite_dollar_cycle",
            scope=scope,
            metric_name="dxy",
            as_of_date=as_of or AS_OF,
            current=history[-1][1],
            history=history,
            data_pending=False,
            note="MOCKED dxy series (test fixture, no network)",
        )

    monkeypatch.setattr(anchors, "global_risk_dollar_anchor", fake_global_risk_dollar_anchor)
    return calls


@pytest.fixture(scope="module")
def fw():
    return load_framework()


def test_assess_scope_writes_both_tables(conn, mocked_dxy, fw):
    result = assess.assess_scope(conn, fw, "NIFTY 50", AS_OF)

    rows = conn.execute(
        "SELECT * FROM cycle_assessments WHERE scope = ? AND as_of_date = ?",
        ("NIFTY 50", AS_OF),
    ).fetchall()
    # All 16 catalog cycles get a row — live ones classified, the rest
    # honest data_pending.
    assert len(rows) == 16

    by_cycle = {r["cycle_id"]: r for r in rows}

    # Live cycles classified from seeded data (never fabricated):
    valuation = by_cycle["valuation_cycle"]
    assert valuation["data_pending"] == 0
    assert valuation["percentile"] is not None
    assert valuation["phase_id"] in fw.phase_order()
    assert valuation["directional_lean"] in (-1, 0, 1)
    assert json.loads(valuation["contributing_kpis"]) == ["index_pe"]

    # PE at series max + rising -> 100th percentile euphoria (seeded golden).
    assert valuation["percentile"] == pytest.approx(100.0)
    assert valuation["phase_id"] == "euphoria"

    # Narrative fields stay NULL until the narrative_intensity agent ingests.
    assert valuation["narrative_intensity_score"] is None
    assert valuation["reconciliation_quadrant"] is None

    composite_row = conn.execute(
        "SELECT * FROM composite_decisions WHERE scope = ? AND as_of_date = ?",
        ("NIFTY 50", AS_OF),
    ).fetchone()
    assert composite_row is not None
    assert composite_row["requires_human_review"] == 1
    assert composite_row["framework_version"] == fw.content_version

    assert result["composite"]["recommended_action"] == "data_pending"


def test_upsert_is_idempotent_on_unique_keys(conn, mocked_dxy, fw):
    assess.assess_scope(conn, fw, "NIFTY 50", AS_OF)
    assess.assess_scope(conn, fw, "NIFTY 50", AS_OF)  # re-run same (scope, date)

    n_assess = conn.execute(
        "SELECT COUNT(*) AS c FROM cycle_assessments WHERE scope = ? AND as_of_date = ?",
        ("NIFTY 50", AS_OF),
    ).fetchone()["c"]
    n_composite = conn.execute(
        "SELECT COUNT(*) AS c FROM composite_decisions WHERE scope = ? AND as_of_date = ?",
        ("NIFTY 50", AS_OF),
    ).fetchone()["c"]
    # UNIQUE(cycle_id, scope, as_of_date) / UNIQUE(scope, as_of_date):
    # re-running updates in place, never duplicates.
    assert n_assess == 16
    assert n_composite == 1

    # The conflict path stamps updated_at on the second pass.
    updated = conn.execute(
        "SELECT updated_at FROM cycle_assessments WHERE scope = ? AND as_of_date = ? "
        "AND cycle_id = 'valuation_cycle'",
        ("NIFTY 50", AS_OF),
    ).fetchone()
    assert updated["updated_at"] is not None


def test_data_pending_honesty_credit_cycle(conn, mocked_dxy, fw):
    assess.assess_scope(conn, fw, "NIFTY 50", AS_OF)
    row = conn.execute(
        "SELECT * FROM cycle_assessments WHERE scope = ? AND as_of_date = ? AND cycle_id = ?",
        ("NIFTY 50", AS_OF, "credit_debt_cycle"),
    ).fetchone()
    # No macro_series source exists for the credit cycle: the row must say
    # data_pending with NO percentile/phase — never a fabricated reading.
    assert row["data_pending"] == 1
    assert row["percentile"] is None
    assert row["phase_id"] is None
    assert row["directional_lean"] is None
    missing = json.loads(row["missing_kpis_json"])
    assert missing, "missing_kpis_json must name what's missing, not be empty"


def test_regime_unknown_while_macro_pending(conn, mocked_dxy, fw):
    assess.assess_scope(conn, fw, "NIFTY 50", AS_OF)
    row = conn.execute(
        "SELECT * FROM composite_decisions WHERE scope = ? AND as_of_date = ?",
        ("NIFTY 50", AS_OF),
    ).fetchone()
    # All 4 macro_regime cycles are data_pending -> regime UNKNOWN and the
    # composite score withheld (never guessed); alignment still computes
    # (it needs only per-cycle leans, not a regime).
    assert row["regime_unknown"] == 1
    assert row["regime_cluster"] is None
    assert row["composite_score"] is None
    assert row["alignment_score"] is not None


def test_evi_partial_disclosure_persisted(conn, mocked_dxy, fw):
    assess.assess_scope(conn, fw, "NIFTY 50", AS_OF)
    row = conn.execute(
        "SELECT * FROM composite_decisions WHERE scope = ? AND as_of_date = ?",
        ("NIFTY 50", AS_OF),
    ).fetchone()
    used = json.loads(row["evi_components_used_json"])
    missing = json.loads(row["evi_components_missing_json"])
    # index_pe from the valuation reading; index_pb from the seeded pb
    # column; gsec_yield_x_pe stays missing (no GSEC_10Y in this fixture's
    # macro_series) as does mcap_gdp (no GDP series anywhere yet).
    assert set(used) == {"index_pe", "index_pb"}
    assert set(missing) == {"gsec_yield_x_pe", "mcap_gdp"}
    assert row["evi_value"] is not None


def test_dxy_anchor_is_mocked_not_live(conn, mocked_dxy, fw):
    assess.assess_scope(conn, fw, "NIFTY 50", AS_OF)
    # The fixture's fake was actually called (once, for the one live
    # global_risk_dollar cycle) — proving no live yfinance call happened.
    assert len(mocked_dxy) == 1
    assert mocked_dxy[0]["as_of"] == AS_OF

    row = conn.execute(
        "SELECT * FROM cycle_assessments WHERE scope = ? AND as_of_date = ? AND cycle_id = ?",
        ("NIFTY 50", AS_OF, "global_risk_appetite_dollar_cycle"),
    ).fetchone()
    assert row["data_pending"] == 0
    assert row["note"].startswith("MOCKED")


def test_ingest_narrative_intensity_updates_rows_and_recomputes_composite(conn, mocked_dxy, fw):
    """orchestrator/run.py's _ingest_narrative_intensity: UPDATEs the
    narrative_* columns on the matching cycle_assessments rows (quant
    columns untouched) and recomputes the scope's composite_decisions."""
    from afund.agents.contracts import NarrativeIntensityOutput
    from afund.orchestrator.run import _ingest_narrative_intensity

    assess.assess_scope(conn, fw, "NIFTY 50", AS_OF)

    validated = NarrativeIntensityOutput(
        scope="NIFTY 50",
        as_of_date=AS_OF,
        narrative_intensity_score=-50.0,  # dismissive
        permanence_narratives=[],
        impairment_narratives=["'equities are dead money' framing in 3 of 5 items"],
        divergence_note="price rising while narrative stays dismissive",
        evidence_refs=["news_items.id=1"],
        confidence=0.7,
        injection_flags=[],
    )
    _ingest_narrative_intensity(conn, validated)

    rows = conn.execute(
        "SELECT * FROM cycle_assessments WHERE scope = ? AND as_of_date = ?",
        ("NIFTY 50", AS_OF),
    ).fetchall()
    for row in rows:
        assert row["narrative_intensity_score"] == pytest.approx(-50.0)
        assert "impairment" in row["narrative_summary"]
        if row["data_pending"] == 0 and row["directional_lean"] is not None:
            # Reconciliation quadrant computed per-cycle from its own lean:
            # +1 lean x dismissive -> contrarian sweet spot; -1 lean x
            # dismissive has no verbatim row -> ambiguous fallback.
            if row["directional_lean"] == 1:
                assert row["reconciliation_quadrant"] == "highest_conviction_opportunity"
                flags = json.loads(row["reconciliation_flags_json"])
                assert flags.get("requires_premortem") is True
            else:
                assert row["reconciliation_quadrant"] is not None
        else:
            assert row["reconciliation_quadrant"] is None

    # Quant fields untouched by the ingest.
    valuation = conn.execute(
        "SELECT * FROM cycle_assessments WHERE scope = ? AND as_of_date = ? AND cycle_id = 'valuation_cycle'",
        ("NIFTY 50", AS_OF),
    ).fetchone()
    assert valuation["percentile"] == pytest.approx(100.0)
    assert valuation["phase_id"] == "euphoria"

    # composite_decisions still exactly one row (recomputed, not duplicated).
    n_composite = conn.execute(
        "SELECT COUNT(*) AS c FROM composite_decisions WHERE scope = ? AND as_of_date = ?",
        ("NIFTY 50", AS_OF),
    ).fetchone()["c"]
    assert n_composite == 1
