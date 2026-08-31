"""Interpretation frames — which multiple a sector is judged on, and which
conditioning variable makes that judgement defensible.

Two tiers feed this module, and neither is allowed to hardcode the other:

  registry/rules/interpretation_frames.yaml    fund, GOVERNED
      the closed conditioning-variable vocabulary, the discriminator types,
      and default frames for the fund's 8 sector slugs (= tier-1 families).

  research/equity_researcher/config/sector_registry.yaml    ER, UPSTREAM
      the same 8 families plus the 32 tier-2 playbooks. The fund consumes
      the playbook layer; it does not author it.

``resolve_frame()`` is the only place the two are combined, and it combines
them the way ``eps_bridge_check.py::_override_chain()`` already resolves
per-sector thresholds: **family first, playbook on top, key by key**. A
playbook that omits ``secondary_multiples`` inherits its family's rather than
silently getting an empty list — the ER registry does exactly that for several
playbooks (``it_services`` declares ``secondary_multiples: []`` meaning "none
beyond the family's", not "the family's do not apply").

Why the frame travels with the packet at all: the fund's buy-side and sector
agents receive numbers, not the ER run's reasoning. Without the frame, an
agent handed a P/E of 30 has no governed way to say whether 30 is expensive —
it would reach for tone. With it, the packet carries the sector's default
multiple and the conditioners that the sector's convention says decide the
question, so the agent's verdict has to name one of them.

Read-only, no LLM, no database. ``scripts/check_interpretation_frames.py``
uses the same loaders so the check and the runtime never disagree about what
the files say.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from afund.config import REPO_ROOT

FUND_FRAMES_PATH = REPO_ROOT / "registry" / "rules" / "interpretation_frames.yaml"
ER_SECTOR_REGISTRY_PATH = (
    REPO_ROOT / "research" / "equity_researcher" / "config" / "sector_registry.yaml"
)

# The prose tier. A pointer, never inlined — packets carry the path
# (CLAUDE.md token-frugality rule).
FACTS_VS_INTERPRETATION_REF = "methodology/facts_vs_interpretation.md"

_FRAME_KEYS = ("primary_multiple", "secondary_multiples", "multiple_conditioners")


@lru_cache(maxsize=1)
def load_fund_frames() -> dict:
    """registry/rules/interpretation_frames.yaml, parsed. Fails loudly if it
    is missing — it is governed fund content, not an optional add-on."""
    return yaml.safe_load(FUND_FRAMES_PATH.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def load_er_registry() -> dict:
    """research/equity_researcher/config/sector_registry.yaml, parsed.

    Degrades to ``{}`` when the ER subsystem isn't synced into this checkout
    (it is a vendored subsystem, and the fund's own pipelines must not hard-
    fail on its absence). Every consumer below treats an empty registry as
    "no playbook layer available", which resolves to the family frame alone.
    """
    if not ER_SECTOR_REGISTRY_PATH.exists():
        return {}
    try:
        return yaml.safe_load(ER_SECTOR_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def conditioning_vocabulary() -> set[str]:
    """The closed token set. `ConditioningVariable` in
    src/afund/agents/contracts.py must stay identical to this —
    scripts/check_interpretation_frames.py --check asserts it."""
    return set((load_fund_frames().get("conditioning_variables") or {}).keys())


def discriminator_vocabulary() -> set[str]:
    return set((load_fund_frames().get("discriminator_types") or {}).keys())


def family_frame(family: str | None) -> dict | None:
    """The fund's governed tier-1 frame for one of the 8 sector slugs."""
    if not family:
        return None
    block = (load_fund_frames().get("family_frames") or {}).get(family)
    return dict(block) if isinstance(block, dict) else None


def playbook_family(playbook: str | None) -> str | None:
    """Family slug for an ER tier-2 playbook, or None if the playbook is
    unknown here (an ER run newer than this checkout's vendored registry)."""
    if not playbook:
        return None
    block = (load_er_registry().get("playbooks") or {}).get(playbook)
    return block.get("family") if isinstance(block, dict) else None


def _er_frame(scope: str, slug: str | None) -> dict | None:
    if not slug:
        return None
    block = (load_er_registry().get(scope) or {}).get(slug)
    if not isinstance(block, dict):
        return None
    frame = {k: block[k] for k in _FRAME_KEYS if k in block}
    return frame or None


def resolve_frame(
    *, family: str | None = None, playbook: str | None = None
) -> dict | None:
    """Layered interpretation frame: family first, playbook on top.

    Pass a playbook and the family is derived from the ER registry, so a
    caller holding only ``sector_playbook`` (which is all the valuation
    handoff carries) gets both layers. Pass a family alone — what the
    sector-level packet has — and the tier-1 frame comes back on its own.

    Returns None when neither layer resolves, which is the honest answer for
    a sector slug nobody has authored a frame for yet; callers put None in
    the packet rather than inventing a default multiple.

    ``resolved_from`` records the layers that actually contributed, in order,
    so a reader of the packet can tell a family default from a playbook
    convention without re-reading either file.
    """
    resolved_family = family or playbook_family(playbook)

    layers: list[tuple[str, dict]] = []
    fund_layer = family_frame(resolved_family)
    if fund_layer:
        layers.append((f"registry:family:{resolved_family}", fund_layer))
    er_family_layer = _er_frame("families", resolved_family)
    if er_family_layer:
        layers.append((f"er:family:{resolved_family}", er_family_layer))
    er_playbook_layer = _er_frame("playbooks", playbook)
    if er_playbook_layer:
        layers.append((f"er:playbook:{playbook}", er_playbook_layer))

    if not layers:
        return None

    frame: dict = {}
    resolved_from: list[str] = []
    for label, layer in layers:
        contributed = False
        for key in _FRAME_KEYS:
            if key not in layer:
                continue
            value = layer[key]
            # An empty secondary_multiples list on a playbook means "nothing
            # beyond the family's", not "discard the family's" — the ER
            # registry uses [] that way. A non-empty value always wins.
            if value in (None, [], ""):
                continue
            if frame.get(key) != value:
                contributed = True
            frame[key] = value
        if contributed or not resolved_from:
            resolved_from.append(label)

    if not frame:
        return None

    frame["family"] = resolved_family
    frame["playbook"] = playbook
    frame["resolved_from"] = resolved_from
    frame["status"] = "DRAFT"
    frame["vocabulary_source"] = "registry/rules/interpretation_frames.yaml"
    return frame
