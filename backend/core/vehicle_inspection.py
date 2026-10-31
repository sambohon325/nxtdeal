"""
core/vehicle_inspection.py -- Digital Vehicle Inspection (DVI), the first of
Sam's "FEATURES COMPLETELY MISSING" list to get built, following the same
"build the flagship/most-referenced-elsewhere piece first" precedent as
Sales' Deal Desk, Operations' Vehicle Lifecycle, Inventory's Master Vehicle
Workspace, and Service's own RO Workflow Engine.

DVI is deliberately NOT a new standalone entity or a parallel workflow --
it's real additive state on the SAME ServiceRecord the RO Workflow Engine
(core/repair_orders.py) already manages, tied specifically to that engine's
existing "Inspection" stage (one of the real 10 stages: Check-In -> RO
Written -> Inspection -> Estimate -> ...). Same additive-attribute-dict
convention as that module's own `estimate`/`qc_checklist`/`parts_requests`.

The real "tightly integrate" mechanism (Sam's own recurring language for
this kind of ask, echoed from Events/session 84 and Website/session 85):
`create_concerns_from_inspection()` turns flagged (yellow/red) inspection
items directly into real Concerns via `core/repair_orders.py`'s own
`add_concern()` -- so a technician's DVI findings flow straight into the
RO's existing Concerns -> Estimate -> Customer Approval pipeline, rather
than DVI being a disconnected report that someone has to manually
re-type into a concern.

A real DVI_CATEGORIES catalog (Tires/Brakes/Fluids/Battery/Belts & Hoses/
Lights/Wipers/Suspension) mirrors what every real dealership DVI tool
(Xtime, Tekion, etc.) actually inspects -- not exhaustive, but a genuine,
defensible starter set rather than a single freeform text field.

Scope note, stated plainly rather than silently expanded: this module does
NOT build a customer-facing shareable inspection report or approval flow --
that's Sam's own separately-named "Customer-Facing Approval Center" item,
still open. Photos are stored as plain image URLs on the inspection item
(same convention as `core/merchandising.py`'s image_library -- a URL, not a
real upload/CDN pipeline) rather than wiring a second Image-entity/
HAS_IMAGE relationship, since these photos are RO-scoped working notes for
a technician, not merchandising assets meant to be independently browsable.
"""

from urllib.parse import urlsplit

from core.dealeros import ledger
from core.entity_types import VEHICLE, SERVICE_RECORD
from core.repair_orders import _get_ro, _now, add_concern, get_ro_workspace
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

INSPECTION_STATUSES = ("not_inspected", "green", "yellow", "red")

DVI_CATEGORIES = {
    "tires": {"label": "Tires", "items": ["Tread Depth", "Tire Pressure", "Tire Condition / Sidewall"]},
    "brakes": {"label": "Brakes", "items": ["Front Pads", "Rear Pads", "Rotors", "Brake Fluid Level"]},
    "fluids": {"label": "Fluids", "items": ["Engine Oil", "Coolant", "Transmission Fluid", "Power Steering Fluid"]},
    "battery": {"label": "Battery", "items": ["Battery Health", "Terminals / Cables"]},
    "belts_hoses": {"label": "Belts & Hoses", "items": ["Serpentine Belt", "Hoses"]},
    "lights": {"label": "Lights", "items": ["Headlights", "Taillights", "Turn Signals / Brake Lights"]},
    "wipers": {"label": "Wipers", "items": ["Wiper Blades", "Washer Fluid"]},
    "suspension": {"label": "Suspension", "items": ["Shocks / Struts", "Alignment (visual)"]},
}


def _blank_items():
    items = {}
    for cat_key, cat in DVI_CATEGORIES.items():
        for item_name in cat["items"]:
            items[f"{cat_key}::{item_name}"] = {
                "category": cat_key,
                "item": item_name,
                "status": "not_inspected",
                "notes": "",
                "photo_urls": [],
                "concern_created": False,
                "updated_by": None,
                "updated_at": None,
            }
    return items


def _dvi_of(ro):
    dvi = ro.attributes.get("dvi")
    if not dvi:
        dvi = {"status": "not_started", "started_by": None, "started_at": None, "completed_by": None, "completed_at": None, "items": _blank_items()}
    return dvi


def _summary(items):
    counts = {"not_inspected": 0, "green": 0, "yellow": 0, "red": 0}
    for entry in items.values():
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return counts


