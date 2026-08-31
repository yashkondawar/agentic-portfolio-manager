"""Phase 1 derivations: pure-Python calculations over already-ingested data.

No LLM calls, no network access — everything here reads from SQLite (via
afund.db.connection.get_conn()) and either returns plain dicts/values or
writes back into derived_ratios. No new tables; nothing here talks to
external sources (that's data/'s job).
"""
