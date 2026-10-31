"""
Thin ACL layer for core/marketing_lists.py (session 82), imported directly into
api/app.py's route handlers -- same "no service layer indirection" convention every
other `*_api.py` module in this codebase follows.

Role rule: any authenticated role can browse/read lists and their members -- Sam:
"this is actually a functionality that is going to appear on the sales side as well,"
so Lists are internal working data with the same broad visibility as CAMPAIGN/
EMAIL_TEMPLATE in core/permissions.py's ENTITY_ACCESS, not a Marketing-only tool.
Creating a list or curating its membership is scoped to the creator, or MARKETING/
ADMIN, mirroring core/email_templates_api.py's ownership check.
"""

from core.marketing_lists import (
    create_list,
    build_list_from_pool,
    get_list,
    update_list,
    add_members,
    remove_members,
    delete_list,
    list_lists,
    get_list_members,
)
from core.campaigns import get_campaign_type
from core.permissions import ADMIN, MARKETING


def _can_manage_all(role):
    return role == ADMIN or role == MARKETING


def _can_edit(role, employee_id, entity):
    return _can_manage_all(role) or entity.attributes.get("created_by") == employee_id


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def create_list_api(employee_id, name, description=""):

    if not (name or "").strip():
        return {"error": "A list needs a name."}

    entity = create_list(name.strip(), employee_id, description or "")

    return _serialize(entity)


def build_list_from_pool_api(employee_id, name, campaign_type_key, params, description=""):

    if not (name or "").strip():
        return {"error": "A list needs a name."}

    if not get_campaign_type(campaign_type_key):
        return {"error": f"Unknown campaign type '{campaign_type_key}'"}

    entity = build_list_from_pool(name.strip(), employee_id, campaign_type_key, params or {}, description or "")

    return _serialize(entity)


def get_list_api(role, employee_id, list_id):

    entity = get_list(list_id)

    if not entity:
        return {"error": "List not found"}

    return _serialize(entity)


def list_lists_api(role, employee_id, mine_only=False):

    lists = list_lists(created_by=employee_id if mine_only else None)

    return [_serialize(l) for l in lists]


def get_list_members_api(role, employee_id, list_id, page=1, page_size=25, entity_type_filter=None):

    entity = get_list(list_id)

    if not entity:
        return {"error": "List not found"}

    return get_list_members(list_id, page, page_size, entity_type_filter)


def update_list_api(role, employee_id, list_id, patch):

    entity = get_list(list_id)

    if not entity:
        return {"error": "List not found"}

    if not _can_edit(role, employee_id, entity):
        return {"error": "Only the creator (or marketing/admin) can edit this list"}

    updated = update_list(list_id, patch or {})

    return _serialize(updated)


def add_members_api(role, employee_id, list_id, entity_ids):

    entity = get_list(list_id)

    if not entity:
        return {"error": "List not found"}

    if not _can_edit(role, employee_id, entity):
        return {"error": "Only the creator (or marketing/admin) can edit this list"}

    result = add_members(list_id, entity_ids or [])

    return {"list": _serialize(result["list"]), "added": result["added"]}


def remove_members_api(role, employee_id, list_id, entity_ids):

    entity = get_list(list_id)

    if not entity:
        return {"error": "List not found"}

    if not _can_edit(role, employee_id, entity):
        return {"error": "Only the creator (or marketing/admin) can edit this list"}

    updated = remove_members(list_id, entity_ids or [])

    return _serialize(updated)


def delete_list_api(role, employee_id, list_id):

    entity = get_list(list_id)

    if not entity:
        return {"error": "List not found"}

    if not _can_edit(role, employee_id, entity):
        return {"error": "Only the creator (or marketing/admin) can archive this list"}

    updated = delete_list(list_id)

    return _serialize(updated)
