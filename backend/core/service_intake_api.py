"""
Thin API-layer function for quick Service ticket intake (session 47). Any authenticated
role can log a service ticket -- same "any role creates" precedent as assets/campaigns/
deals.
"""

from core.service_intake import create_service_record, VALID_PAY_TYPES, VALID_STATUSES


def _serialize(entity):
    return {
        "id": entity.id,
        **entity.attributes,
    }


def create_service_record_api(
    employee_id,
    vin,
    description,
    pay_type,
    status="Completed",
    customer_id=None,
    mileage=None,
    cost=None,
    parts_cost=None,
    labor_hours=None,
):

    if not description or not description.strip():
        return {"error": "description is required"}

    if pay_type not in VALID_PAY_TYPES:
        return {"error": f"pay_type must be one of {', '.join(VALID_PAY_TYPES)}"}

    if status not in VALID_STATUSES:
        return {"error": f"status must be one of {', '.join(VALID_STATUSES)}"}

    record = create_service_record(
        employee_id,
        vin,
        description.strip(),
        pay_type,
        status,
        customer_id,
        mileage,
        cost,
        parts_cost,
        labor_hours,
    )

    return _serialize(record)
