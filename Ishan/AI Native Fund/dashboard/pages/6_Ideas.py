"""Ideas — click-gated generation. Nothing LLM fires from this app: both
buttons subprocess the deterministic legs (cycle assessment / 4-gate funnel
/ packet-prep) via `afund.orchestrator.run --job ...` and stream the log
live. Every `agent:<role>` step in those pipelines only builds a packet and
writes a PREPARED agent_runs row — it never calls an LLM — so the log
naturally contains one "READY: invoke Claude Code agent ..." line per
agent step; each is rendered below as an info card with the exact command
to complete it in a separate Claude Code session.

Below the generation controls: a side-by-side idea/synthesis/critique
viewer reading already-INGESTED (COMPLETED) outputs from data/packets/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402

st.set_page_config(page_title="Ideas — AI-Native Fund", layout="wide")

conn = shared.get_conn()

st.title("Ideas")
st.caption(
    "Click-gated generation: buttons run only the deterministic legs (cycle assessment / funnel / "
    "packet-prep). Nothing LLM ever fires from this app — every agent step below stops at a "
    "PREPARED packet + printed instruction for a separate Claude Code session."
)

READY_RE = re.compile(r"^READY: invoke Claude Code agent '([^']+)' with packet file (.+?); (.+)$")


def _render_log_and_ready_cards(job: str, extra_args: dict | None = None) -> None:
    log_lines: list[str] = []
    ready_cards: list[tuple[str, str, str]] = []
    with st.status(f"Running {job}...", expanded=True) as status:
        log_box = st.empty()

        def _sink(line: str) -> None:
            log_lines.append(line)
            log_box.code("\n".join(log_lines[-300:]), language="text")
            m = READY_RE.match(line.strip())
            if m:
                ready_cards.append((m.group(1), m.group(2), m.group(3)))

        exit_code = shared.run_job_streaming(job, extra_args, line_sink=_sink)
        if exit_code == 0:
            status.update(label=f"{job} finished (deterministic legs only)", state="complete")
        else:
            status.update(label=f"{job} exited with code {exit_code}", state="error")

    if ready_cards:
        st.subheader("LLM steps prepared (nothing fired automatically)")
        for role, packet_path, rest in ready_cards:
            command_match = re.search(r"(\.venv\\Scripts\\python -m afund\.orchestrator\.run --ingest-output \S+ --file <output\.json>)", rest)
            command = command_match.group(1) if command_match else rest
            st.info(
                f"**{role}** — LLM step prepared — packet `{packet_path}`.\n\n"
                f"Run in a Claude Code session: agent `{role}` on that packet, then:\n\n"
                f"`{command}`\n\n"
                "Completes automatically only when the API backend is configured "
                "(config/settings.yaml -> llm.backend)."
            )
    else:
        st.caption("No agent steps were reached in this run (check the log above).")


st.divider()

# ---------------------------------------------------------------------------
# Button 1 — asset-allocation ideas (top-down)
# ---------------------------------------------------------------------------

st.subheader("Asset-allocation ideas (top-down)")
st.caption("Runs weekly_cycle_assessment (cycle engine, all scopes) then weekly_idea_cycle (4-gate funnel + agent chain).")


@st.fragment
def _asset_allocation_block() -> None:
    if st.button("Generate asset-allocation ideas", type="primary"):
        st.markdown("**Step 1/2: weekly_cycle_assessment**")
        _render_log_and_ready_cards("weekly_cycle_assessment")
        st.markdown("**Step 2/2: weekly_idea_cycle**")
        _render_log_and_ready_cards("weekly_idea_cycle")
        # The "Latest ingested outputs" viewer below lives outside this
        # fragment and reads agent_runs/batch state that this run may have
        # changed — a full app rerun (not just this fragment) keeps it honest.
        st.rerun(scope="app")


_asset_allocation_block()

st.divider()

# ---------------------------------------------------------------------------
# Button 2 — stock idea (bottom-up, scoped to one symbol)
# ---------------------------------------------------------------------------

st.subheader("Stock idea (bottom-up)")
st.caption("Runs weekly_idea_cycle scoped to one instrument symbol (funnel still scans the full universe; --symbol narrows the agent packet's instrument focus).")


@st.fragment
def _stock_idea_block() -> None:
    symbol_input = st.text_input("Symbol", placeholder="e.g. TCS").strip().upper()
    if st.button("Generate stock idea"):
        if not symbol_input:
            st.error("Enter a symbol first.")
        elif not shared.instrument_exists(conn, symbol_input):
            st.error(
                f"'{symbol_input}' was not found in instruments (active=1). "
                "Check the spelling, or Positions/Micro KPI Screen pages for known symbols."
            )
        else:
            _render_log_and_ready_cards("weekly_idea_cycle", {"symbol": symbol_input})
            # Same reasoning as _asset_allocation_block: refresh the viewer
            # section below, which lives outside this fragment.
            st.rerun(scope="app")


_stock_idea_block()

st.divider()

# ---------------------------------------------------------------------------
# Side-by-side idea / synthesis / critique viewer (already-ingested outputs)
# ---------------------------------------------------------------------------

st.subheader("Latest ingested outputs")
st.caption(
    "Reads already-COMPLETED (ingested) agent outputs from data/packets/ — this section never triggers "
    "generation itself."
)

batch_id = shared.latest_batch_id_for_trigger(conn, role="idea_gen")
if batch_id:
    st.caption(f"Scoped to the latest idea_gen batch: `{batch_id}`")

idea_out = shared.latest_agent_output(conn, "idea_gen", batch_id=batch_id)
synthesis_out = shared.latest_agent_output(conn, "synthesis", batch_id=batch_id)
critique_out = shared.latest_agent_output(conn, "critique", batch_id=batch_id)

col_idea, col_synth, col_crit = st.columns(3)

with col_idea:
    st.markdown("**Idea generation**")
    if idea_out is None:
        st.info("No ingested idea_gen output yet.")
    else:
        for idea in idea_out.get("ideas", []):
            with st.container(border=True):
                st.markdown(f"**{idea['instrument']}** — {idea['direction']} ({idea['entry_door']})")
                st.caption(f"strategy: {idea['strategy_tag']} · confidence: {idea['confidence']:.2f}")
                st.write(idea["thesis"])
                st.caption(f"Invalidation: {idea['invalidation_condition']}")
        if not idea_out.get("ideas"):
            st.info(idea_out.get("no_ideas_reason") or "No ideas this cycle.")

with col_synth:
    st.markdown("**Synthesis**")
    if synthesis_out is None:
        st.info("No ingested synthesis output yet.")
    else:
        st.markdown(f"**{synthesis_out['instrument']}** — {synthesis_out['confidence_tier']}")
        st.write(synthesis_out["house_view"])
        if synthesis_out.get("supporting_logic"):
            st.markdown("Supporting logic:")
            for point in synthesis_out["supporting_logic"]:
                st.write(f"- {point}")
        if synthesis_out.get("load_bearing_assumptions"):
            st.caption("Load-bearing assumptions: " + "; ".join(synthesis_out["load_bearing_assumptions"]))

with col_crit:
    st.markdown("**Critique**")
    if critique_out is None:
        st.info("No ingested critique output yet.")
    else:
        st.markdown(f"Revised confidence: **{critique_out.get('revised_confidence')}**")
        narrative = critique_out.get("narrative_critique") or {}
        if narrative.get("flaws_found"):
            st.markdown("Flaws found:")
            for f in narrative["flaws_found"]:
                st.write(f"- {f}")
        if narrative.get("strongest_counter_argument"):
            st.caption(f"Strongest counter: {narrative['strongest_counter_argument']}")

        premortem = critique_out.get("premortem")
        if premortem:
            with st.container(border=True):
                st.markdown("**Premortem**")
                st.write(f"Most plausible failure: {premortem.get('most_plausible_failure')}")
                st.caption(f"Probability: {premortem.get('probability_qualitative')}")
                if premortem.get("failure_modes"):
                    for fm in premortem["failure_modes"]:
                        st.write(f"- {fm}")
                if premortem.get("kill_conditions"):
                    st.caption("Kill conditions: " + "; ".join(premortem["kill_conditions"]))
