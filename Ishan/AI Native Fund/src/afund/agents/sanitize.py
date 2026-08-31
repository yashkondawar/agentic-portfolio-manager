"""Untrusted-text sanitization for anything that lands in an agent packet
but did not originate from our own deterministic code — news headlines,
newsletter PDF text, or any other free-text external content.

This is a defense-in-depth layer, not a substitute for the per-agent
SECURITY preamble (registry/prompts/security_preamble.md) that instructs
agents to treat all packet data as untrusted. sanitize_untrusted() runs
BEFORE that text ever reaches a packet: it neutralizes obvious
prompt-injection patterns, strips control characters, truncates to a
budget, and wraps the result in an explicit <untrusted_data> tag so an
agent (and a human reading the packet) can see exactly where the trust
boundary is.

Nothing here calls an LLM; this is pure text processing.
"""
from __future__ import annotations

import re
from typing import Any

NEUTRALIZED_MARKER = "[NEUTRALIZED:injection-pattern]"

# Each pattern is matched case-insensitively. Patterns are intentionally
# broad (better to over-neutralize benign text than miss an injection).
#
# "act_as" is a narrower exception to that "broad by default" rule: a bare
# `\bact\s+as\s+` (the original pattern) false-positived on legitimate
# financial prose like "RBI Dividends act as ATM" (Aequitas 2026-06
# newsletter) — "act as" alone is common, non-adversarial English. Only flag
# it when it looks like an instruction-style role override: "act as" followed
# by a role/authority noun (system, admin, developer, assistant, AI/model,
# unrestricted/jailbroken/DAN, ...), or "act as" preceded by an imperative
# ("you must/should/will act as ..."), which is adversarial regardless of
# what role noun (if any) follows.
_ACT_AS_ROLE_WORDS = (
    r"(?:system|admin|administrator|root|developer|assistant|ai|model|"
    r"unrestricted|jailbroken|dan)"
)
_ACT_AS_PATTERN = (
    r"\b(?:you\s+(?:must|should|will)\s+act\s+as\b"
    r"|act\s+as\s+(?:a\s+|an\s+|the\s+)?" + _ACT_AS_ROLE_WORDS + r"\b)"
)

_INJECTION_PATTERNS: list[tuple[str, str]] = [
    ("ignore_previous_instructions", r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions"),
    ("disregard_instructions", r"disregard\s+.{0,30}instructions"),
    ("system_prompt", r"system\s+prompt"),
    ("you_are_now", r"you\s+are\s+now\b"),
    ("act_as", _ACT_AS_PATTERN),
    ("reveal_secrets", r"(reveal|print|show)\s+.{0,40}(env|environment|secret|api.?key|token|password)"),
    ("role_marker_tag", r"</?(system|assistant|user)>"),
    ("role_marker_inst", r"\[/?INST\]"),
    ("role_marker_line", r"(?m)^\s*assistant\s*:"),
]

_COMPILED_PATTERNS = [(name, re.compile(pattern, re.IGNORECASE)) for name, pattern in _INJECTION_PATTERNS]

# Control characters other than \t (0x09), \n (0x0A), \r (0x0D).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# 3+ consecutive newlines (2+ blank lines) collapsed to a single blank line.
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")

TRUNCATION_SUFFIX = "...[truncated]"


def _neutralize_injection_patterns(text: str) -> tuple[str, list[str]]:
    flags: list[str] = []

    def _replace(match: re.Match, name: str) -> str:
        flags.append(f"{name}: {match.group(0)!r}")
        return NEUTRALIZED_MARKER

    for name, compiled in _COMPILED_PATTERNS:
        text = compiled.sub(lambda m, n=name: _replace(m, n), text)

    return text, flags


def _strip_control_chars(text: str) -> str:
    return _CONTROL_CHARS_RE.sub("", text)


def _collapse_blank_lines(text: str) -> str:
    return _EXCESS_BLANK_LINES_RE.sub("\n\n", text)


def sanitize_untrusted(text: str, source_ref: str, max_chars: int = 4000) -> tuple[str, list[str]]:
    """Sanitize untrusted free text before it enters an agent packet.

    Steps, in order:
      (a) neutralize known prompt-injection patterns (case-insensitive),
          replacing each match with NEUTRALIZED_MARKER and recording a flag;
      (b) strip control characters and collapse 2+ blank lines to 1;
      (c) truncate to max_chars, appending "...[truncated]" if truncated;
      (d) wrap the result in <untrusted_data source="{source_ref}">...</untrusted_data>.

    Returns (wrapped_text, flags) — flags is empty if nothing was neutralized.
    """
    if text is None:
        text = ""

    neutralized, flags = _neutralize_injection_patterns(text)
    cleaned = _strip_control_chars(neutralized)
    cleaned = _collapse_blank_lines(cleaned)

    if len(cleaned) > max_chars:
        keep = max(max_chars - len(TRUNCATION_SUFFIX), 0)
        cleaned = cleaned[:keep] + TRUNCATION_SUFFIX

    wrapped = f'<untrusted_data source="{source_ref}">{cleaned}</untrusted_data>'
    return wrapped, flags


def embed_untrusted(packet: dict[str, Any], key: str, text: str, source_ref: str, max_chars: int = 4000) -> list[str]:
    """Sanitize `text` and set packet[key] to the wrapped result in place.

    Returns the flags produced (also appended to packet.setdefault('sanitize_flags', [])
    so callers get one place to look for every sanitize flag raised while
    building a packet). This is the single helper any future free-text
    external content path (macro_digest newsletter text, research snippets,
    etc.) should call rather than inlining sanitize_untrusted() calls.
    """
    wrapped, flags = sanitize_untrusted(text, source_ref, max_chars=max_chars)
    packet[key] = wrapped
    if flags:
        packet.setdefault("sanitize_flags", []).extend(flags)
    return flags
