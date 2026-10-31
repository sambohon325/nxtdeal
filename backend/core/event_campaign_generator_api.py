"""
Thin ACL layer for core/event_campaign_generator.py, imported directly into
api/app.py's route handlers. Same role split as core/dealership_events_api.py/
core/event_planning_api.py -- generating a draft is view-tier (any authenticated
role can preview copy), but actually persisting a real Campaign+EmailTemplate is
scoped to ADMIN/MARKETING/SALES.
"""

from core.event_campaign_generator import (
    generate_event_campaign_draft,
    create_event_campaign,
    list_campaigns_for_event,
)
from core.permissions import ADMIN, MARKETING, SALES


def _can_act(role):
    return role in (ADMIN, MARKETING, SALES)


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def generate_event_campaign_draft_api(role, event_id, channel="email", tone="friendly and professional"):
    return generate_event_campaign_draft(event_id, channel, tone)


def create_event_campaign_api(role, employee_id, event_id, channel, tone="friendly and professional"):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can generate a real event campaign"}

    result = create_event_campaign(event_id, channel, employee_id, tone)

    if isinstance(result, dict) and "error" in result:
        return result

    return {
        "campaign": _serialize(result["campaign"]),
        "template": _serialize(result["template"]),
    }


def list_campaigns_for_event_api(role, event_id):
    return [_serialize(c) for c in list_campaigns_for_event(event_id)]
