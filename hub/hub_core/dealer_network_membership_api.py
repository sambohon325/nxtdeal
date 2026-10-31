"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/dealer_network_membership.py.
"""

from hub_core.dealer_network_membership import (
    NETWORK_TIERS,
    NETWORK_TIER_LABELS,
    set_network_tier,
    get_dealer_network_membership,
    recheck_pipeline_connectivity,
    list_all_network_membership_summaries,
)
from hub_core.dealer_network_membership_storage import save_dealer_network_membership
from hub_core.hub_audit_api import record_and_save

DEALER_NETWORK_MEMBERSHIP_PATH = "storage/dealer_network_membership.json"


def get_network_membership_catalog_api():
    return {
        "tiers": [
            {"key": key, "label": NETWORK_TIER_LABELS[key]} for key in NETWORK_TIERS
        ],
    }


def list_network_membership_summaries_api():
    return {"dealers": list_all_network_membership_summaries()}


def get_dealer_network_membership_api(dealer_id):
    result, error = get_dealer_network_membership(dealer_id)
    if error:
        return {"error": error}
    return result


def set_dealer_network_tier_api(dealer_id, tier, updated_by="nxtdeal_staff"):

    config, error = set_network_tier(dealer_id, tier, updated_by=updated_by)
    if error:
        return {"error": error}

    save_dealer_network_membership(DEALER_NETWORK_MEMBERSHIP_PATH)

    record_and_save(
        event_type="network_membership_updated",
        summary=f"Network tier for {dealer_id} set to '{tier}' by {updated_by}",
        dealer_id=dealer_id,
        actor=updated_by,
        details={"tier": tier},
    )

    result, _ = get_dealer_network_membership(dealer_id)
    return result


def recheck_dealer_pipeline_connectivity_api(dealer_id):
    result, error = recheck_pipeline_connectivity(dealer_id)
    if error:
        return {"error": error}
    return result
