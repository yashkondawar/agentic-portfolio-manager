"""Phase 1 data pipelines: pure-Python fetch/parse/upsert jobs.

No LLM calls anywhere in this package. Every pipeline reads its source
URL/config from config/sources.yaml, logs a row to job_runs, and is
idempotent (INSERT OR IGNORE / upsert on UNIQUE keys).
"""
