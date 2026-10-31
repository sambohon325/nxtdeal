"""
Multi-tenant storage path config (NXTDeal Hub, session 50).

Every dealer's NXTDeal backend is the same codebase, pointed at its own storage
directory via one environment variable. This module is the single source of truth for
that directory so it only has to be read from the environment once, in one place.

Design: `hub/` (new, sibling to backend/) provisions a fresh tenant by scaffolding
`backend/storage/tenants/{dealer_id}/` with empty graph.json/audit.json/credentials.json
plus a first ADMIN credential. That dealer's actual running backend process is then
started with `DEALEROS_STORAGE_DIR=storage/tenants/{dealer_id}` in its environment (or
left unset for today's one real dealer, which keeps writing to plain `storage/` exactly
as before -- this file changes nothing for that dealer until the env var is set).

STATUS -- the storage-path call-site migration is COMPLETE as of session 52. api/app.py's
three top-level load_graph/load_audit_log/load_credentials calls use this module, and
every save_graph/save_audit_log/save_credentials call site across core/*_api.py and the
core/*.py modules now imports GRAPH_PATH/AUDIT_PATH/CREDENTIALS_PATH from here instead of
hardcoding the literal "storage/..." path (16 files migrated session 52:
documents/service_intake/vehicle_intake/lead_intake/field_notes/bot_coverage/
data_connections/lead_assignment/lead_workflows/auth_api/assets_api/campaigns_api/
deals_api/websites_api/escalation_routing_api/routing_api; workflow_tracking was already
migrated). A provisioned tenant whose DEALEROS_STORAGE_DIR is set to something other than
the default "storage" now has all of its *writes* land in its own directory, not the
original storage/. Remaining known non-json path still tied to storage/: documents.py's
UPLOAD_DIR = "storage/uploads" (chat attachment bytes) -- out of scope for this migration,
which covered graph/audit/credentials json only.

STATUS UPDATE (session 55) -- the last remaining non-json path, documents.py's chat-
attachment UPLOAD_DIR, is now migrated too via uploads_dir()/UPLOADS_DIR below. Every
storage location in the backend (graph/audit/credentials json plus uploaded attachment
bytes) now resolves through this module, so a provisioned tenant with DEALEROS_STORAGE_DIR
set is fully isolated on disk. No known storage-relative path outside this module remains.
"""

import os

_ENV_VAR = "DEALEROS_STORAGE_DIR"
_DEFAULT_DIR = "storage"


def storage_dir():
    """The active tenant's storage directory, e.g. "storage" (default, today's one real
    dealer) or "storage/tenants/DLR-00002" (a provisioned tenant). Read fresh on every
    call (not cached at import time) so tests can monkeypatch the env var freely."""

    return os.environ.get(_ENV_VAR, _DEFAULT_DIR)


def storage_path(filename):
    """Join the active tenant's storage directory with a filename, e.g.
    storage_path("graph.json") -> "storage/graph.json" or
    "storage/tenants/DLR-00002/graph.json"."""

    return f"{storage_dir()}/{filename}"


def uploads_dir():
    """The active tenant's chat-attachment upload directory (backing documents.py's raw
    file bytes), e.g. "storage/uploads" or "storage/tenants/DLR-00002/uploads". Read
    fresh on every call (like storage_dir()) so a provisioned tenant's attachments land
    in its own directory, never the default one."""

    return storage_path("uploads")


# Convenience constants for the three boot-critical files. These are computed at import
# time for callers that just want "the current path" without a function call -- fine for
# api/app.py's one-time startup load, but anything that could run before/after an env var
# change in the same process (tests, the Hub's own provisioning code) should prefer
# storage_path() directly instead of importing these.
GRAPH_PATH = storage_path("graph.json")
AUDIT_PATH = storage_path("audit.json")
CREDENTIALS_PATH = storage_path("credentials.json")
UPLOADS_DIR = uploads_dir()


def backups_dir():
    """The active tenant's backup snapshot directory (core/data_backup.py,
    Administration's "Data Management" item, Administration Control Center
    rebuild) -- same tenant-aware, read-fresh-on-every-call convention as
    uploads_dir()."""

    return storage_path("backups")
