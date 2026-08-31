"""Phase 9 research subsystem bridge.

- ``er_adapter``: file-based bridge to the external equity researcher
  subsystem (``research/equity_researcher/``) — kickoff + output ingestion.
- ``sector_assembler``: builds the sector-level research packet consumed by
  the in-house ``sector_researcher`` agent.
- ``sensitivity``: pure EPS x PE scenario-grid math used by the ``buy_side``
  agent's output (Python computes the grid; the agent only supplies inputs
  and narrative reasoning).
"""
