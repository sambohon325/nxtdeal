"""
core/knowledge_pins_api.py -- thin ACL layer for Shared Knowledge (session 72),
imported directly into api/app.py's route handlers, same "no service layer
indirection" convention every other `*_api.py` module in this codebase follows.

Unlike core/data_connections_api.py's connection management (ADMIN/OPERATIONS-only),
sharing a pin is something ANY authenticated employee can do -- there's no role gate on
*creating* a shared pin, only on *modifying/deleting* one someone else shared (see
core/knowledge_pins.py's _can_modify -- owner or ADMIN only).
"""

from core.knowledge_pins import (
    SHARE_ROLES,
    create_pin,
    list_pins_for_role,
    retag_pin,
    update_sharing,
    delete_pin,
)


def share_roles_api():
    """The real, fixed list of departments/roles a pin can be shared with -- backs the
    frontend's share picker so it never has to hardcode this list separately."""

    return {"roles": SHARE_ROLES}


def create_shared_pin_api(employee_id, kind, ref_id, label, tag, visibility, roles=None):

    if not label or not label.strip():
        return {"error": "A shared pin needs a label."}

    return create_pin(employee_id, kind, ref_id, label.strip(), (tag or "General").strip(), visibility, roles)


def list_shared_pins_api(role, employee_id):

    return {"pins": list_pins_for_role(role, employee_id)}


def retag_shared_pin_api(pin_id, employee_id, role, tag):

    return retag_pin(pin_id, employee_id, role, tag)


def share_shared_pin_api(pin_id, employee_id, role, add_roles=None, set_all=False):

    return update_sharing(pin_id, employee_id, role, add_roles=add_roles, set_all=set_all)


def delete_shared_pin_api(pin_id, employee_id, role):

    return delete_pin(pin_id, employee_id, role)
