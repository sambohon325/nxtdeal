"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/dealer_onboarding.py, matching backend/core/*_api.py's "validate + call
the real function + shape the response" convention (same as
hub_core/dealer_modules_api.py right alongside this one).
"""

from hub_core.dealer_onboarding import (
    ONBOARDING_STEP_CATALOG,
    get_onboarding_status,
    list_all_onboarding_summaries,
    recompute_auto_steps,
    set_manual_step,
)
from hub_core.dealer_onboarding_storage import save_dealer_onboarding
from hub_core.hub_audit_api import record_and_save

DEALER_ONBOARDING_PATH = "storage/dealer_onboarding.json"


def get_onboarding_catalog_api():
    return {"steps": ONBOARDING_STEP_CATALOG}


def list_onboarding_summaries_api():
    return {"dealers": list_all_onboarding_summaries()}


def get_dealer_onboarding_api(dealer_id):
    result, error = get_onboarding_status(dealer_id)
    if error:
        return {"error": error}
    return result


def recheck_dealer_onboarding_api(dealer_id):

    _, error = recompute_auto_steps(dealer_id)

    if error:
        return {"error": error}

    save_dealer_onboarding(DEALER_ONBOARDING_PATH)

    # Return the composed, label-enriched view (same shape as the GET route),
    # not the raw stored dataclass dict.
    result, _ = get_onboarding_status(dealer_id)
    return result


def set_dealer_onboarding_step_api(dealer_id, step_key, complete, updated_by="nxtdeal_staff", note=None):

    _, error = set_manual_step(dealer_id, step_key, complete, updated_by=updated_by, note=note)

    if error:
        return {"error": error}

    save_dealer_onboarding(DEALER_ONBOARDING_PATH)

    record_and_save(
        event_type="onboarding_step_completed",
        summary=f"Onboarding step '{step_key}' for {dealer_id} set to complete={complete} by {updated_by}",
        dealer_id=dealer_id,
        actor=updated_by,
        details={"step_key": step_key, "complete": complete, "note": note},
    )

    result, _ = get_onboarding_status(dealer_id)
    return result
