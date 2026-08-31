"""Stage a meta-research proposal onto a review branch — NEVER onto main.

Meta-research (see .claude/agents/meta_research.md) PROPOSES registry/prompt
changes; it never applies them. This script is the one deterministic path
that turns a proposal JSON artifact into an actual (staged, unmerged) git
branch a human reviews with `git diff` before merging by hand. It is the
ONLY place in this repo that ever writes to files under registry/ or
.claude/agents/ on behalf of an agent's output — and even then, only on a
side branch, never on the branch that was checked out when the script ran.

Usage:
    .venv\\Scripts\\python scripts\\apply_meta_proposal.py data\\proposals\\<file>.json [--branch-name X]

What it does:
    1. Refuses to run if registry/ or .claude/agents/ has uncommitted changes
       (dirty-tree guard — staging on top of unrelated dirty state would make
       the review branch's diff misleading).
    2. Creates (or resets, if --branch-name already exists locally) a branch
       named meta/<period> (or --branch-name) off the current HEAD.
    3. For each proposal: tries `git apply` on proposed_diff as a unified
       diff; if that fails (not valid diff text — proposed_diff is
       LLM-authored free text, not guaranteed to be a clean unified diff),
       falls back to writing `<target_file>.proposed` alongside the real
       target_file with the raw proposed_diff content, so nothing at
       target_file itself is ever silently overwritten by a malformed diff.
    4. Commits the staged changes on that branch only.
    5. Switches back to the original branch (main, typically) — its working
       tree is left byte-for-byte as it was before this script ran.
    6. Prints `git diff <original>..<branch> --stat` and review instructions.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

GUARDED_ROOTS = ("registry", ".claude/agents")


class ApplyProposalError(RuntimeError):
    """Raised for any refusal/failure condition; main() prints it and exits 1."""


def _run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if check and result.returncode != 0:
        raise ApplyProposalError(
            f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result


def _current_branch() -> str:
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout.strip()


def _assert_clean_guarded_roots() -> None:
    """Refuse to run if registry/ or .claude/agents/ has uncommitted changes
    on the CURRENT branch — staging a proposal on top of unrelated dirty
    state there would make the resulting review branch's diff misleading
    (mixing the human's in-progress edits with the agent's proposal)."""
    dirty_lines = []
    for root in GUARDED_ROOTS:
        result = _run_git(["status", "--porcelain", "--", root])
        if result.stdout.strip():
            dirty_lines.append(result.stdout)
    if dirty_lines:
        raise ApplyProposalError(
            "Refusing to run: uncommitted changes exist in registry/ or .claude/agents/ on the "
            "current branch. Commit or stash them first, then re-run.\n" + "\n".join(dirty_lines)
        )


def _load_proposal(json_path: Path) -> dict:
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ApplyProposalError(f"Cannot read proposal file {json_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ApplyProposalError(f"Proposal file {json_path} is not valid JSON: {exc}") from exc


def _target_file_allowed(target_file: str) -> bool:
    normalized = target_file.replace("\\", "/").lstrip("/")
    if ".." in Path(normalized).parts:
        return False
    return normalized.startswith("registry/") or normalized.startswith(".claude/agents/")


def _apply_one_proposal(proposal: dict, branch_dir: Path) -> str:
    """Apply a single proposal dict's proposed_diff. Returns a one-line
    outcome description for the summary. Tries `git apply` first (a real
    unified diff); on any failure, falls back to writing
    `<target_file>.proposed` next to the target with the raw text so the
    real target_file is never silently clobbered by unparseable diff text."""
    target_file = proposal["target_file"]
    proposed_diff = proposal.get("proposed_diff") or ""

    if not _target_file_allowed(target_file):
        raise ApplyProposalError(
            f"Proposal target_file {target_file!r} is outside registry/ or .claude/agents/ — refusing "
            f"to apply (this script only ever stages changes within those two roots)."
        )

    diff_file = branch_dir / "_meta_proposal.patch"
    diff_file.write_text(proposed_diff, encoding="utf-8")
    try:
        result = subprocess.run(
            ["git", "apply", "--check", str(diff_file)],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        if result.returncode == 0:
            subprocess.run(
                ["git", "apply", str(diff_file)],
                cwd=str(REPO_ROOT), capture_output=True, text=True, check=True,
            )
            return f"{target_file}: applied as unified diff"
    finally:
        diff_file.unlink(missing_ok=True)

    # Fallback: not a clean unified diff (LLM-authored free text is common
    # here) — write the proposed content alongside the target, untouched.
    target_path = REPO_ROOT / target_file
    proposed_path = Path(str(target_path) + ".proposed")
    proposed_path.parent.mkdir(parents=True, exist_ok=True)
    proposed_path.write_text(proposed_diff, encoding="utf-8")
    return f"{target_file}: not a clean unified diff -> wrote {proposed_path.relative_to(REPO_ROOT)}"


def apply_proposal(json_path: Path, branch_name: str | None = None) -> dict:
    """Full staging flow. Returns a summary dict:
    {"branch": str, "original_branch": str, "outcomes": [str, ...],
     "proposal_count": int}."""
    _assert_clean_guarded_roots()

    data = _load_proposal(json_path)
    period = data.get("period", "unknown_period")
    proposals = data.get("proposals", [])
    branch_name = branch_name or f"meta/{period}"

    original_branch = _current_branch()

    # Validate every target_file BEFORE creating/touching any branch, so a
    # bad proposal never leaves a half-created branch behind.
    for proposal in proposals:
        target_file = proposal.get("target_file", "")
        if not _target_file_allowed(target_file):
            raise ApplyProposalError(
                f"Proposal target_file {target_file!r} is outside registry/ or .claude/agents/ — "
                f"refusing to create branch {branch_name!r}."
            )

    existing = _run_git(["branch", "--list", branch_name])
    if existing.stdout.strip():
        _run_git(["branch", "-D", branch_name])

    _run_git(["checkout", "-b", branch_name])

    outcomes: list[str] = []
    try:
        if not proposals:
            outcomes.append("(no proposals in this artifact — branch created with no changes)")
        else:
            for proposal in proposals:
                outcomes.append(_apply_one_proposal(proposal, REPO_ROOT))

            _run_git(["add", "registry", ".claude/agents"])
            commit_message = f"meta-research proposal {period} — HUMAN REVIEW REQUIRED"
            _run_git(["commit", "-m", commit_message, "--allow-empty"])
    finally:
        _run_git(["checkout", original_branch])

    return {
        "branch": branch_name,
        "original_branch": original_branch,
        "outcomes": outcomes,
        "proposal_count": len(proposals),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Stage a meta-research proposal onto a review branch")
    parser.add_argument("proposal_json", help="Path to a data/proposals/<period>_meta_proposal.json file")
    parser.add_argument("--branch-name", default=None, help="Override the default meta/<period> branch name")
    args = parser.parse_args(argv)

    json_path = Path(args.proposal_json)
    if not json_path.is_absolute():
        json_path = Path.cwd() / json_path

    try:
        summary = apply_proposal(json_path, branch_name=args.branch_name)
    except ApplyProposalError as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)

    print(f"Staged {summary['proposal_count']} proposal(s) on branch '{summary['branch']}':")
    for outcome in summary["outcomes"]:
        print(f"  - {outcome}")

    stat = subprocess.run(
        ["git", "diff", f"{summary['original_branch']}..{summary['branch']}", "--stat"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    print(stat.stdout)
    print(f"Back on branch '{summary['original_branch']}' — working tree untouched.")
    print(f"Review with: git diff {summary['original_branch']}..{summary['branch']}")
    print(f"Merge only if approved: git checkout {summary['original_branch']} && git merge {summary['branch']}")


if __name__ == "__main__":
    main()
