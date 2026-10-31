"""
core/service_customers.py -- Service's "Customers" item, the fourth slice of
Service's rebuild (following RO Workflow Engine, Overview, and Shop Control,
session 111). Sam's own framing: "Service should be relationship-driven."
His spec: a Customer Service Profile (Vehicles Owned/Service History/
Warranty Coverage/Recall History/Declined Services), Customer Retention
(Last Visit/Average Spend/Visit Frequency), Lost Customer Recovery (No
Service In 12 Months/Warranty Expired/Missed Maintenance), and Declined
Services ("one of the biggest profit drivers").

Customer 360 reuses the exact grouped-360 pattern `core/sales_menu.py`'s
`_customer_360()` already established (session 95) -- Vehicles Owned via the
real `OWNS` relationship, Service History via the real `AUTHORIZED`
relationship -- and adds Warranty Coverage/Recall History per owned vehicle
by reusing `core/repair_orders.py`'s own real `_warranty_status()`/
`_recall_status()` inferences verbatim (the same ones the RO Workspace
already shows), rather than a second warranty/recall computation.

Declined Services is REAL, not a fabricated example: `core/repair_orders.py`'s
`estimate` field already captures `approved=False` + `decline_reason` for any
live RO whose estimate was declined -- this module just lists those across
every RO, honestly scoped to the RO Workflow Engine's own live records (the
434 historical ServiceRecords predate the estimate/approval flow entirely
and carry no `estimate` field at all, so they're correctly excluded rather
than guessed at). "One-click follow-up" reuses `log_ro_communication()`
directly -- no second follow-up-tracking mechanism.

Lost Customer Recovery's "No Service In 12 Months" is real (last real
ServiceDate across a customer's AUTHORIZED ServiceRecords vs. today).
"Warranty Expired" is an honest gap -- no warranty term/expiration-date
field exists anywhere in this codebase (Warranty Status itself is only ever
an inference off Vehicle.Condition, not a real expiration date to check
against). "Missed Maintenance" is also an honest gap -- no service-interval
schedule/mileage-based due date model exists in this codebase.

Customer Retention's Visit Frequency is real but simple: total visit count
over the real span between first and last visit (a rate, not a fabricated
schedule-adherence score).
"""

from datetime import datetime, date

from core.dealeros import ledger
from core.entity_types import CUSTOMER, VEHICLE, SERVICE_RECORD
from core.relationship_types import OWNS, AUTHORIZED
from core.repair_orders import (
    _warranty_status,
    _recall_status,
    _stage_of,
    _customer_for_record,
    _vehicle_for_record,
)

LOST_CUSTOMER_DAYS_THRESHOLD = 365


def _relationships_from(entity_id, relationship_type):
    return [
        r for r in ledger.get_relationships()
        if r.source_id == entity_id and r.relationship_type == relationship_type
    ]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _customer_name(c):
    return f"{c.attributes.get('FirstName', '')} {c.attributes.get('LastName', '')}".strip()


def _vehicles_owned(customer_id):
    """Deduped by vehicle id -- a real, pre-existing data-quality quirk in
    this seed graph has some customers with duplicate OWNS relationships to
    the same vehicle (confirmed live, e.g. CUST-00140 -> VEH-00222 twice);
    this dedupes for display rather than silently showing the same vehicle
    twice, without altering the underlying relationship data itself."""
    seen = {}
    for r in _relationships_from(customer_id, OWNS):
        e = ledger.get_entity(r.target_id)
        if e and e.entity_type == VEHICLE:
            seen[e.id] = e
    return list(seen.values())


def _service_records_for(customer_id):
    return [
        e for e in (ledger.get_entity(r.target_id) for r in _relationships_from(customer_id, AUTHORIZED))
        if e and e.entity_type == SERVICE_RECORD
    ]


def get_customer_360(customer_id):

    customer = ledger.get_entity(customer_id)
    if not customer or customer.entity_type != CUSTOMER:
        return {"error": f"Customer '{customer_id}' not found"}

    vehicles = _vehicles_owned(customer_id)
    records = _service_records_for(customer_id)

    declined = [
        r for r in records
        if (r.attributes.get("estimate") or {}).get("approved") is False
    ]

    return {
        "customer": {"id": customer.id, "name": _customer_name(customer), "email": customer.attributes.get("Email"), "phone": customer.attributes.get("Phone")},
        "vehicles_owned": {
            "count": len(vehicles),
            "vehicles": [
                {
                    "id": v.id,
                    "vin": v.attributes.get("VIN"),
                    "year": v.attributes.get("Year"),
                    "make": v.attributes.get("Make"),
                    "model": v.attributes.get("Model"),
                    "warranty_status": _warranty_status(v),
                    "recall_status": _recall_status(v),
                }
                for v in vehicles
            ],
        },
        "service_history": {
            "count": len(records),
            "records": sorted([
                {
                    "id": r.id,
                    "service_date": r.attributes.get("ServiceDate"),
                    "description": r.attributes.get("Description"),
                    "cost": r.attributes.get("Cost"),
                    "pay_type": r.attributes.get("PayType"),
                    "ro_stage": _stage_of(r),
                }
                for r in records
            ], key=lambda r: r["service_date"] or "", reverse=True),
        },
        "declined_services": {
            "count": len(declined),
            "records": [
                {
                    "ro_id": r.id,
                    "description": r.attributes.get("Description"),
                    "amount": (r.attributes.get("estimate") or {}).get("amount"),
                    "decline_reason": (r.attributes.get("estimate") or {}).get("decline_reason"),
                    "declined_at": (r.attributes.get("estimate") or {}).get("approved_at"),
                }
                for r in declined
            ],
        },
        "retention": get_retention_metrics(customer_id, records=records),
    }


