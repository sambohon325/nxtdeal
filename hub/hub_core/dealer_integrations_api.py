"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/dealer_integrations.py, matching backend/core/*_api.py's "validate + call
the real function + shape the response" convention.
"""

from hub_core.dealer_integrations import (
    PROVIDER_CATALOG,
    VALID_HEALTH_STATUSES,
    VALID_DATA_FLOWS,
    SYNC_FREQUENCY_PRESETS,
    add_integration,
    update_integration,
    remove_integration,
    get_dealer_integrations,
)
from hub_core.dealer_integrations_storage import save_dealer_integrations
from hub_core.hub_audit_api import record_and_save

DEALER_INTEGRATIONS_PATH = "storage/dealer_integrations.json"


def get_integrations_catalog_api():
    return {
        "providers": PROVIDER_CATALOG,
        "health_statuses": VALID_HEALTH_STATUSES,
        "data_flows": VALID_DATA_FLOWS,
        "sync_frequency_presets": SYNC_FREQUENCY_PRESETS,
    }


def get_dealer_integrations_api(dealer_id):
    result, error = get_dealer_integrations(dealer_id)
    if error:
        return {"error": error}
    return result


def add_dealer_integration_api(dealer_id, provider_key, connection_health="healthy",
                                data_flow="bidirectional", sync_frequency="daily",
                                active=True, notes=None, custom_label=None,
                                created_by="nxtdeal_staff"):

    record, error = add_integration(
        dealer_id, provider_key,
        connection_health=connection_health, data_flow=data_flow,
        sync_frequency=sync_frequency, active=active, notes=notes,
        custom_label=custom_label, created_by=created_by,
    )

    if error:
        return {"error": error}

    save_dealer_integrations(DEALER_INTEGRATIONS_PATH)

    record_and_save(
        event_type="integration_added",
        summary=f"Integration '{provider_key}' added for {dealer_id} by {created_by}",
        dealer_id=dealer_id,
        actor=created_by,
        details={"provider_key": provider_key, "integration_id": getattr(record, "integration_id", None)},
    )

    result, _ = get_dealer_integrations(dealer_id)
    return result


def update_dealer_integration_api(integration_id, updated_by="nxtdeal_staff", **fields):

    record, error = update_integration(integration_id, updated_by=updated_by, **fields)

    if error:
        return {"error": error}

    save_dealer_integrations(DEALER_INTEGRATIONS_PATH)

    record_and_save(
        event_type="integration_updated",
        summary=f"Integration '{integration_id}' updated by {updated_by}",
        dealer_id=record.dealer_id,
        actor=updated_by,
        details={"integration_id": integration_id, "fields": fields},
    )

    result, _ = get_dealer_integrations(record.dealer_id)
    return result


def remove_dealer_integration_api(integration_id, removed_by="nxtdeal_staff"):

    record, error = remove_integration(integration_id)

    if error:
        return {"error": error}

    save_dealer_integrations(DEALER_INTEGRATIONS_PATH)

    record_and_save(
        event_type="integration_removed",
        summary=f"Integration '{integration_id}' removed by {removed_by}",
        dealer_id=record.dealer_id,
        actor=removed_by,
        details={"integration_id": integration_id},
    )

    result, _ = get_dealer_integrations(record.dealer_id)
    return result
