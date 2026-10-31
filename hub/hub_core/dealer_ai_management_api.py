"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/dealer_ai_management.py, matching backend/core/*_api.py's "validate + call
the real function + shape the response" convention.
"""

from hub_core.dealer_ai_management import (
    list_ai_area_catalog,
    get_dealer_ai_management,
    recompute_dealer_ai_snapshot,
)
from hub_core.dealer_ai_management_storage import save_dealer_ai_snapshots

DEALER_AI_SNAPSHOTS_PATH = "storage/dealer_ai_snapshots.json"


def get_ai_area_catalog_api():
    return {"areas": list_ai_area_catalog()}


def get_dealer_ai_management_api(dealer_id):
    result, error = get_dealer_ai_management(dealer_id)
    if error:
        return {"error": error}
    return result


def recheck_dealer_ai_management_api(dealer_id):

    snapshot, error = recompute_dealer_ai_snapshot(dealer_id)

    if error:
        return {"error": error}

    save_dealer_ai_snapshots(DEALER_AI_SNAPSHOTS_PATH)

    result, _ = get_dealer_ai_management(dealer_id)
    return result
