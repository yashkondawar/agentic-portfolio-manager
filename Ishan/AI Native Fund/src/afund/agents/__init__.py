"""Phase 4 — LLM agent layer plumbing.

This package holds only deterministic scaffolding: pydantic output
contracts (contracts.py), untrusted-text sanitization (sanitize.py), and
the backend-invocation abstraction (runner.py). Nothing here calls an LLM
directly except runner.invoke_api, which is gated behind the "api" backend
and an installed `anthropic` package — the default "claude_code" backend
never makes a network call from this package.
"""
