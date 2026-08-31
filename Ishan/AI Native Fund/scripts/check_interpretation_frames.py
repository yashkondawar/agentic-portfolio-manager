"""Check the fund's governed interpretation vocabulary against the ER
subsystem's (one-way).

Usage:
    .venv\\Scripts\\python scripts\\check_interpretation_frames.py [--check]

This is a CHECK, not a generator, and the asymmetry is deliberate. The 32
tier-2 playbooks in ``research/equity_researcher/config/sector_registry.yaml``
are upstream-owned — the ER subsystem authors them and the fund vendors them
(see docs/SYSTEM_MAP.md). Generating them from the fund would invert that
ownership; letting them drift from the fund's governed vocabulary would mean
an agent could return a conditioning variable the fund's contracts reject.
So the fund declares the vocabulary in ``registry/rules/interpretation_frames.yaml``
and this script asserts the upstream file stays inside it.

What it asserts:

  V1  every token in the ER registry's ``interpretation_vocabulary
      .conditioning_variables`` is in the fund's ``conditioning_variables``
  V2  every conditioner actually USED by an ER family or playbook is in the
      fund's vocabulary (V1 checks the declared list; a frame can cite a
      token the list forgot)
  V3  ``ConditioningVariable`` in src/afund/agents/contracts.py is exactly the
      fund vocabulary — the Literal is what validates agent output, so a
      registry token missing from it is a token an agent cannot legally return
  V4  ``DiscriminatorType`` in contracts.py is exactly the fund's
      ``discriminator_types``
  V5  the fund's 8 ``family_frames`` mirror the ER registry's ``families.*``
      frames key for key (both files carry them; unchecked duplication is
      how the two tiers end up contradicting each other)
  V6  every multiple token the fund names is in the ER registry's
      ``interpretation_vocabulary.multiples``
  V7  every frame and vocabulary entry is ``status: DRAFT`` — nothing here is
      back-tested (CLAUDE.md hard rule)

Exits 0 when clean, 1 on any failure. ``--check`` is accepted for symmetry
with the two generators (gen_sector_packs.py, gen_eps_thresholds.py) and is
a no-op: this script never writes anything.
"""
from __future__ import annotations

import argparse
import sys
from typing import get_args

# Import path setup mirrors the other scripts/: run from the repo root with
# the venv python and src/ is already on sys.path via the editable install.
from afund.agents.contracts import ConditioningVariable, DiscriminatorType
from afund.research import interpretation as interp

FRAME_KEYS = ("primary_multiple", "secondary_multiples", "multiple_conditioners")

_errors: list[str] = []
_notes: list[str] = []


def err(code: str, msg: str) -> None:
    _errors.append(f"[{code}] {msg}")


def _frame_of(block: dict) -> dict:
    return {k: block[k] for k in FRAME_KEYS if k in block}


