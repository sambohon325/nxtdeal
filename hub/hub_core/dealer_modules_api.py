"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/dealer_modules.py, matching backend/core/*_api.py's "validate + call the
real function + shape the response" convention (same as hub_core/dealers_api.py
right above this one).
"""

from hub_core.dealer_modules import (
    MODULE_CATALOG,
    get_dealer_module_config,
    set_module_enabled,
)
from hub_core.dealer_modules_storage import save_dealer_modules
from hub_core.dealer_registry import registry as dealer_registry
from hub_core.hub_audit_api import record_and_save

DEALER_MODULES_PATH = "storage/dealer_modules.json"


def get_module_catalog_api():
    return {"modules": MODULE_CATALOG}


def get_dealer_modules_api(dealer_id):
    if not dealer_registry.get(dealer_id):
        return {"error": f"no dealer with id '{dealer_id}'"}
    return get_dealer_module_config(dealer_id)


def set_dealer_module_api(dealer_id, module_key, enabled, updated_by="nxtdeal_staff"):

    result, error = set_module_enabled(
        dealer_id, module_key, enabled, updated_by=updated_by
    )

    if error:
        return {"error": error}

    save_dealer_modules(DEALER_MODULES_PATH)

    record_and_save(
        event_type="module_enabled_changed",
        summary=f"Module '{module_key}' for {dealer_id} set to {enabled} by {updated_by}",
        dealer_id=dealer_id,
        actor=updated_by,
        details={"module_key": module_key, "enabled": enabled},
    )

    return result
