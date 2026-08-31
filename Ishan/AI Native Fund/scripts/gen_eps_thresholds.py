"""Generate the ER EPS-bridge checker's thresholds file from the registry
(one-way).

Usage:
    .venv\\Scripts\\python scripts\\gen_eps_thresholds.py [--check]

Reads ``registry/rules/eps_bridge.yaml`` (the fund's single source of truth
for EPS-bridge doctrine thresholds) and writes
``research/equity_researcher/config/eps_bridge_thresholds.yaml`` — the file
``research/equity_researcher/tools/eps_bridge_check.py`` auto-discovers at
run time. The output preserves the registry's ``{value, status, note}``
block shape per threshold key, plus the ``sector_overrides`` block, so the
checker's threshold-resolution logic (and any hand-written YAML someone
points ``--thresholds`` at) sees an identical shape either way.

``sector_overrides`` resolves **layered, family then playbook** — see
``eps_bridge_check.py::_override_chain()``. A slug may be one of the fund's 8
family slugs or one of the 32 tier-2 playbook slugs in the ER
``config/sector_registry.yaml``; a playbook slug pulls its family's override in
first. The generator emits that contract as a header comment on the output so
the ER config explains its own resolution order, and renders each override as a
full ``{value, status, note}`` block rather than a one-line mapping, because the
notes carry the derivation and a flow-style scalar makes them unreadable.

Keys prefixed ``_`` in the registry's override blocks (``_kind``, ``_family``,
``_derivation``, ``_not_overridden``) are provenance. They render as comments
and are **never** emitted as YAML keys — ``_merge_thresholds()`` walks every key
in an override block, so a stray ``_derivation`` would land in the merged
threshold dict as if it were a threshold.

Every generated file carries a header marking it GENERATED — do not
hand-edit the output; edit ``registry/rules/eps_bridge.yaml`` and re-run
this script instead.

``--check`` runs the generation in-memory and exits non-zero if the output
file would differ from what's on disk (useful for idempotency checks / CI),
without writing anything.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_RULES_PATH = REPO_ROOT / "registry" / "rules" / "eps_bridge.yaml"
OUTPUT_PATH = (
    REPO_ROOT / "research" / "equity_researcher" / "config" / "eps_bridge_thresholds.yaml"
)

GENERATED_HEADER = (
    "# GENERATED from registry/rules/eps_bridge.yaml by "
    "scripts/gen_eps_thresholds.py — edit the registry source, then "
    "re-run; do not hand-edit."
)

NOTE_WRAP_WIDTH = 78
NOTE_INDENT = "    "


def _load_registry() -> dict:
    return yaml.safe_load(REGISTRY_RULES_PATH.read_text(encoding="utf-8")) or {}


def _format_scalar(value) -> str:
    """Render a threshold value the way PyYAML/the hand-authored source
    files do: floats keep a decimal point, ints/bools/None use their plain
    form."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _render_note(note: str) -> str:
    text = " ".join((note or "").split())
    wrapped = textwrap.fill(
        text,
        width=NOTE_WRAP_WIDTH,
        initial_indent=NOTE_INDENT,
        subsequent_indent=NOTE_INDENT,
    )
    return f"  note: >\n{wrapped}\n"


def _render_threshold_block(key: str, block: dict) -> str:
    lines = [f"{key}:"]
    lines.append(f"  value: {_format_scalar(block.get('value'))}")
    lines.append(f"  status: {block.get('status', 'DRAFT')}")
    text = f"{chr(10).join(lines)}\n" + _render_note(block.get("note", ""))
    return text


OVERRIDE_HEADER = """\
# Per-sector threshold overrides. Resolution is LAYERED, family then playbook:
# tools/eps_bridge_check.py::_override_chain() reads config/sector_registry.yaml,
# and when --sector names a tier-2 playbook it applies that playbook's FAMILY
# override first and the playbook's own override on top. So `--sector
# life_insurance` picks up bfsi's structural NAs and then life_insurance's own.
# A slug that is neither a family nor a playbook resolves to itself and gets no
# family layer. Later layers win key by key; a layer that omits a key inherits it.
#
# `value: null` means the checker reports NA for that rule rather than a number
# — an override says the rung has no referent in this sector, not that its bar
# is different. Everything here is DRAFT until back-tested."""

