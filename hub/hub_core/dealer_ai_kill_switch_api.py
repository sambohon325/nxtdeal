"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/dealer_ai_kill_switch.py, matching backend/core/*_api.py's
"validate + call the real function + shape the response" convention.
Every real push is also recorded to the Hub's own centralized audit log
(hub_core/hub_audit_api.py's record_and_save()), same discipline every other
mutation in this rebuild follows.
"""

from hub_core.dealer_ai_kill_switch import (
    get_dealer_kill_switch_status,
    push_kill_switch_to_dealer,
    list_kill_switch_actions_for_dealer,
    list_all_kill_switch_actions,
)
from hub_core.dealer_ai_kill_switch_storage import save_dealer_ai_kill_switch_actions
from hub_core.hub_audit_api import record_and_save

DEALER_AI_KILL_SWITCH_ACTIONS_PATH = "storage/dealer_ai_kill_switch_actions.json"


def get_dealer_kill_switch_status_api(dealer_id):
    result, error = get_dealer_kill_switch_status(dealer_id)
    if error:
        return {"error": error}
    return result


def push_dealer_kill_switch_api(dealer_id, pushed_by, scope, active, reason=None, department=None):

    action, error = push_kill_switch_to_dealer(
        dealer_id, pushed_by, scope, active, reason=reason, department=department
    )

    if error:
        return {"error": error}

    save_dealer_ai_kill_switch_actions(DEALER_AI_KILL_SWITCH_ACTIONS_PATH)

    record_and_save(
        event_type="ai_kill_switch_pushed",
        summary=(
            f"AI kill switch [{scope}] {'ACTIVATED' if action.active else 'deactivated'} "
            f"on {dealer_id} by {pushed_by} "
            f"({'succeeded' if action.success else 'FAILED: ' + str(action.push_error)})"
        ),
        dealer_id=dealer_id,
        actor=pushed_by,
        details={
            "action_id": action.action_id,
            "scope": action.scope,
            "active": action.active,
            "department": action.department,
            "success": action.success,
        },
    )

    return action.to_dict()


def get_dealer_kill_switch_history_api(dealer_id):
    result, error = list_kill_switch_actions_for_dealer(dealer_id)
    if error:
        return {"error": error}
    return result


def get_all_kill_switch_history_api():
    return list_all_kill_switch_actions()