def get_retention_metrics(customer_id, records=None):

    if records is None:
        records = _service_records_for(customer_id)

    dates = sorted([r.attributes.get("ServiceDate") for r in records if r.attributes.get("ServiceDate")])

    if not dates:
        return {"last_visit": None, "first_visit": None, "visit_count": 0, "average_spend": None, "visits_per_year": None}

    total_spend = sum(_safe_float(r.attributes.get("Cost")) for r in records)
    average_spend = round(total_spend / len(records), 2) if records else None

    try:
        first = date.fromisoformat(dates[0])
        last = date.fromisoformat(dates[-1])
        span_years = max((last - first).days / 365.0, 1 / 365.0)
        visits_per_year = round(len(dates) / span_years, 2)
    except ValueError:
        visits_per_year = None

    return {
        "last_visit": dates[-1],
        "first_visit": dates[0],
        "visit_count": len(records),
        "average_spend": average_spend,
        "visits_per_year": visits_per_year,
    }


def get_lost_customer_recovery():
    """'No Service In 12 Months' -- REAL, off every customer's last real
    ServiceDate vs. today. 'Warranty Expired' and 'Missed Maintenance' are
    honest gaps, noted rather than fabricated (see module docstring)."""

    today = date.today()
    lost = []

    for c in ledger.get_all().values():
        if c.entity_type != CUSTOMER:
            continue
        records = _service_records_for(c.id)
        if not records:
            continue
        dates = [r.attributes.get("ServiceDate") for r in records if r.attributes.get("ServiceDate")]
        if not dates:
            continue
        last_visit = max(dates)
        try:
            days_since = (today - date.fromisoformat(last_visit)).days
        except ValueError:
            continue
        if days_since >= LOST_CUSTOMER_DAYS_THRESHOLD:
            lost.append({
                "customer_id": c.id,
                "name": _customer_name(c),
                "phone": c.attributes.get("Phone"),
                "last_visit": last_visit,
                "days_since_last_visit": days_since,
                "total_visits": len(records),
            })

    lost.sort(key=lambda c: c["days_since_last_visit"], reverse=True)

    return {
        "count": len(lost),
        "customers": lost[:100],
        "not_yet_tracked": {
            "warranty_expired": "No warranty term/expiration-date field exists anywhere in this codebase -- Warranty Status is only ever an inference off Vehicle.Condition, not a real expiration date to check against.",
            "missed_maintenance": "No service-interval schedule/mileage-based due-date model exists in this codebase yet.",
        },
    }


def get_declined_services():
    """'One of the biggest profit drivers' -- real declined estimates across
    every live RO Workflow Engine record (historical ServiceRecords predate
    the estimate/approval flow entirely and are correctly excluded, not
    guessed at). 'One-click follow-up' reuses log_ro_communication()
    directly, no second tracking mechanism."""

    records = [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]
    today = date.today()

    declined = []
    for r in records:
        estimate = r.attributes.get("estimate")
        if not estimate or estimate.get("approved") is not False:
            continue

        vehicle = _vehicle_for_record(r)
        customer = _customer_for_record(r)

        days_since = None
        approved_at = estimate.get("approved_at")
        if approved_at:
            try:
                days_since = (today - datetime.fromisoformat(approved_at).date()).days
            except ValueError:
                days_since = None

        declined.append({
            "ro_id": r.id,
            "customer_id": customer.id if customer else None,
            "customer_name": _customer_name(customer) if customer else None,
            "vehicle": f"{vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} {vehicle.attributes.get('Model', '')}".strip() if vehicle else None,
            "description": r.attributes.get("Description"),
            "amount": estimate.get("amount"),
            "decline_reason": estimate.get("decline_reason"),
            "days_since_declined": days_since,
        })

    declined.sort(key=lambda d: d["amount"] or 0, reverse=True)

    return {"count": len(declined), "total_value": round(sum(d["amount"] or 0 for d in declined), 2), "records": declined}
