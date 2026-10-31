"""
NXTDeal Hub -- AI-Powered Self-Auditing Code Layer: the real git action.

Sam's binding decision #2 (AskUserQuestion, 2026-07-19): every small-tier
auto-fix, and every medium-tier fix once a human approves it, lands on its
own dedicated git branch with a real commit. NOTHING this system does is
ever auto-merged to main -- a human always reviews and merges via a normal
PR/branch-review workflow. This module is the one place that touches git at
all; every other module in this feature calls into it rather than shelling
out to git directly.

Safety discipline, all real and enforced, not just described:
  - Refuses to run at all if the working tree is not clean (uncommitted
    changes present) -- an auto-fix must never risk mixing itself into a
    human's own in-progress, uncommitted work.
  - Always creates the fix branch off the CURRENT branch's HEAD (never
    force-checks-out main first, never assumes what branch is "the right"
    base -- whatever the repo is sitting on when a scan runs).
  - Always returns the repo to the exact branch it started on afterward,
    success or failure, so a human's own checked-out branch is never left
    swapped out from under them.
  - Every git subprocess call has its exit code checked; a non-zero exit at
    any step aborts the whole action and reports a real, specific error --
    never silently continues.
"""

import re
import subprocess

from hub_core.code_auditor_rules import repo_root


class GitActionError(Exception):
    pass


def _run(args, cwd):
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitActionError(
            f"git {' '.join(args)} failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _current_branch(cwd):
    return _run(["rev-parse", "--abbrev-ref", "HEAD"], cwd)


def _working_tree_clean(cwd):
    status = _run(["status", "--porcelain"], cwd)
    return status == ""


def _slugify(text, max_len=40):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "fix"


def create_fix_branch_and_commit(finding_id, rule_key, file_path, new_content, commit_message):
    """Real, minimal git action: checkout a new branch off the current
    HEAD, write new_content to file_path, commit it, then return to the
    original branch. Returns (branch_name, commit_sha, error) -- error is
    None on success.

    file_path is repo-relative (e.g. "backend/core/some_module.py"). Only
    a single file per call, by design -- every fix this system applies is
    narrow enough to be one file, matching the "small, mechanically safe"
    bar the small tier itself already requires (see code_auditor.py)."""

    cwd = repo_root()

    try:
        original_branch = _current_branch(cwd)
    except GitActionError as exc:
        return None, None, str(exc)

    if not _working_tree_clean(cwd):
        return None, None, (
            "Working tree has uncommitted changes -- refusing to create an "
            "auto-fix branch. Commit or stash your own changes first, then "
            "re-run this action."
        )

    branch_name = f"code-auditor/{finding_id.lower()}-{_slugify(rule_key)}"

    try:
        _run(["checkout", "-b", branch_name], cwd)
    except GitActionError as exc:
        return None, None, str(exc)

    try:
        full_path_parts = file_path.replace("\\", "/").split("/")
        import os
        full_path = os.path.join(cwd, *full_path_parts)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        _run(["add", "--", file_path], cwd)
        _run(["commit", "-m", commit_message], cwd)
        commit_sha = _run(["rev-parse", "HEAD"], cwd)

    except (GitActionError, OSError) as exc:
        # Best-effort cleanup: return to the original branch even on
        # failure, so a broken fix attempt never leaves the repo stuck on
        # a half-finished branch.
        try:
            _run(["checkout", original_branch], cwd)
        except GitActionError:
            pass
        return None, None, str(exc)

    try:
        _run(["checkout", original_branch], cwd)
    except GitActionError as exc:
        # The commit itself succeeded (branch_name/commit_sha are real) --
        # only the "return to original branch" step failed. Report both:
        # the fix is real and safe (it's on its own branch, not main), but
        # a human needs to know the working tree may still be on the new
        # branch.
        return branch_name, commit_sha, (
            f"Fix committed successfully to {branch_name} ({commit_sha[:8]}), "
            f"but failed to check the repo back out to {original_branch}: {exc}. "
            f"The repo may currently be sitting on {branch_name} -- verify "
            f"before doing anything else in this working directory."
        )

    return branch_name, commit_sha, None