def get_catalog():
    return {"categories": DVI_CATEGORIES, "statuses": list(INSPECTION_STATUSES)}


def start_inspection(ro_id, started_by):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    dvi = _dvi_of(ro)
    if dvi["status"] != "not_started":
        return {"error": f"Inspection already in '{dvi['status']}' status for this RO"}

    dvi["status"] = "in_progress"
    dvi["started_by"] = started_by
    dvi["started_at"] = _now()

    ro.attributes["dvi"] = dvi
    save_graph(GRAPH_PATH)

    return get_inspection(ro_id)


def update_inspection_item(ro_id, item_key, status, notes, updated_by):

    if status not in INSPECTION_STATUSES:
        return {"error": f"status must be one of {list(INSPECTION_STATUSES)}"}

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    dvi = _dvi_of(ro)
    if dvi["status"] == "not_started":
        return {"error": "Inspection must be started before updating an item"}
    if item_key not in dvi["items"]:
        return {"error": f"Unknown inspection item '{item_key}'"}

    entry = dvi["items"][item_key]
    entry["status"] = status
    entry["notes"] = notes or ""
    entry["updated_by"] = updated_by
    entry["updated_at"] = _now()

    ro.attributes["dvi"] = dvi
    save_graph(GRAPH_PATH)

    return get_inspection(ro_id)


def attach_inspection_photo(ro_id, item_key, image_url, uploaded_by, media_type="photo"):

    if media_type not in {"photo", "video"}:
        return {"error": "Choose photo or video media"}

    if not image_url or not image_url.strip():
        return {"error": "image_url is required"}

    image_url = image_url.strip()
    try:
        parsed = urlsplit(image_url)
        valid_url = (
            parsed.scheme in ("http", "https")
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not any(character.isspace() or ord(character) < 32 for character in image_url)
        )
        parsed.port  # Reject malformed port numbers as well as malformed hosts.
    except ValueError:
        valid_url = False
    if not valid_url:
        return {"error": "Enter a valid http:// or https:// photo URL"}

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    dvi = _dvi_of(ro)
    if item_key not in dvi["items"]:
        return {"error": f"Unknown inspection item '{item_key}'"}

    urls = dvi["items"][item_key].setdefault("video_urls" if media_type == "video" else "photo_urls", [])
    if image_url not in urls:
        urls.append(image_url)
    dvi["items"][item_key]["updated_by"] = uploaded_by
    dvi["items"][item_key]["updated_at"] = _now()

    ro.attributes["dvi"] = dvi
    save_graph(GRAPH_PATH)

    return get_inspection(ro_id)


def complete_inspection(ro_id, completed_by):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    dvi = _dvi_of(ro)
    if dvi["status"] == "not_started":
        return {"error": "Inspection has not been started yet"}
    if dvi["status"] == "completed":
        return {"error": "Inspection is already completed"}

    remaining = [k for k, v in dvi["items"].items() if v["status"] == "not_inspected"]
    if remaining:
        return {"error": f"{len(remaining)} inspection item(s) still not inspected -- every item must be set to green/yellow/red before completing"}

    dvi["status"] = "completed"
    dvi["completed_by"] = completed_by
    dvi["completed_at"] = _now()

    ro.attributes["dvi"] = dvi
    save_graph(GRAPH_PATH)

    return get_inspection(ro_id)


def get_inspection(ro_id):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    dvi = _dvi_of(ro)

    return {
        "ro_id": ro_id,
        "status": dvi["status"],
        "started_by": dvi["started_by"],
        "started_at": dvi["started_at"],
        "completed_by": dvi["completed_by"],
        "completed_at": dvi["completed_at"],
        "summary": _summary(dvi["items"]),
        "items": dvi["items"],
    }


