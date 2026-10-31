"""
Tenant-side receiver for the NXTDeal Hub's real-time AI Kill Switch
emergency-push mechanism (security-hardening pass, 2026-07-20, Task #6).

Same DEALEROS_NETWORK_KEY shared secret every other Hub<->tenant
server-to-server route already uses (/network/anonymous-snapshot,
/network/ai-management-snapshot, /network/operational-health-snapshot),
reused via core/network_snapshot_api.py's check_network_key() -- no second
copy of the shared-secret check.

Two functions, matching the "status is fetched live, a push is a real
recorded action" split hub/hub_core/dealer_ai_kill_switch.py's own docstring
establishes for the Hub side:

  - get_ai_kill_switch_status_network_api() -- a plain, read-only reuse of
    core/ai_kill_switch.py's own get_kill_switch_overview(), gated by the
    network key instead of an employee Bearer token (the Hub has no
    employee credentials for a dealer it doesn't operate, the identical
    reasoning core/ai_management_network_api.py's own docstring already
    gives for that route). No PII in this payload -- switch state, real
    department names, and a free-text reason string an ADMIN/OPERATIONS
    employee themselves already wrote when they set it.

  - push_ai_kill_switch_api() -- the real emergency-stop mechanism. A
    Hub-pushed toggle is ALWAYS recorded with updated_by="hub_emergency_push"
    (never a specific employee id, since no employee on THIS tenant actually
    took the action -- a NXTDeal staffer did, from the Hub console), so the
    stored kill-switch state and this tenant's own audit trail always
    distinguish a Hub-initiated emergency stop from a local admin's own
    action, matching core/ai_kill_switch.py's own module docstring claim
    verbatim. Reuses core/ai_kill_switch.py's 4 existing scope-specific
    setters directly -- no parallel mutation path, no way for a network-key
    holder to do anything a local ADMIN/OPERATIONS employee couldn't
    already do through the regular, Bearer-token-gated /ai-kill-switch/*
    routes.
"""

from core.network_snapshot_api import check_network_key
from core.ai_kill_switch import (
    get_kill_switch_overview,
    set_dealer_wide_kill_switch,
    set_department_kill_switch,
    set_bot_kill_switch,
    set_workflow_automation_kill_switch,
)

HUB_PUSH_ACTOR = "hub_emergency_push"

_VALID_PUSH_SCOPES = ("dealer_wide", "department", "bot", "workflow_automation")


def get_ai_kill_switch_status_network_api(network_key):

    error = check_network_key(network_key)
    if error:
        return error

    return get_kill_switch_overview()


def push_ai_kill_switch_api(network_key, scope, active, reason=None, department=None):

    error = check_network_key(network_key)
    if error:
        return error

    if scope not in _VALID_PUSH_SCOPES:
        return {"error": f"Unknown kill-switch scope '{scope}'. Valid: {_VALID_PUSH_SCOPES}"}

    if scope == "dealer_wide":
        result = set_dealer_wide_kill_switch(bool(active), HUB_PUSH_ACTOR, reason=reason)
    elif scope == "department":
        if not department:
            return {"error": "A department is required when scope='department'."}
        result = set_department_kill_switch(department, bool(active), HUB_PUSH_ACTOR, reason=reason)
    elif scope == "bot":
        result = set_bot_kill_switch(bool(active), HUB_PUSH_ACTOR, reason=reason)
    else:
        result = set_workflow_automation_kill_switch(bool(active), HUB_PUSH_ACTOR, reason=reason)

    if isinstance(result, dict) and result.get("error"):
        return result

    return {"scope": scope, "department": department, "state": result}
