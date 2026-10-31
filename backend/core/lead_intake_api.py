"""
Thin API-layer function for quick Lead intake (session 47). Any authenticated role can
log a walk-in/event lead -- same "any role creates" precedent as assets/campaigns/deals.
"""

from core.lead_intake import create_lead, VALID_SOURCES


def _serialize(entity):
    return {
        "id": entity.id,
        **entity.attributes,
    }


def create_lead_api(
    employee_id,
    first_name,
    last_name,
    source,
    phone=None,
    email=None,
    city=None,
    state=None,
    vin=None,
):

    if not first_name or not last_name:
        return {"error": "first_name and last_name are required"}

    if source not in VALID_SOURCES:
        return {"error": f"source must be one of {', '.join(VALID_SOURCES)}"}

    lead = create_lead(
        employee_id,
        first_name.strip(),
        last_name.strip(),
        source,
        phone,
        email,
        city,
        state,
        vin,
    )

    return _serialize(lead)
