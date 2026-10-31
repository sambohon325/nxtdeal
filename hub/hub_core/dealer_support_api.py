"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/dealer_support.py.
"""

from hub_core.dealer_support import (
    recheck_dealer_operational_snapshot,
    get_dealer_support_status,
    compute_churn_risk,
)
from hub_core.dealer_support_storage import save_dealer_support
from hub_core.dealer_registry import registry as dealer_registry

DEALER_SUPPORT_PATH = "storage/dealer_support.json"


def get_dealer_support_status_api(dealer_id):
    result, error = get_dealer_support_status(dealer_id)
    if error:
        return {"error": error}
    return result


def recheck_dealer_support_snapshot_api(dealer_id):

    snapshot, error = recheck_dealer_operational_snapshot(dealer_id)
    if error:
        return {"error": error}

    save_dealer_support(DEALER_SUPPORT_PATH)

    result, _ = get_dealer_support_status(dealer_id)
    return result


def list_support_summaries_api():

    summaries = []
    for dealer in dealer_registry.list_all():
        churn, _ = compute_churn_risk(dealer.dealer_id)
        summaries.append({
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "status": dealer.status,
            "churn_risk_level": churn["level"] if churn else None,
            "churn_risk_points": churn["points"] if churn else None,
        })

    return {"dealers": summaries}