def create_concerns_from_inspection(ro_id, item_keys, created_by):
    """The real tie-in: turns selected flagged (yellow/red) inspection items
    directly into real Concerns via core/repair_orders.py's own
    add_concern(), so DVI findings flow straight into the RO's existing
    Concerns -> Estimate -> Customer Approval pipeline instead of sitting in
    a disconnected report. Each converted item is marked concern_created so
    it isn't silently double-converted into two concerns later."""

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    dvi = _dvi_of(ro)

    if not item_keys:
        return {"error": "item_keys is required (at least one inspection item)"}

    created = []
    already_done = []
    invalid = []

    for item_key in item_keys:
        entry = dvi["items"].get(item_key)
        if not entry:
            invalid.append(item_key)
            continue
        if entry.get("concern_created"):
            already_done.append(item_key)
            continue
        if entry["status"] not in ("yellow", "red"):
            invalid.append(item_key)
            continue

        description = f"DVI finding — {DVI_CATEGORIES[entry['category']]['label']}: {entry['item']} ({entry['status'].upper()})"
        if entry.get("notes"):
            description += f" — {entry['notes']}"

        add_concern(ro_id, description, created_by)
        entry["concern_created"] = True
        created.append(item_key)

    ro.attributes["dvi"] = dvi
    save_graph(GRAPH_PATH)

    return {
        "ro_id": ro_id,
        "created_concerns_for": created,
        "already_had_concerns": already_done,
        "invalid_items": invalid,
        "workspace": get_ro_workspace(ro_id),
    }


def get_inspection_history_for_vehicle(vehicle_id_or_vin):
    """Cross-RO Vehicle Inspection History -- closes Sam's "Digital
    Inspections' remaining asks" gap: today, DVI data is only viewable
    inside one specific RO's own workspace modal, with no way to see a
    vehicle's full inspection trend across visits (e.g. "has this same
    tire-wear issue shown up before?"). A real, read-only composition over
    already-real per-RO DVI data -- no new entity type, no new mutation.
    Reuses the exact VIN-cross-reference pattern core/repair_orders.py's
    own _vehicle_for_record() already established, just run in the other
    direction (VIN -> every ServiceRecord, not ServiceRecord -> Vehicle).

    Accepts either a real Vehicle id (VEH-...) or a raw VIN string, since
    a caller may only have one or the other on hand."""

    vehicle = ledger.get_entity(vehicle_id_or_vin)
    if vehicle and vehicle.entity_type == VEHICLE:
        vin = vehicle.attributes.get("VIN")
    else:
        vehicle = None
        vin = vehicle_id_or_vin

    if not vin:
        return {"error": f"No VIN found for '{vehicle_id_or_vin}'"}

    records = []
    for r in ledger.get_all().values():
        if r.entity_type != SERVICE_RECORD or r.attributes.get("VIN") != vin:
            continue
        dvi = r.attributes.get("dvi")
        if not dvi or dvi.get("status") == "not_started":
            continue
        records.append((r, dvi))

    records.sort(key=lambda pair: pair[0].attributes.get("ServiceDate") or "", reverse=True)

    inspections = []
    finding_counts = {}
    finding_labels = {}

    for r, dvi in records:
        summary = _summary(dvi["items"])
        flagged = []
        for key, entry in dvi["items"].items():
            if entry["status"] in ("yellow", "red"):
                flagged.append({
                    "item_key": key,
                    "category": entry["category"],
                    "item": entry["item"],
                    "status": entry["status"],
                    "notes": entry["notes"],
                })
                fk = (entry["category"], entry["item"])
                finding_counts[fk] = finding_counts.get(fk, 0) + 1
                if entry["category"] in DVI_CATEGORIES:
                    finding_labels[fk] = f"{DVI_CATEGORIES[entry['category']]['label']}: {entry['item']}"
                else:
                    finding_labels[fk] = entry["item"]

        inspections.append({
            "ro_id": r.id,
            "service_date": r.attributes.get("ServiceDate"),
            "dvi_status": dvi["status"],
            "completed_at": dvi.get("completed_at"),
            "summary": summary,
            "flagged_items": flagged,
        })

    recurring_findings = [
        {
            "category": cat,
            "item": item,
            "label": finding_labels[(cat, item)],
            "occurrences": count,
        }
        for (cat, item), count in finding_counts.items()
        if count >= 2
    ]
    recurring_findings.sort(key=lambda f: f["occurrences"], reverse=True)

    return {
        "vehicle_id": vehicle.id if vehicle else None,
        "vin": vin,
        "inspection_count": len(inspections),
        "inspections": inspections,
        "recurring_findings": recurring_findings,
        "note": (
            "REAL -- composed directly from every completed/in-progress DVI "
            "recorded across this vehicle's real repair-order history "
            "(cross-referenced by VIN). 'recurring_findings' flags any "
            "inspection item marked yellow/red in 2 or more separate "
            "inspections -- a real, worth-a-closer-look signal, not a "
            "diagnosis or a prediction."
        ),
    }