def check() -> int:
    fund = interp.load_fund_frames()
    er = interp.load_er_registry()

    fund_vocab = set((fund.get("conditioning_variables") or {}).keys())
    fund_dtypes = set((fund.get("discriminator_types") or {}).keys())
    fund_families = fund.get("family_frames") or {}

    if not fund_vocab:
        err("V0", "registry/rules/interpretation_frames.yaml declares no "
                  "conditioning_variables — the governed tier is empty")
        return _report()

    if not er:
        _notes.append(
            "ER subsystem not present (research/equity_researcher/config/"
            "sector_registry.yaml absent) — V1/V2/V5/V6 skipped; the fund-side "
            "checks below still ran."
        )

    er_vocab = set(
        (er.get("interpretation_vocabulary") or {}).get("conditioning_variables") or []
    )
    er_multiples = set((er.get("interpretation_vocabulary") or {}).get("multiples") or [])
    er_families = er.get("families") or {}
    er_playbooks = er.get("playbooks") or {}

    # V1 — declared ER vocabulary is a subset of the fund's
    for token in sorted(er_vocab - fund_vocab):
        err("V1", f"ER interpretation_vocabulary declares {token!r}, which is not in "
                  f"registry/rules/interpretation_frames.yaml conditioning_variables")

    # V2 — conditioners actually used by ER frames
    for scope, blocks in (("families", er_families), ("playbooks", er_playbooks)):
        for slug, block in (blocks or {}).items():
            if not isinstance(block, dict):
                continue
            for token in block.get("multiple_conditioners") or []:
                if token not in fund_vocab:
                    err("V2", f"ER {scope}.{slug}.multiple_conditioners cites {token!r}, "
                              f"not in the fund vocabulary")

    # V3/V4 — the pydantic Literals are what actually validate agent output
    contract_vocab = set(get_args(ConditioningVariable))
    if contract_vocab != fund_vocab:
        missing = sorted(fund_vocab - contract_vocab)
        extra = sorted(contract_vocab - fund_vocab)
        err("V3", "ConditioningVariable in src/afund/agents/contracts.py disagrees with "
                  f"the registry rule (missing from the Literal: {missing or 'none'}; "
                  f"in the Literal but not the registry: {extra or 'none'})")
    contract_dtypes = set(get_args(DiscriminatorType))
    if contract_dtypes != fund_dtypes:
        missing = sorted(fund_dtypes - contract_dtypes)
        extra = sorted(contract_dtypes - fund_dtypes)
        err("V4", "DiscriminatorType in src/afund/agents/contracts.py disagrees with the "
                  f"registry rule (missing: {missing or 'none'}; extra: {extra or 'none'})")

    # V5 — the two copies of the 8 family frames must agree
    if er_families:
        for slug in sorted(set(fund_families) | set(er_families)):
            fund_block = fund_families.get(slug)
            er_block = er_families.get(slug)
            if fund_block is None:
                err("V5", f"ER declares family {slug!r} with no matching family_frames "
                          f"entry in the registry rule")
                continue
            if er_block is None:
                err("V5", f"registry rule declares family {slug!r}, absent from the ER "
                          f"registry families")
                continue
            a, b = _frame_of(fund_block), _frame_of(er_block)
            if a != b:
                err("V5", f"family {slug!r} frame differs — registry rule {a} vs ER {b}")

    # V6 — multiple tokens the fund names must exist upstream
    if er_multiples:
        for slug, block in fund_families.items():
            if not isinstance(block, dict):
                continue
            named = [block.get("primary_multiple")] + list(block.get("secondary_multiples") or [])
            for token in named:
                if token and token not in er_multiples:
                    err("V6", f"family_frames.{slug} names multiple {token!r}, not in the ER "
                              f"registry's interpretation_vocabulary.multiples")

    # V7 — everything DRAFT until back-tested
    for section in ("conditioning_variables", "discriminator_types", "family_frames"):
        for slug, block in (fund.get(section) or {}).items():
            if not isinstance(block, dict):
                continue
            if block.get("status") != "DRAFT":
                err("V7", f"{section}.{slug} has status {block.get('status')!r}; every "
                          f"threshold/convention is DRAFT until back-tested (CLAUDE.md)")
    if fund.get("status") != "DRAFT":
        err("V7", "registry/rules/interpretation_frames.yaml top-level status is not DRAFT")

    return _report(
        vocab=len(fund_vocab),
        dtypes=len(fund_dtypes),
        families=len(fund_families),
        playbooks=len(er_playbooks),
    )


def _report(**counts) -> int:
    for note in _notes:
        print(f"note: {note}")
    if _errors:
        for line in _errors:
            print(line)
        print(f"\nFAIL — {len(_errors)} interpretation-frame error(s).")
        return 1
    if counts:
        print(
            f"OK - {counts.get('vocab')} conditioning variables, "
            f"{counts.get('dtypes')} discriminator types, "
            f"{counts.get('families')} family frames mirrored, "
            f"{counts.get('playbooks')} ER playbooks checked. All DRAFT."
        )
    else:
        print("OK.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="No-op; accepted for symmetry with the generators. This script "
             "only ever checks.",
    )
    parser.parse_args()
    return check()


if __name__ == "__main__":
    sys.exit(main())
