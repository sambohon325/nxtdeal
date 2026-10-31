"""
Thin API-layer functions for the generic FieldNote quick-log (session 47) -- same
"no service layer indirection" convention as every other `*_api.py` module. Any
authenticated role can log a field note (matches the "any role creates" precedent set
by assets/campaigns/deals/websites) -- there's no approval step to gate.
"""

from core.field_notes import create_field_note, list_field_notes, CATEGORIES


def _serialize(entity):
    return {
        "id": entity.id,
        **entity.attributes,
    }


def create_field_note_api(employee_id, department, category, body, linked_entity_id=None):

    if not department:
        return {"error": "department is required"}

    if not body or not body.strip():
        return {"error": "body is required"}

    if category not in CATEGORIES:
        return {"error": f"category must be one of {', '.join(CATEGORIES)}"}

    entity = create_field_note(department, category, body.strip(), employee_id, linked_entity_id)

    return _serialize(entity)


def list_field_notes_api(department=None, limit=50, linked_entity_id=None):

    return [_serialize(n) for n in list_field_notes(department, limit, linked_entity_id)]
