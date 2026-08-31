"""Decisions & Theses — ported from dashboard/app.py, plus checklist_status
render (from fund_manager_rec_json's FundManagerOutput.checklist_status:
PASS/FAIL/NA per mechanical + judgment item). PENDING decisions are
highlighted with the exact CLI command to record a human decision."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402

st.set_page_config(page_title="Decisions & Theses — AI-Native Fund", layout="wide")

conn = shared.get_conn()

st.title("Decisions & Theses")

st.subheader("Decision Log")
decisions_df = shared.df_from_query(
    conn,
    "SELECT id, decision_date, instrument_id, sector, action, strategy_tag, human_decision, human_notes, "
    "fund_manager_rec_json FROM decision_log ORDER BY created_at DESC, id DESC",
)

if decisions_df.empty:
    st.info("No decisions recorded yet.")
else:
    pending = decisions_df[decisions_df["human_decision"] == "PENDING"]
    if not pending.empty:
        st.warning(f"{len(pending)} decision(s) pending human review.")
        st.dataframe(pending.drop(columns=["fund_manager_rec_json"]), use_container_width=True)
        st.caption(
            "Record a decision via: `.venv\\Scripts\\python -m afund.orchestrator.run "
            "--record-human-decision <decision_id> --decision APPROVE|REJECT|MODIFY [--notes \"...\"]`"
        )

    st.dataframe(decisions_df.drop(columns=["fund_manager_rec_json"]), use_container_width=True)

    st.divider()
    st.subheader("Checklist detail")
    label_map = {
        row.id: f"#{row.id} · {row.action} · {row.sector or row.instrument_id} · {row.human_decision}"
        for row in decisions_df.itertuples()
    }
    selected_id = st.selectbox("Select a decision", list(label_map), format_func=lambda i: label_map[i])
    selected_row = decisions_df[decisions_df["id"] == selected_id].iloc[0]

    if selected_row["human_decision"] == "PENDING":
        st.warning(
            f"PENDING — record via: `.venv\\Scripts\\python -m afund.orchestrator.run "
            f"--record-human-decision {selected_id} --decision APPROVE|REJECT|MODIFY [--notes \"...\"]`"
        )

    rec_json = selected_row["fund_manager_rec_json"]
    if not rec_json:
        st.info("No fund_manager_rec_json recorded for this decision.")
    else:
        try:
            rec = json.loads(rec_json)
        except ValueError:
            rec = None
        if rec is None:
            st.warning("fund_manager_rec_json could not be parsed as JSON.")
        else:
            checklist = rec.get("checklist_status")
            if not checklist:
                st.caption("No checklist_status present on this recommendation.")
            else:
                st.markdown("**Checklist (mechanical + judgment)**")
                icon = {"PASS": "✅", "FAIL": "❌", "NA": "➖"}
                rows = [
                    {"item": item, "status": f"{icon.get(status, '?')} {status}"}
                    for item, status in checklist.items()
                ]
                st.dataframe(rows, use_container_width=True)
                fails = [item for item, status in checklist.items() if status == "FAIL"]
                if fails:
                    st.error(f"FAIL on: {', '.join(fails)}")

st.divider()

st.subheader("Thesis Tracker")
thesis_df = shared.df_from_query(
    conn,
    "SELECT id, instrument_id, decision_id, thesis_text, invalidation_condition, status, opened_date, last_checked "
    "FROM thesis_tracker ORDER BY opened_date DESC, id DESC",
)
if thesis_df.empty:
    st.info("No theses tracked yet.")
else:
    st.dataframe(thesis_df, use_container_width=True)
