"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/dealer_backups.py, matching backend/core/*_api.py's "validate + call
the real function + shape the response" convention.
"""

from hub_core.dealer_backups import (
    log_backup_event,
    get_backups_for_dealer,
    get_backups_overview,
    registry,
)
from hub_core.dealer_backups_storage import save_dealer_backups_log
from hub_core.hub_audit_api import record_and_save

DEALER_BACKUPS_LOG_PATH = "storage/dealer_backups_log.json"


def get_backups_overview_api():
    return get_backups_overview()


def get_dealer_backups_api(dealer_id):
    result, error = get_backups_for_dealer(dealer_id)
    if error:
        return {"error": error}
    return result


def log_dealer_backup_api(dealer_id, logged_by, label=None, note=None):

    entry, error = log_backup_event(dealer_id, logged_by, label=label, note=note)

    if error:
        return {"error": error}

    try:
        save_dealer_backups_log(DEALER_BACKUPS_LOG_PATH)
    except Exception:
        # A failed manual log write is not confirmed backup activity. Remove only
        # this entry; preserve unrelated records and never rewind shared IDs.
        if registry.entries.get(entry.log_id) is entry:
            registry.entries.pop(entry.log_id, None)
        raise

    record_and_save(
        event_type="dealer_backup_logged",
        summary=f"Backup event logged for {dealer_id} by {logged_by}",
        dealer_id=dealer_id,
        actor=logged_by,
        details={"log_id": entry.log_id, "label": entry.label},
    )

    result, _ = get_backups_for_dealer(dealer_id)
    return result
