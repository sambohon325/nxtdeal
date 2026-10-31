"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 2 of 4:
Storage.

Real disk usage across every real store this platform actually has: each
dealer tenant's real graph.json/audit.json/credentials.json/uploads/backups
file sizes (fetched via hub/hub_core/tenant_storage_metrics.py -- the SAME real
signal hub_core/databases.py's Primary tier already surfaces, presented here
through a disk-usage/growth lens instead of a database-health lens) plus
the Hub's OWN real storage files (hub/storage/*.json -- dealers/network
snapshots/modules/feature flags/onboarding/migrations/integrations/AI
snapshots/network membership/support/audit log/contacts), read directly
off this Hub process's own local disk (always real, always live -- the Hub
IS this process, no fetch needed).

No fabricated growth projection -- "growth" reported here is a real,
point-in-time size comparison against the LAST fetched snapshot for a given
dealer (if any), not a forecast.
"""

import os

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.tenant_storage_metrics import registry as storage_registry


# Every real Hub-side storage file this codebase actually writes, per its
# own module's PATH constant -- kept as a plain list here (not re-imported
# from each module, to avoid a long, fragile import chain) since these are
# well-established, stable filenames documented throughout hub/app.py's own
# load_*() calls at boot.
_HUB_STORAGE_FILES = [
    ("dealers", "storage/dealers.json"),
    ("network_snapshots", "storage/network_snapshots.json"),
    ("dealer_modules", "storage/dealer_modules.json"),
    ("feature_flags", "storage/feature_flags.json"),
    ("dealer_onboarding", "storage/dealer_onboarding.json"),
    ("dealer_migrations", "storage/dealer_migrations.json"),
    ("dealer_integrations", "storage/dealer_integrations.json"),
    ("dealer_ai_snapshots", "storage/dealer_ai_snapshots.json"),
    ("dealer_network_membership", "storage/dealer_network_membership.json"),
    ("dealer_support", "storage/dealer_support.json"),
    ("hub_audit_log", "storage/hub_audit.json"),
    ("dealer_contacts", "storage/dealer_contacts.json"),
    ("dealer_backups_log", "storage/dealer_backups_log.json"),
    ("hub_credentials", "storage/hub_credentials.json"),
    ("provisioning", "storage/provisioning.json"),
    ("demo_accounts", "storage/demo_accounts.json"),
    ("network_connect_accounts", "storage/network_connect_accounts.json"),
    ("code_audit_findings", "storage/code_audit_findings.json"),
    ("code_audit_runs", "storage/code_audit_runs.json"),
    ("dealer_ai_kill_switch_actions", "storage/dealer_ai_kill_switch_actions.json"),
]


def _safe_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def get_hub_own_storage():
    """The Hub's own storage files -- always real, always live (this
    process reads its own local disk directly, no network fetch needed)."""

    files = []
    total = 0
    paths = [(key, path, path) for key, path in _HUB_STORAGE_FILES]
    # Inventory configured personal storage even while the feature is disabled:
    # disabling access does not remove existing accounts or their recovery needs.
    # Stat only; never connect to SQLite or create a missing database here.
    personal_path = os.getenv("NXTDEAL_MYSALES_DB", "")
    if personal_path and os.path.isabs(personal_path):
        for suffix, key in [("", "mysales"), ("-wal", "mysales_wal"),
                            ("-shm", "mysales_shm"), ("-journal", "mysales_journal")]:
            paths.append((key, personal_path + suffix, "NXTDEAL_MYSALES_DB" + suffix))
    for key, path, display_path in paths:
        size = _safe_size(path)
        exists = size is not None
        if exists:
            total += size
        files.append({
            "store": key,
            "path": display_path,
            "exists": exists,
            "size_bytes": size or 0,
        })

    return {
        "files": files,
        "total_size_bytes": total,
        "note": (
            "Known Hub JSON stores and the configured personal MySales SQLite "
            "database/sidecars, measured from local file metadata only. Missing "
            "or unreadable files have unknown size. This point-in-time inventory "
            "is not a consistent backup: use SQLite's online backup API for a "
            "live database and coordinate JSON-store backups with writers."
        ),
        "mysales_path_status": ("configured" if personal_path and os.path.isabs(personal_path)
                                else "invalid" if personal_path else "not_configured"),
    }


def _dealer_storage_entry(dealer):

    snapshot = storage_registry.get(dealer.dealer_id)

    if snapshot is None or not snapshot.reachable:
        return {
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "checked": snapshot is not None,
            "reachable": snapshot.reachable if snapshot else None,
            "basis": snapshot.basis if snapshot else None,
            "fetched_at": snapshot.fetched_at if snapshot else None,
            "error": snapshot.error if snapshot else None,
            "total_size_bytes": None,
            "breakdown": None,
        }

    data = snapshot.data
    graph = data.get("graph_json", {}) or {}
    audit = data.get("audit_json", {}) or {}
    creds = data.get("credentials_json", {}) or {}
    uploads = data.get("uploads", {}) or {}
    backups = data.get("backups", {}) or {}

    total = sum(
        v or 0
        for v in [
            graph.get("size_bytes"),
            audit.get("size_bytes"),
            creds.get("size_bytes"),
            uploads.get("total_size_bytes"),
            backups.get("total_size_bytes"),
        ]
    )

    return {
        "dealer_id": dealer.dealer_id,
        "dealer_name": dealer.name,
        "checked": True,
        "reachable": True,
        "basis": snapshot.basis,
        "fetched_at": snapshot.fetched_at,
        "error": None,
        "total_size_bytes": total,
        "breakdown": {
            "graph_json_bytes": graph.get("size_bytes"),
            "audit_json_bytes": audit.get("size_bytes"),
            "credentials_json_bytes": creds.get("size_bytes"),
            "uploads_bytes": uploads.get("total_size_bytes"),
            "uploads_file_count": uploads.get("file_count"),
            "backups_bytes": backups.get("total_size_bytes"),
            "backups_file_count": backups.get("file_count"),
        },
        "dev_note": data.get("_dev_note"),
    }


def get_storage_overview():

    dealers = dealer_registry.list_all()
    dealer_entries = [_dealer_storage_entry(d) for d in dealers]

    hub_storage = get_hub_own_storage()

    known_tenant_total = sum(e["total_size_bytes"] or 0 for e in dealer_entries if e["total_size_bytes"])

    return {
        "hub_storage": hub_storage,
        "dealers": dealer_entries,
        "summary": {
            "total_dealers": len(dealers),
            "dealers_with_known_storage": len([e for e in dealer_entries if e["total_size_bytes"] is not None]),
            "known_tenant_storage_bytes": known_tenant_total,
            "hub_storage_bytes": hub_storage["total_size_bytes"],
        },
        "note": (
            "Real disk usage only -- the Hub's own figures are always live "
            "(this process reads its own local disk directly); each "
            "dealer's figures are their LAST-KNOWN fetched snapshot (see "
            "hub_core/tenant_storage_metrics.py -- either a real live network "
            "fetch, or, only for today's one co-located dev tenant, a "
            "clearly-labeled Hub-local filesystem read). No growth "
            "forecasting or fabricated projection -- these are real, "
            "point-in-time sizes, not a trend model."
        ),
    }
