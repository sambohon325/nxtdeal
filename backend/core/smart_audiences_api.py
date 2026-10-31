"""
ACL layer for core/smart_audiences.py -- imported directly into api/app.py's route
handlers, same "no service layer indirection" convention every other `*_api.py`
module in this codebase follows.

Role rule: viewing/previewing/evaluating is broad (ADMIN/OPERATIONS/SALES/MARKETING
-- Sales legitimately works off Marketing-built segments too, same reasoning
core/marketing_lists.py's own broad readability grants SALES, session 82); creating/
deleting a saved SmartAudience definition is narrower (ADMIN/MARKETING), matching
this codebase's convention of gating a persistent segmentation asset a notch
tighter than merely viewing what it contains.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING
from core.smart_audiences import (
    FIELD_CATALOG,
    OPERATORS,
    list_presets,
    preview_preset,
    preview_conditions,
    create_audience,
    delete_audience,
    list_audiences,
    evaluate_audience,
)


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING)
_MUTATE_ROLES = (ADMIN, MARKETING)

_FORBIDDEN_VIEW = {"error": "You don't have access to Smart Audiences with your current role."}
_FORBIDDEN_MUTATE = {"error": "Only Admin or Marketing can create or delete saved Smart Audiences."}


def get_field_catalog_api(role):
    if role not in _VIEW_ROLES:
        return _FORBIDDEN_VIEW
    return {"fields": FIELD_CATALOG, "operators": OPERATORS}


def list_presets_api(role):
    if role not in _VIEW_ROLES:
        return _FORBIDDEN_VIEW
    return {"presets": list_presets()}


def preview_preset_api(role, preset_key, params=None):
    if role not in _VIEW_ROLES:
        return _FORBIDDEN_VIEW
    return preview_preset(preset_key, params)


def preview_conditions_api(role, conditions):
    if role not in _VIEW_ROLES:
        return _FORBIDDEN_VIEW
    return preview_conditions(conditions)


def create_audience_api(role, name, created_by, conditions=None, preset_key=None, preset_params=None, description=""):
    if role not in _MUTATE_ROLES:
        return _FORBIDDEN_MUTATE
    return create_audience(name, created_by, conditions, preset_key, preset_params, description)


def delete_audience_api(role, audience_id):
    if role not in _MUTATE_ROLES:
        return _FORBIDDEN_MUTATE
    return delete_audience(audience_id)


def list_audiences_api(role):
    if role not in _VIEW_ROLES:
        return _FORBIDDEN_VIEW
    return {
        "audiences": [
            {
                "id": a.id,
                "name": a.attributes.get("name"),
                "description": a.attributes.get("description"),
                "preset_key": a.attributes.get("preset_key"),
                "conditions": a.attributes.get("conditions"),
                "created_by": a.attributes.get("created_by"),
                "created_at": a.attributes.get("created_at"),
            }
            for a in list_audiences()
        ]
    }


def evaluate_audience_api(role, audience_id):
    if role not in _VIEW_ROLES:
        return _FORBIDDEN_VIEW
    return evaluate_audience(audience_id)
