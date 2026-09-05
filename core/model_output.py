"""Recover a JSON object from model prose.

Every backend is a different model, and models differ in how much scaffolding
they wrap around a JSON answer even when told to return JSON only: some emit a
bare object, some fence it, some add a closing pleasantry, some nest a detail
object inside. The strategies that ask for JSON treat a parse failure as "the
LLM is unavailable" and fall back to deterministic scoring -- so sloppy
extraction does not raise, it silently changes the recommendation. That makes
this a correctness boundary between backends, not a formatting nicety.

The previous approach -- ``split("```")[1]`` plus a ``\\{[^{}]*"key"[^{}]*\\}``
regex -- failed on two shapes that Claude and Gemini produce routinely:
trailing prose after a valid object, and prose before an object containing a
nested object. Brace matching handles both, and every shape in between.
"""

from __future__ import annotations

import json
from typing import Any


def _strip_fences(text: str) -> str:
    """Return the contents of the first ``` fence, or the text unchanged."""
    if "```" not in text:
        return text
    parts = text.split("```")
    if len(parts) < 3:
        return text
    body = parts[1]
    # ```json / ```JSON / ```  -- drop the language tag, keep the payload.
    newline = body.find("\n")
    if newline != -1 and body[:newline].strip().isalpha():
        body = body[newline + 1 :]
    return body


def _balanced_objects(text: str):
    """Yield every top-level ``{...}`` span, respecting strings and escapes.

    A plain brace counter is not enough: a brace inside a string literal (such
    as ``"reasoning": "ROE {high}"``) would unbalance it.
    """
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth:
                depth -= 1
                if depth == 0 and start != -1:
                    yield text[start : index + 1]
                    start = -1


def extract_json_object(text: str, *, must_contain: str | None = None) -> dict[str, Any]:
    """Parse the first JSON object in ``text``, ignoring prose around it.

    ``must_contain`` names a key the caller requires, which disambiguates when
    a model emits several objects (for example an example object followed by
    the real answer). Raises ``ValueError`` when nothing usable is found, so
    callers keep their existing "LLM failed, use the fallback" behaviour.
    """
    candidates = list(_balanced_objects(_strip_fences(text)))
    if not candidates:
        candidates = list(_balanced_objects(text))

    fallback: dict[str, Any] | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        if must_contain is None or must_contain in parsed:
            return parsed
        if fallback is None:
            fallback = parsed

    if fallback is not None:
        return fallback
    raise ValueError(f"no JSON object found in model output: {text[:200]!r}")


__all__ = ["extract_json_object"]
