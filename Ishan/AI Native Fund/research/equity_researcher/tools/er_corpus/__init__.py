"""ER initiation-note corpus tooling (deterministic, zero LLM tokens).

See tools/er_corpus/README.md. Entry points:
    fetch_corpus.py   download + markitdown-convert + manifest
    discover.py       enumerate candidate PDF URLs from crawlable hosts
    profile_notes.py  regex-profile the converted corpus (structure statistics)
"""
