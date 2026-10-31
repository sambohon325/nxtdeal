"""
core/vendor_management.py -- Administration's "Vendor Management" item
(Administration Control Center rebuild, continued). VENDOR has been a defined
entity type in core/entity_types.py since early sessions but was never once
instantiated by any importer or seed script -- core/administration_menu.py's
vendors() function has been reusing real Connection records (core/
data_connections.py) as an honest proxy for "active vendors" since session 65.

This module builds the real thing: a genuine Vendor record with contact info, a
contract term (start/end date, auto-renew flag), a monthly cost, and a category
(software/parts-supplier/service-provider/marketing/other). Closes most of
vendors()'s old not_yet_tracked list for real (contracts, renewal_dates,
monthly_costs) the moment an admin actually enters one -- usage_analysis (per-
seat usage tracking) stays an honest gap, since no such tracking model exists
anywhere in this codebase and nothing here would make one real.

Same additive-attribute-on-a-first-class-entity convention as every other
department module in this codebase -- a Vendor is its own record (not a dict on
Connection), since a vendor relationship (contract, contact, cost) is a
genuinely different real-world object from a technical data Connection, even
though today's honest proxy conflated the two.
"""

from datetime import datetime, timezone, date

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import VENDOR
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

VENDOR_CATEGORIES = ("software", "parts_supplier", "service_provider", "marketing", "other")
VENDOR_STATUSES = ("active", "inactive", "under_review")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_vendor(vendor_id):
    v = ledger.get_entity(vendor_id)
    if not v or v.entity_type != VENDOR:
        return None
    return v


def _serialize(v):
    a = v.attributes
    renewal = a.get("contract_end_date")
    days_to_renewal = None
    if renewal:
        try:
            days_to_renewal = (date.fromisoformat(renewal) - date.today()).days
        except ValueError:
            days_to_renewal = None
    return {"id": v.id, **a, "days_to_renewal": days_to_renewal}


def create_vendor(
    name,
    category,
    created_by,
    contact_name="",
    contact_email="",
    contact_phone="",
    monthly_cost=None,
    contract_start_date=None,
    contract_end_date=None,
    auto_renew=False,
    notes="",
):
    if category not in VENDOR_CATEGORIES:
        return {"error": f"category must be one of {VENDOR_CATEGORIES}"}

    if not name or not name.strip():
        return {"error": "A vendor name is required"}

    vendor_id = id_generator.generate("VNDR")
    entity = Entity(
        id=vendor_id,
        entity_type=VENDOR,
        attributes={
            "name": name.strip(),
            "category": category,
            "status": "active",
            "contact_name": contact_name,
            "contact_email": contact_email,
            "contact_phone": contact_phone,
            "monthly_cost": monthly_cost,
            "contract_start_date": contract_start_date,
            "contract_end_date": contract_end_date,
            "auto_renew": bool(auto_renew),
            "notes": notes,
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return _serialize(entity)


def update_vendor(vendor_id, updated_by, **fields):
    v = _get_vendor(vendor_id)
    if not v:
        return {"error": f"Vendor '{vendor_id}' not found"}

    editable = (
        "name", "category", "contact_name", "contact_email", "contact_phone",
        "monthly_cost", "contract_start_date", "contract_end_date", "auto_renew", "notes",
    )
    for key, value in fields.items():
        if key in editable and value is not None:
            if key == "category" and value not in VENDOR_CATEGORIES:
                return {"error": f"category must be one of {VENDOR_CATEGORIES}"}
            v.attributes[key] = value

    v.attributes["updated_at"] = _now()
    v.attributes["updated_by"] = updated_by
    save_graph(GRAPH_PATH)
    return _serialize(v)


def set_vendor_status(vendor_id, status, updated_by):
    v = _get_vendor(vendor_id)
    if not v:
        return {"error": f"Vendor '{vendor_id}' not found"}
    if status not in VENDOR_STATUSES:
        return {"error": f"status must be one of {VENDOR_STATUSES}"}

    v.attributes["status"] = status
    v.attributes["updated_at"] = _now()
    v.attributes["updated_by"] = updated_by
    save_graph(GRAPH_PATH)
    return _serialize(v)


def get_vendor(vendor_id):
    v = _get_vendor(vendor_id)
    if not v:
        return {"error": f"Vendor '{vendor_id}' not found"}
    return _serialize(v)


def list_vendors(category=None, status=None):
    vendors = [e for e in ledger.get_all().values() if e.entity_type == VENDOR]
    if category:
        vendors = [v for v in vendors if v.attributes.get("category") == category]
    if status:
        vendors = [v for v in vendors if v.attributes.get("status") == status]
    vendors.sort(key=lambda v: v.attributes.get("name") or "")
    return [_serialize(v) for v in vendors]


def get_vendor_dashboard():
    """Real aggregate: total monthly spend, upcoming renewals (next 60 days),
    and a category breakdown -- the actual data vendors()'s old not_yet_tracked
    list said didn't exist anywhere."""

    vendors = [e for e in ledger.get_all().values() if e.entity_type == VENDOR]
    serialized = [_serialize(v) for v in vendors]

    total_monthly_cost = sum(v.get("monthly_cost") or 0 for v in serialized if v.get("status") == "active")

    upcoming_renewals = [
        v for v in serialized
        if v.get("days_to_renewal") is not None and 0 <= v["days_to_renewal"] <= 60
    ]
    upcoming_renewals.sort(key=lambda v: v["days_to_renewal"])

    by_category = {}
    for v in serialized:
        cat = v.get("category", "other")
        by_category.setdefault(cat, {"count": 0, "monthly_cost": 0})
        by_category[cat]["count"] += 1
        by_category[cat]["monthly_cost"] += v.get("monthly_cost") or 0

    return {
        "total_vendors": len(serialized),
        "active_vendors": len([v for v in serialized if v.get("status") == "active"]),
        "total_monthly_cost": round(total_monthly_cost, 2),
        "upcoming_renewals": upcoming_renewals,
        "by_category": by_category,
        "vendors": serialized,
        "not_yet_tracked": {
            "usage_analysis": "No per-seat/per-license usage-tracking data model exists anywhere in this codebase.",
        },
    }
