"""
Thin ACL layer for core/up_system.py. Logging an Up or managing the floor rotation is
gated to ADMIN/OPERATIONS/SALES -- the same roles that already touch Lead assignment
elsewhere in this codebase (core/lead_assignment_api.py).
"""

from core.up_system import (
    get_rotation,
    set_board_active,
    set_board_order,
    peek_next,
    log_up,
    update_up_status,
    list_ups,
    get_be_back_board,
    UP_TYPES,
    UP_STATUSES,
)
from core.dealeros import ledger
from core.permissions import ADMIN, OPERATIONS, SALES

_UP_ROLES = (ADMIN, OPERATIONS, SALES)


def _employee_name(employee_id):

    if not employee_id:
        return None

    e = ledger.get_entity(employee_id)

    if not e:
        return employee_id

    return f"{e.attributes.get('FirstName', '')} {e.attributes.get('LastName', '')}".strip() or employee_id


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _serialize_rotation(rotation):

    board = rotation.attributes.get("board", [])
    next_id = peek_next()

    return {
        "board": [
            {"employee_id": s["employee_id"], "name": _employee_name(s["employee_id"]), "active": s.get("active", True)}
            for s in board
        ],
        "next_index": rotation.attributes.get("next_index", 0),
        "next_up": {"employee_id": next_id, "name": _employee_name(next_id)} if next_id else None,
        "updated_at": rotation.attributes.get("updated_at"),
    }


def _serialize_up(lead):

    return {
        "id": lead.id,
        "first_name": lead.attributes.get("FirstName"),
        "last_name": lead.attributes.get("LastName"),
        "phone": lead.attributes.get("Phone"),
        "email": lead.attributes.get("Email"),
        "up_type": lead.attributes.get("up_type"),
        "up_status": lead.attributes.get("up_status"),
        "up_notes": lead.attributes.get("up_notes", ""),
        "up_logged_by": lead.attributes.get("up_logged_by"),
        "up_logged_by_name": _employee_name(lead.attributes.get("up_logged_by")),
        "up_logged_at": lead.attributes.get("up_logged_at"),
        "assigned_to": lead.attributes.get("AssignedSalesperson"),
        "assigned_to_name": _employee_name(lead.attributes.get("AssignedSalesperson")),
        "pipeline_state": lead.attributes.get("PipelineState"),
    }


def list_up_types_api():
    return list(UP_TYPES)


def list_up_statuses_api():
    return UP_STATUSES


def get_rotation_api(role):

    if role not in _UP_ROLES:
        return {"error": "You don't have access to the floor rotation"}

    return _serialize_rotation(get_rotation())


def set_board_active_api(role, employee_id, active):

    if role not in _UP_ROLES:
        return {"error": "You don't have access to manage the floor rotation"}

    return _serialize_rotation(set_board_active(employee_id, active))


def set_board_order_api(role, employee_ids):

    if role not in _UP_ROLES:
        return {"error": "You don't have access to manage the floor rotation"}

    return _serialize_rotation(set_board_order(employee_ids))


def log_up_api(role, logged_by, up_type, first_name, last_name, phone=None, email=None, notes=""):

    if role not in _UP_ROLES:
        return {"error": "You don't have access to log an Up"}

    result = log_up(up_type, logged_by, first_name, last_name, phone=phone, email=email, notes=notes)

    if _is_error(result):
        return result

    return _serialize_up(result)


def update_up_status_api(role, employee_id, lead_id, new_status):

    if role not in _UP_ROLES:
        return {"error": "You don't have access to update an Up"}

    result = update_up_status(lead_id, new_status, employee_id)

    if _is_error(result):
        return result

    return _serialize_up(result)


def list_ups_api(role, status=None, up_type=None, assigned_to=None, date=None):

    if role not in _UP_ROLES:
        return {"error": "You don't have access to the Up Log"}

    return [_serialize_up(u) for u in list_ups(status=status, up_type=up_type, assigned_to=assigned_to, date=date)]


def get_be_back_board_api(role):

    if role not in _UP_ROLES:
        return {"error": "You don't have access to the Be-Back Board"}

    return [_serialize_up(u) for u in get_be_back_board()]
