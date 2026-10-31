"""
core/negotiation_engine_api.py -- API layer for the AI Negotiation Engine (2026-07-24, DR-3).

Gate posture:
  * Viewing rules / sessions / summary: any authenticated role (operational insight).
  * Changing the dealer rules (the profit envelope): ADMIN only.
  * Starting a session, evaluating/applying an offer, accepting: the sales-desk roles
    (ADMIN/OPERATIONS/SALES/FINANCE) -- the same _BOARD_VIEW_ROLES core/deals_api.py uses to
    desk a deal. (The customer / AI-worker driven paths arrive in DR-4, which calls the core
    functions with an actor_kind so core/execution_modes.py governs who may drive it.)
  * Resolving an escalation (manager approval): the F&I / manager roles
    (ADMIN/OPERATIONS/FINANCE) -- outside-the-envelope offers need a manager.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE
from core.negotiation_engine import (
    get_rules,
    set_rules,
    negotiation_summary,
    start_session,
    evaluate_offer,
    apply_offer,
    resolve_escalation,
    accept_session,
    get_session,
    list_sessions,
)

_DESK_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)
_MANAGER_ROLES = (ADMIN, OPERATIONS, FINANCE)


def get_negotiation_dashboard_api(role):
    return {"rules": get_rules(), "summary": negotiation_summary(),
            "recent_sessions": list_sessions(limit=25)["sessions"]}


def get_negotiation_rules_api(role):
    return {"rules": get_rules()}


def set_negotiation_rules_api(admin_role, admin_id, patch):
    if admin_role != ADMIN:
        return {"error": "Admin role required to change negotiation rules"}
    return set_rules(patch, admin_id)


def list_sessions_api(role, deal_id=None, status=None, limit=100):
    return list_sessions(deal_id=deal_id, status=status, limit=limit)


def get_session_api(role, session_id):
    view = get_session(session_id)
    return view if view else {"error": f"No deal session {session_id}"}


def start_session_api(role, actor_id, deal_id, ttl_hours=None, target_payment=None):
    if role not in _DESK_ROLES:
        return {"error": "Not permitted to start a negotiation session"}
    return start_session(deal_id, actor_id, ttl_hours=ttl_hours, target_payment=target_payment)


def evaluate_offer_api(role, session_id, proposal):
    if role not in _DESK_ROLES:
        return {"error": "Not permitted to evaluate a negotiation offer"}
    return evaluate_offer(session_id, proposal)


def apply_offer_api(role, actor_id, session_id, proposal):
    if role not in _DESK_ROLES:
        return {"error": "Not permitted to apply a negotiation offer"}
    # A staff member on the desk is a human actor.
    return apply_offer(session_id, proposal, actor_id, actor_kind="human")


def resolve_escalation_api(role, manager_id, session_id, decision, note=None):
    if role not in _MANAGER_ROLES:
        return {"error": "Manager role required to resolve a negotiation escalation"}
    return resolve_escalation(session_id, decision, manager_id, note=note)


def accept_session_api(role, actor_id, session_id):
    if role not in _DESK_ROLES:
        return {"error": "Not permitted to accept a negotiation"}
    return accept_session(session_id, actor_id)