OVERRIDE_FOOTER = """\
# To add an override: name the slug (family or playbook), cite the registry entry
# or playbook passage it derives from, and prefer `value: null` over inventing a
# sector-specific number. Edit registry/rules/eps_bridge.yaml and re-run
# scripts/gen_eps_thresholds.py; then `python tools/preflight.py`, which checks
# the parse and the slug resolution."""


def _comment(text: str, indent: str) -> list[str]:
    """Render registry provenance (`_`-prefixed keys) as a wrapped comment block.

    The provenance never becomes a YAML key in the output: _override_chain()
    would otherwise treat `_derivation` as a threshold and set it on the merged
    dict. The registry keeps the derivation; the generated file carries it as
    commentary, which is where a reader of the ER config wants it anyway."""
    body = " ".join((text or "").split())
    if not body:
        return []
    return textwrap.fill(
        body,
        width=NOTE_WRAP_WIDTH,
        initial_indent=f"{indent}# ",
        subsequent_indent=f"{indent}# ",
    ).splitlines()


def _render_sector_override_block(key: str, block: dict, indent: str) -> list[str]:
    """One threshold override, in the same {value, status, note} shape as a
    top-level threshold so the checker sees an identical structure either way."""
    if not isinstance(block, dict) or "value" not in block:
        return [f"{indent}{key}: {_format_scalar(block)}"]
    lines = [
        f"{indent}{key}:",
        f"{indent}  value: {_format_scalar(block.get('value'))}",
        f"{indent}  status: {block.get('status', 'DRAFT')}",
    ]
    note = " ".join((block.get("note") or "").split())
    if note:
        lines.append(f"{indent}  note: >")
        lines.extend(
            textwrap.fill(
                note,
                width=NOTE_WRAP_WIDTH,
                initial_indent=f"{indent}    ",
                subsequent_indent=f"{indent}    ",
            ).splitlines()
        )
    return lines


def _render_sector_overrides(sector_overrides: dict) -> str:
    if not sector_overrides:
        return (
            "sector_overrides: {}\n"
            "# Per-sector threshold overrides — see registry/rules/eps_bridge.yaml\n"
            "# for the override syntax (partial {value, status, note} blocks keyed\n"
            "# by sector slug and threshold key). Populate the registry source, then\n"
            "# re-run this generator; do not hand-edit here.\n"
        )

    lines = [OVERRIDE_HEADER, "", "sector_overrides:"]
    for sector, overrides in sector_overrides.items():
        overrides = overrides or {}
        lines.append("")
        lines.append(f"  {sector}:")
        kind = overrides.get("_kind")
        family = overrides.get("_family")
        if kind:
            label = f"Layer: {kind}"
            if family:
                label += f", resolved after `{family}`"
            lines.extend(_comment(label + ".", "    "))
        lines.extend(_comment(overrides.get("_derivation", ""), "    "))
        for key, val in overrides.items():
            if key.startswith("_"):
                continue
            lines.extend(_render_sector_override_block(key, val, "    "))
        not_overridden = overrides.get("_not_overridden")
        if not_overridden:
            lines.extend(_comment(not_overridden, "    "))
    lines.append("")
    lines.append(OVERRIDE_FOOTER)
    return "\n".join(lines) + "\n"


def render() -> str:
    data = _load_registry()
    sector_overrides = data.get("sector_overrides") or {}
    threshold_keys = [k for k in data.keys() if k != "sector_overrides"]

    parts: list[str] = [GENERATED_HEADER, ""]
    for key in threshold_keys:
        parts.append(_render_threshold_block(key, data[key] or {}))
    parts.append(_render_sector_overrides(sector_overrides))

    text = "\n".join(parts)
    # collapse accidental multiple-blank-lines, ensure single trailing newline
    import re

    text = re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Don't write the file; exit 1 if the generated content would differ.",
    )
    args = parser.parse_args()

    rendered = render()
    existing = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else None

    if args.check:
        if existing == rendered:
            print("eps_bridge_thresholds.yaml up to date.")
            return 0
        print("OUT OF DATE: research/equity_researcher/config/eps_bridge_thresholds.yaml")
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    changed = existing != rendered
    print(f"Generated {OUTPUT_PATH} ({'changed' if changed else 'unchanged'}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
