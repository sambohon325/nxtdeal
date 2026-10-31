"""Thin passthrough matching this codebase's "*_api.py is what api/app.py imports"
convention -- core/lead_record.py's get_lead_record() already takes `role` as its
first argument and does its own access check via core/ai_tools.py's
get_entity_by_id(), so there's no additional ACL logic to add here."""

from core.lead_record import get_lead_record


def get_lead_record_api(role, lead_id):
    return get_lead_record(role, lead_id)
