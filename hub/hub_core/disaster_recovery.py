"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 2 of 4:
Disaster Recovery.

This module deliberately does NOT build a one-click automated restore
action. A wrong restore is genuinely destructive (it overwrites a live
tenant's real graph.json), and backend/core/data_backup.py's own
restore_backup() is ADMIN-only for exactly that reason -- making a
cross-process, Hub-triggered version of that action one click away, with no
additional safeguard, was judged too risky to build without Sam directly
scoping what confirmation/guardrails it should have. Documentation over
automation for this one, on purpose.

What this module DOES do: document the REAL recovery method this very
session actually used, twice, to recover from two real accidental data-loss
incidents this session's own work (see CLAUDE.md's NXTDeal Hub section,
"Data-loss incident during Dealer Management slice 4" and the earlier
Inventory-slice incident it references) -- a real, git-based restore via
`git show HEAD:backend/storage/graph.json`, since this repo happens to
track storage/graph.json in git. This is documented as what ACTUALLY
happened, not an invented enterprise DR system with RTO/RPO numbers this
codebase has no real mechanism to back.

Real, composed signals (reusing already-real data from this same slice,
not a new engine):
  - Latest observed real backup (hub_core/tenant_storage_metrics.py's last-
    fetched snapshot -- backend/core/data_backup.py's real backup
    mechanism).
  - Latest logged backup event (hub_core/dealer_backups.py's honest manual
    log).
  - Real, live reachability (hub_core/server_health.py) -- if a dealer is down
    right now, that's directly relevant to "can we even reach this tenant
    to recover it."
  - A real, best-effort git-tracked-snapshot check (dev-only, same
    co-located-filesystem caveat as hub_core/tenant_storage_metrics.py's local
    fallback) -- whether storage/graph.json is tracked by git in this repo
    and when it was last committed, since that's the literal mechanism this
    session's own incidents were recovered with. NOT assumed true for a
    real, separately-hosted production tenant (a real deployment would
    almost certainly gitignore live data files) -- stated plainly.
"""

import os
import subprocess

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.server_health import get_server_health_overview
from hub_core.tenant_storage_metrics import registry as storage_registry
from hub_core.dealer_backups import registry as backups_log_registry


_RECOVERY_PLAYBOOK_STEPS = [
    {
        "step": 1,
        "title": "Confirm the incident before touching anything",
        "detail": (
            "Before running any recovery command, confirm what actually "
            "happened: run `git status` in the tenant's backend directory "
            "and compare storage/graph.json's real entity/relationship "
            "counts (see the Databases panel) against what's expected. Do "
            "NOT restore from a hunch -- confirm the file is genuinely "
            "wrong first (this session's own two real incidents were both "
            "caught this way, via a diff/count check, before any recovery "
            "command was run)."
        ),
    },
    {
        "step": 2,
        "title": "Prefer a real, timestamped backup if one exists",
        "detail": (
            "Check the Backups panel for this dealer's most recent real "
            "backup (storage/backups/graph_<timestamp>.json). If one "
            "exists and predates the incident, an ADMIN can restore it "
            "directly through the tenant's own Data Management screen "
            "(POST /data-management/backups/{backup_id}/restore) -- this "
            "is the real, already-built, in-product recovery path and "
            "should be tried first."
        ),
    },
    {
        "step": 3,
        "title": "Git-based recovery (the real method used twice this "
        "session, when no in-product backup was current enough)",
        "detail": (
            "If storage/graph.json is tracked in this repo's git history "
            "(true for this dev/sandbox environment -- NOT assumed true "
            "for a real, separately-hosted production tenant, which would "
            "likely gitignore live data files), the last known-good commit "
            "can be restored directly:\n\n"
            "  git show HEAD:backend/storage/graph.json > backend/storage/graph.json\n\n"
            "Then restart (or, if the process is still running, call "
            "load_graph() again in-process) so the tenant's in-memory "
            "ledger picks up the restored file. Verify afterward with a "
            "real entity/relationship count check, not just a route-count "
            "check -- exactly the discipline CLAUDE.md's own incident "
            "notes establish."
        ),
    },
    {
        "step": 4,
        "title": "Re-verify with real counts, not just a clean boot",
        "detail": (
            "A clean `import api.app` boot or a matching route count is "
            "NOT sufficient proof of a successful recovery -- this "
            "session's own incident notes document a subagent's 'verified "
            "restored' claim that was independently caught as still wrong. "
            "Confirm real entity_count/relationship_count/audit event "
            "count match the expected pre-incident baseline (the Databases "
            "panel's own real figures) before considering the recovery "
            "complete."
        ),
    },
]


def _co_located_git_snapshot_check(dealer):
    """DEV-ONLY, best-effort -- mirrors hub_core/tenant_storage_metrics.py's own
    local-filesystem fallback caveat exactly. Only meaningful when the Hub
    and this dealer's tenant process share one filesystem AND that
    filesystem is inside a git repo tracking storage/graph.json (true for
    this sandbox, not assumed true for a real production tenant). Never
    raises."""

    tenant_root = os.path.join("..", "backend")
    graph_relpath = os.path.join(dealer.storage_dir, "graph.json")

    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H|%cI", "--", graph_relpath],
            cwd=tenant_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = (result.stdout or "").strip()
    if result.returncode != 0 or not output:
        return None

    commit_hash, _, committed_at = output.partition("|")
    return {
        "tracked_in_git": True,
        "last_commit_hash": commit_hash[:12],
        "last_committed_at": committed_at or None,
        "basis": "hub_local_git_read_dev_only",
        "note": (
            "This dealer's storage/graph.json happens to be tracked in "
            "this repo's own git history in this sandbox -- a real, "
            "checkable fact here, but NOT assumed true for a real, "
            "separately-hosted production tenant, which would very likely "
            "gitignore live data files instead."
        ),
    }


def get_disaster_recovery_status():

    dealers = dealer_registry.list_all()
    health = get_server_health_overview()
    status_by_dealer = {c["dealer_id"]: c for c in health["dealers"]}

    per_dealer = []
    for dealer in dealers:
        snapshot = storage_registry.get(dealer.dealer_id)
        backups = snapshot.data.get("backups") if (snapshot and snapshot.reachable) else None
        logged = [entry for entry in backups_log_registry.list_for_dealer(dealer.dealer_id)
                  if entry.to_dict()["timestamp_status"] == "known"]

        per_dealer.append({
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "current_reachability": status_by_dealer.get(dealer.dealer_id, {}).get("status", "unknown"),
            "latest_observed_backup": {
                "file_count": backups.get("file_count") if backups else None,
                "latest_file": backups.get("latest_file") if backups else None,
                "latest_modified_at": backups.get("latest_modified_at") if backups else None,
            } if backups is not None else None,
            "latest_logged_backup_event": logged[0].to_dict() if logged else None,
            "git_snapshot_check": _co_located_git_snapshot_check(dealer),
        })

    return {
        "dealers": per_dealer,
        "playbook": _RECOVERY_PLAYBOOK_STEPS,
        "disclosure": (
            "This is documentation + real, already-collected signals -- "
            "deliberately NOT a one-click automated restore action. A "
            "wrong restore genuinely overwrites a live tenant's real data; "
            "the actual restore mechanism (backend/core/data_backup.py's "
            "restore_backup(), ADMIN-only, tenant-side) and the git-based "
            "recovery method documented in the playbook above are both "
            "real and already exist -- this screen is a reference/status "
            "view over them, not a new destructive action added here. The "
            "playbook's step 3 (git-based recovery) is the exact method "
            "this session's own two real recovered data-loss incidents "
            "used, restated here rather than invented."
        ),
    }
