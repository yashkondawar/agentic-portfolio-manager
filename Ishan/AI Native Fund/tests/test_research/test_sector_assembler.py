"""Offline tests for afund.research.sector_assembler.build_sector_packet.

All synthetic data seeded into a temp SQLite DB built from schema.sql —
mirrors tests/test_screener.py's fixture pattern. No network, no LLM calls.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

from afund.orchestrator import context
from afund.research import sector_assembler

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"

AS_OF = dt.date(2026, 7, 5)


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "afund_test.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def _redirect_packets_dir(tmp_path, monkeypatch):
    packets_dir = tmp_path / "packets"
    monkeypatch.setattr(context, "PACKETS_DIR", packets_dir)
    monkeypatch.setattr(sector_assembler, "PACKETS_DIR", packets_dir)
    yield packets_dir


def _insert_instrument(conn, instrument_id, symbol, sector, instrument_type="STOCK"):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, sector, active) VALUES (?, ?, ?, ?, 1)",
        (instrument_id, symbol, instrument_type, sector),
    )


def _insert_flat_series(conn, instrument_id, days=800, price=100.0):
    d = AS_OF - dt.timedelta(days=days)
    rows = []
    while d <= AS_OF:
        rows.append((instrument_id, d.isoformat(), price))
        d += dt.timedelta(days=1)
    conn.executemany("INSERT INTO daily_prices (instrument_id, date, close) VALUES (?, ?, ?)", rows)


@pytest.fixture()
def seeded_conn(conn):
    # Two IT instruments, one BFSI instrument -- so the sector filter has
    # something real to exclude.
    _insert_instrument(conn, 1, "INFY", "Information Technology")
    _insert_instrument(conn, 2, "TCS", "Information Technology")
    _insert_instrument(conn, 3, "HDFCBANK", "Financial Services")
    _insert_flat_series(conn, 1)
    _insert_flat_series(conn, 2)
    _insert_flat_series(conn, 3)

    conn.execute(
        """
        INSERT INTO derived_ratios (instrument_id, as_of_date, cadence, metric_name, metric_value)
        VALUES (1, ?, 'quarterly', 'stock_p_e', 24.5)
        """,
        (AS_OF.isoformat(),),
    )
    conn.execute(
        """
        INSERT INTO derived_ratios (instrument_id, as_of_date, cadence, metric_name, metric_value)
        VALUES (2, ?, 'quarterly', 'stock_p_e', 28.0)
        """,
        (AS_OF.isoformat(),),
    )
    conn.execute(
        """
        INSERT INTO derived_ratios (instrument_id, as_of_date, cadence, metric_name, metric_value)
        VALUES (3, ?, 'quarterly', 'stock_p_e', 18.0)
        """,
        (AS_OF.isoformat(),),
    )
    conn.commit()
    return conn


def test_build_sector_packet_basic_shape(seeded_conn):
    result = sector_assembler.build_sector_packet(seeded_conn, "it_technology", batch_id="test_batch")
    assert Path(result["path"]).exists()
    packet = result["packet"]
    assert packet["role"] == "sector_researcher"
    assert packet["sector"] == "it_technology"
    assert "cycle_context" in packet
    assert "comparison_table" in packet
    assert "sector_financials" in packet
    assert "registry_slice" in packet
    assert result["approx_tokens"] > 0


def test_build_sector_packet_filters_by_sector(seeded_conn):
    result = sector_assembler.build_sector_packet(seeded_conn, "it_technology", batch_id="test_batch")
    packet = result["packet"]
    financial_symbols = {row["symbol"] for row in packet["sector_financials"]}
    assert "INFY" in financial_symbols
    assert "TCS" in financial_symbols
    assert "HDFCBANK" not in financial_symbols


def test_build_sector_packet_bfsi_excludes_it(seeded_conn):
    result = sector_assembler.build_sector_packet(seeded_conn, "bfsi", batch_id="test_batch")
    packet = result["packet"]
    financial_symbols = {row["symbol"] for row in packet["sector_financials"]}
    assert financial_symbols == {"HDFCBANK"}


def test_build_sector_packet_registry_slice_matches_sector(seeded_conn):
    result = sector_assembler.build_sector_packet(seeded_conn, "it_technology", batch_id="test_batch")
    kpi_set = result["packet"]["registry_slice"]["kpi_set"]
    assert kpi_set is not None


def test_build_sector_packet_unknown_sector_falls_back_to_generic_kpis(seeded_conn):
    # No instruments map to this made-up slug, but the registry_slice should
    # still resolve via the "generic" fallback rather than erroring.
    result = sector_assembler.build_sector_packet(seeded_conn, "not_a_real_sector", batch_id="test_batch")
    kpi_set = result["packet"]["registry_slice"]["kpi_set"]
    assert kpi_set is not None
    assert result["packet"]["sector_financials"] == []
    assert result["packet"]["comparison_table"] == []


def test_build_sector_packet_respects_budget(seeded_conn, monkeypatch):
    # 1200, not the 800 this asserted before the interpretation layer landed:
    # the packet's irreducible floor rose by the ~360 chars of
    # interpretation_frame, which is deliberately outside the truncation
    # order (see build_sector_packet's last-rungs comment). Everything
    # droppable still drops.
    from afund.config import load_settings as _orig_load_settings

    def _tiny_budget_settings():
        settings = dict(_orig_load_settings())
        settings["packet_budgets"] = dict(settings.get("packet_budgets", {}))
        settings["packet_budgets"]["sector_researcher"] = 1200
        return settings

    monkeypatch.setattr(sector_assembler, "load_settings", _tiny_budget_settings)

    result = sector_assembler.build_sector_packet(seeded_conn, "it_technology", batch_id="test_batch")
    assert result["approx_tokens"] <= 1200 // 4 + 1
    assert result["packet"]["truncation_notes"]


def test_interpretation_frame_survives_budget_pressure(seeded_conn, monkeypatch):
    """The lens outlives the data it is a lens on. A comparison table with no
    frame is how "P/E 30 looks high" gets written without naming a
    conditioning variable — so the frame is dropped last, i.e. never."""
    from afund.config import load_settings as _orig_load_settings

    def _absurd_budget_settings():
        settings = dict(_orig_load_settings())
        settings["packet_budgets"] = dict(settings.get("packet_budgets", {}))
        settings["packet_budgets"]["sector_researcher"] = 200
        return settings

    monkeypatch.setattr(sector_assembler, "load_settings", _absurd_budget_settings)

    packet = sector_assembler.build_sector_packet(
        seeded_conn, "it_technology", batch_id="test_batch"
    )["packet"]

    assert packet["divergence_reference"] is None
    frame = packet["interpretation_frame"]
    assert frame["primary_multiple"] == "pe_forward"
    assert "growth_durability" in frame["multiple_conditioners"]
    assert frame["status"] == "DRAFT"


def test_sector_packet_frame_is_family_level_and_points_at_playbooks(seeded_conn):
    """The fund's 8 slugs are the tier-1 families; the 32 tier-2 playbooks stay
    owned by ER triage. This packet has no ticker, so it must not pick one."""
    packet = sector_assembler.build_sector_packet(
        seeded_conn, "bfsi", batch_id="test_batch"
    )["packet"]

    frame = packet["interpretation_frame"]
    assert frame["family"] == "bfsi"
    assert frame["playbook"] is None
    assert frame["resolved_from"] == ["registry:family:bfsi"]
    # P/B, not P/E — the whole point of a per-family frame.
    assert frame["primary_multiple"] == "p_b"

    ref = packet["divergence_reference"]
    if ref is None:  # ER subsystem not synced into this checkout
        pytest.skip("research/equity_researcher not present")
    assert ref["methodology"]["path"].endswith("facts_vs_interpretation.md")
    slugs = {c["playbook"] for c in ref["sector_playbooks"]}
    assert "banks_private" in slugs
    # Never a playbook from another family.
    assert "it_services" not in slugs


def test_build_sector_packet_persists_to_batch_dir(seeded_conn, tmp_path):
    result = sector_assembler.build_sector_packet(seeded_conn, "it_technology", batch_id="my_batch")
    out_path = Path(result["path"])
    assert out_path.parent.name == "my_batch"
    assert out_path.name == "01_sector_researcher.json"
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["sector"] == "it_technology"


def test_build_sector_packet_json_serializable(seeded_conn):
    result = sector_assembler.build_sector_packet(seeded_conn, "it_technology", batch_id="test_batch")
    json.dumps(result["packet"])  # must not raise
