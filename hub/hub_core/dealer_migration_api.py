"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/dealer_migration.py, matching backend/core/*_api.py's "validate + call
the real function + shape the response" convention.
"""

from hub_core.dealer_migration import (
    BLOCKED_THRESHOLD_PCT,
    MIGRATION_SOURCE_LABELS,
    MIGRATION_SOURCES,
    READINESS_CATEGORIES,
    READINESS_CATEGORY_LABELS,
    READY_THRESHOLD_PCT,
    get_migration_status,
    list_all_migration_summaries,
    set_migration_source,
    set_readiness,
)
from hub_core.dealer_migration_storage import save_dealer_migrations
from hub_core.hub_audit_api import record_and_save

DEALER_MIGRATIONS_PATH = "storage/dealer_migrations.json"


def get_migration_catalog_api():
    return {
        "sources": [
            {"key": key, "label": MIGRATION_SOURCE_LABELS[key]}
            for key in MIGRATION_SOURCES
        ],
        "readiness_categories": [
            {"key": key, "label": READINESS_CATEGORY_LABELS[key]}
            for key in READINESS_CATEGORIES
        ],
        "go_live_thresholds": {
            "ready_pct": READY_THRESHOLD_PCT,
            "blocked_pct": BLOCKED_THRESHOLD_PCT,
        },
    }


def list_migration_summaries_api():
    return {"dealers": list_all_migration_summaries()}


def get_dealer_migration_api(dealer_id):
    result, error = get_migration_status(dealer_id)
    if error:
        return {"error": error}
    return result


def set_dealer_migration_source_api(dealer_id, migrating_from, other_note=None, updated_by="nxtdeal_staff"):

    _, error = set_migration_source(
        dealer_id, migrating_from, other_note=other_note, updated_by=updated_by
    )

    if error:
        return {"error": error}

    save_dealer_migrations(DEALER_MIGRATIONS_PATH)

    record_and_save(
        event_type="migration_source_set",
        summary=f"Migration source for {dealer_id} set to '{migrating_from}' by {updated_by}",
        dealer_id=dealer_id,
        actor=updated_by,
        details={"migrating_from": migrating_from, "other_note": other_note},
    )

    result, _ = get_migration_status(dealer_id)
    return result


def set_dealer_readiness_api(dealer_id, category, pct, note=None, updated_by="nxtdeal_staff"):

    _, error = set_readiness(dealer_id, category, pct, note=note, updated_by=updated_by)

    if error:
        return {"error": error}

    save_dealer_migrations(DEALER_MIGRATIONS_PATH)

    record_and_save(
        event_type="migration_readiness_set",
        summary=f"Migration readiness '{category}' for {dealer_id} set to {pct}% by {updated_by}",
        dealer_id=dealer_id,
        actor=updated_by,
        details={"category": category, "pct": pct, "note": note},
    )

    result, _ = get_migration_status(dealer_id)
    return result
