"""
Thin ACL layer for core/manager_to.py. Requesting a TO is open to any rep who can
already act on a Lead/Deal (ADMIN/OPERATIONS/SALES) -- claiming and resolving is
gated to manager-tier, using the exact same infer_tier()-off-Employee.Title
convention core/sales_overview.py's is_manager_view already established, since this
codebase has no separate "sales manager" role.
"""

from core.dealeros import ledger
from core.entity_types import LEAD, DEAL
from core.manager_to import request_to, claim_to, resolve_to, list_tos, list_open_tos, get_stats, REASONS, STATUSES, OUTCOMES
from core.permissions import ADMIN, OPERATIONS, SALES
from core.bot_tasks import infer_tier, TIER_MANAGER, TIER_EXECUTIVE

_REQUEST_ROLES = (ADMIN, OPERATIONS, SALES)


def _employee_name(employee_id):

    if not employee_id:
        return None

    e = ledger.get_entity(employee_id)

    if not e:
        return employee_id

    return f"{e.attributes.get('FirstName', '')} {e.attributes.get('LastName', '')}".strip() or employee_id


def _linked_entity_label(linked_entity_id, linked_entity_type):

    entity = ledger.get_entity(linked_entity_id)

    if not entity:
        return linked_entity_id

    if linked_entity_type == LEAD:
        return f"{entity.attributes.get('FirstName', '')} {entity.attributes.get('LastName', '')}".strip() or linked_entity_id

    if linked_entity_type == DEAL:
        customer = ledger.get_entity(entity.attributes.get("customer_id"))
        customer_name = (
            f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip()
            if customer else None
        )
        return customer_name or linked_entity_id

    return linked_entity_id


def _is_manager(role, employee_id):

    if role in (ADMIN, OPERATIONS):
        return True

    employee = ledger.get_entity(employee_id)
    tier = infer_tier(employee.attributes.get("Title") if employee else None)

    return tier in (TIER_MANAGER, TIER_EXECUTIVE)


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _serialize(to_entity):

    a = to_entity.attributes

    return {
        "id": to_entity.id,
        "linked_entity_id": a.get("linked_entity_id"),
        "linked_entity_type": a.get("linked_entity_type"),
        "linked_entity_label": _linked_entity_label(a.get("linked_entity_id"), a.get("linked_entity_type")),
        "requested_by": a.get("requested_by"),
        "requested_by_name": _employee_name(a.get("requested_by")),
        "reason": a.get("reason"),
        "notes": a.get("notes", ""),
        "status": a.get("status"),
        "requested_at": a.get("requested_at"),
        "claimed_by": a.get("claimed_by"),
        "claimed_by_name": _employee_name(a.get("claimed_by")),
        "claimed_at": a.get("claimed_at"),
        "resolved_by": a.get("resolved_by"),
        "resolved_by_name": _employee_name(a.get("resolved_by")),
        "resolved_at": a.get("resolved_at"),
        "outcome": a.get("outcome"),
        "resolution_notes": a.get("resolution_notes", ""),
    }


def list_to_reasons_api():
    return REASONS


def list_to_statuses_api():
    return STATUSES


def list_to_outcomes_api():
    return OUTCOMES


def request_to_api(role, employee_id, linked_entity_id, reason, notes=""):

    if role not in _REQUEST_ROLES:
        return {"error": "You don't have access to request a TO"}

    result = request_to(linked_entity_id, employee_id, reason, notes=notes)

    if _is_error(result):
        return result

    return _serialize(result)


def claim_to_api(role, employee_id, to_id):

    if not _is_manager(role, employee_id):
        return {"error": "Only a manager can claim a TO"}

    result = claim_to(to_id, employee_id)

    if _is_error(result):
        return result

    return _serialize(result)


def resolve_to_api(role, employee_id, to_id, outcome, notes=""):

    if not _is_manager(role, employee_id):
        return {"error": "Only a manager can resolve a TO"}

    result = resolve_to(to_id, employee_id, outcome, notes=notes)

    if _is_error(result):
        return result

    return _serialize(result)


def list_open_tos_api(role):

    if role not in _REQUEST_ROLES:
        return {"error": "You don't have access to the TO board"}

    return [_serialize(t) for t in list_open_tos()]


def list_tos_api(role, status=None):

    if role not in _REQUEST_ROLES:
        return {"error": "You don't have access to the TO board"}

    return [_serialize(t) for t in list_tos(status=status)]


def get_to_stats_api(role):

    if role not in _REQUEST_ROLES:
        return {"error": "You don't have access to TO stats"}

    return get_stats()
