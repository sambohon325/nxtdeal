"""
core/lot_control.py -- Inventory department's "Lot Management" item
(Inventory rebuild, fifth slice). inventory.pdf's own framing: Vehicle
Locations, Lot Map, Key Management, Damage Reports, and Showroom
Assignments. Vehicle Locations (by-lot counts) and a real ownership-
integrity check already existed via core/workflow_tab_data.py's
inventory_lot_audit() (session 63) -- this module is the real ACTION layer
on top of that read-only view: a granular Lot Map (row/space position, not
just which lot), Key Management, Damage Reports, and Showroom Assignments.

Unlike Pricing/Acquisitions (SIMULATED, since real market/competitor data
genuinely doesn't exist anywhere this system could obtain it), these four
gaps are internal tracking capabilities this codebase simply hadn't built
yet -- there's no reason to simulate a key-checkout log or a damage report
when the real thing is just as easy to build. Built as REAL features here,
matching this codebase's established default: simulate only a genuine
external-world gap, build everything else for real.

Same additive-attribute-on-Vehicle convention as core/vehicle_lifecycle.py's
lifecycle_status/recon_checklist/vendor_assignments for lot_position/
key_status/showroom_assignment/scan_log (a vehicle has exactly one current
value for each, plus an append-only log/history where relevant -- key_log
and scan_log). Damage Reports are the one genuinely new first-class entity
here (DamageReport, core/entity_types.py) since multiple reports can exist
per vehicle over time, each with its own severity/status/resolution
lifecycle -- same reasoning core/operations_tasks.py's OperationsTask used
for the same distinction from an additive attribute.

Geofencing remains an honest not_yet_tracked gap even under the new
simulate-data policy -- a simulated GPS coordinate with no real map/geofence
rendering behind it would be actively misleading (implying a location
capability this system doesn't have), not a useful stand-in the way a
simulated market price is. QR/check-in scan logging IS real, even though no
actual scanning hardware is integrated -- the log entry itself is real,
whether the trigger is a hardware scan or a manual "log a scan" action.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import VEHICLE, DAMAGE_REPORT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.workflow_tab_data import _unsold_vehicles

KEY_STATUSES = ("on_lot", "checked_out", "missing")
DAMAGE_SEVERITIES = ("minor", "moderate", "severe")
DAMAGE_STATUSES = ("open", "in_repair", "resolved")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_vehicle(vehicle_id):
    v = ledger.get_entity(vehicle_id)
    if not v or v.entity_type != VEHICLE:
        return None
    return v


def _vehicle_brief(v):
    return {
        "vehicle_id": v.id,
        "vin": v.attributes.get("VIN"),
        "stock_number": v.attributes.get("StockNumber"),
        "year": v.attributes.get("Year"),
        "make": v.attributes.get("Make"),
        "model": v.attributes.get("Model"),
        "lot": v.attributes.get("Lot"),
    }


# --- Lot Position (the real Lot Map) ---

def set_lot_position(vehicle_id, updated_by, row=None, space=None, section=None, notes=""):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    position = {
        "row": row, "space": space, "section": section, "notes": notes,
        "updated_by": updated_by, "updated_at": _now(),
    }
    v.attributes["lot_position"] = position
    save_graph(GRAPH_PATH)
    return {"vehicle_id": vehicle_id, "lot_position": position}


def get_lot_position(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}
    return {"vehicle_id": vehicle_id, "lot_position": v.attributes.get("lot_position")}


def get_lot_map():
    """Real per-lot grouping enriched with each unsold vehicle's actual
    row/space position (or an honest 'unpositioned' if nobody's logged one
    yet) -- the same 'unsold_by_lot' population
    core/workflow_tab_data.py's inventory_lot_audit() already established,
    now with a real granular position attached per vehicle."""
    unsold = _unsold_vehicles()
    by_lot = {}
    for v in unsold:
        lot = v.attributes.get("Lot") or "Unknown"
        by_lot.setdefault(lot, []).append({
            **_vehicle_brief(v),
            "lot_position": v.attributes.get("lot_position"),
        })
    return {
        "by_lot": by_lot,
        "total_unsold": len(unsold),
        "positioned_count": sum(1 for v in unsold if v.attributes.get("lot_position")),
        "unpositioned_count": sum(1 for v in unsold if not v.attributes.get("lot_position")),
    }


# --- Key Management ---

def checkout_key(vehicle_id, holder, updated_by, notes=""):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    current = v.attributes.get("key_status") or {}
    if current.get("status") == "checked_out":
        return {"error": f"Key for '{vehicle_id}' is already checked out to {current.get('holder')}"}

    entry = {
        "action": "checked_out", "holder": holder, "notes": notes,
        "updated_by": updated_by, "at": _now(),
    }
    log = v.attributes.get("key_log") or []
    log.append(entry)

    v.attributes["key_status"] = {"status": "checked_out", "holder": holder, "checked_out_at": entry["at"]}
    v.attributes["key_log"] = log
    save_graph(GRAPH_PATH)
    return {"vehicle_id": vehicle_id, "key_status": v.attributes["key_status"], "log": log}


def checkin_key(vehicle_id, updated_by, notes=""):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    current = v.attributes.get("key_status") or {}
    if current.get("status") not in ("checked_out", "missing"):
        return {"error": f"Key for '{vehicle_id}' is not currently checked out or missing"}

    entry = {
        "action": "checked_in", "holder": current.get("holder"), "notes": notes,
        "previous_status": current.get("status"),
        "updated_by": updated_by, "at": _now(),
    }
    log = v.attributes.get("key_log") or []
    log.append(entry)

    v.attributes["key_status"] = {"status": "on_lot", "holder": None, "checked_in_at": entry["at"]}
    v.attributes["key_log"] = log
    save_graph(GRAPH_PATH)
    return {"vehicle_id": vehicle_id, "key_status": v.attributes["key_status"], "log": log}


def report_key_missing(vehicle_id, updated_by, notes=""):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    entry = {"action": "reported_missing", "notes": notes, "updated_by": updated_by, "at": _now()}
    log = v.attributes.get("key_log") or []
    log.append(entry)

    v.attributes["key_status"] = {"status": "missing", "holder": None, "reported_at": entry["at"]}
    v.attributes["key_log"] = log
    save_graph(GRAPH_PATH)
    return {"vehicle_id": vehicle_id, "key_status": v.attributes["key_status"], "log": log}


def get_key_status(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}
    return {
        "vehicle_id": vehicle_id,
        "key_status": v.attributes.get("key_status") or {"status": "on_lot", "holder": None},
        "log": v.attributes.get("key_log") or [],
    }


def get_key_board():
    """Real fleet-wide key status board -- who has which set of keys right
    now, and which are reported missing."""
    unsold = _unsold_vehicles()
    checked_out = []
    missing = []
    for v in unsold:
        status = v.attributes.get("key_status") or {}
        if status.get("status") == "checked_out":
            checked_out.append({**_vehicle_brief(v), "key_status": status})
        elif status.get("status") == "missing":
            missing.append({**_vehicle_brief(v), "key_status": status})
    return {
        "checked_out": checked_out,
        "missing": missing,
        "on_lot_count": len(unsold) - len(checked_out) - len(missing),
    }


# --- Damage Reports ---

def report_damage(vehicle_id, severity, description, reported_by, estimated_cost=None):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    if severity not in DAMAGE_SEVERITIES:
        return {"error": f"severity must be one of {DAMAGE_SEVERITIES}"}

    report_id = id_generator.generate("DMG")
    entity = Entity(
        id=report_id,
        entity_type=DAMAGE_REPORT,
        attributes={
            "vehicle_id": vehicle_id,
            "severity": severity,
            "description": description,
            "estimated_cost": estimated_cost,
            "status": "open",
            "reported_by": reported_by,
            "reported_at": _now(),
            "updated_by": None,
            "updated_at": None,
            "resolved_by": None,
            "resolved_at": None,
            "resolution_notes": "",
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def update_damage_status(report_id, new_status, updated_by, resolution_notes=""):
    entity = ledger.get_entity(report_id)
    if not entity or entity.entity_type != DAMAGE_REPORT:
        return {"error": f"Damage report '{report_id}' not found"}
    if new_status not in DAMAGE_STATUSES:
        return {"error": f"new_status must be one of {DAMAGE_STATUSES}"}
    if entity.attributes.get("status") == "resolved":
        return {"error": f"Damage report '{report_id}' is already resolved"}

    entity.attributes["status"] = new_status
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()

    if new_status == "resolved":
        entity.attributes["resolved_by"] = updated_by
        entity.attributes["resolved_at"] = _now()
        entity.attributes["resolution_notes"] = resolution_notes

    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def list_damage_reports(vehicle_id=None, status=None):
    reports = [e for e in ledger.get_all().values() if e.entity_type == DAMAGE_REPORT]
    if vehicle_id:
        reports = [r for r in reports if r.attributes.get("vehicle_id") == vehicle_id]
    if status:
        reports = [r for r in reports if r.attributes.get("status") == status]
    reports.sort(key=lambda r: r.attributes.get("reported_at") or "", reverse=True)
    return {"count": len(reports), "reports": [{"id": r.id, **r.attributes} for r in reports]}


# --- Showroom Assignment ---

def assign_showroom(vehicle_id, assigned_by, notes=""):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    assignment = {"assigned": True, "assigned_by": assigned_by, "assigned_at": _now(), "notes": notes}
    v.attributes["showroom_assignment"] = assignment
    save_graph(GRAPH_PATH)
    return {"vehicle_id": vehicle_id, "showroom_assignment": assignment}


def remove_showroom_assignment(vehicle_id, updated_by):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    v.attributes["showroom_assignment"] = {"assigned": False, "removed_by": updated_by, "removed_at": _now()}
    save_graph(GRAPH_PATH)
    return {"vehicle_id": vehicle_id, "showroom_assignment": v.attributes["showroom_assignment"]}


def get_showroom_board():
    unsold = _unsold_vehicles()
    assigned = [
        {**_vehicle_brief(v), "showroom_assignment": v.attributes.get("showroom_assignment")}
        for v in unsold
        if (v.attributes.get("showroom_assignment") or {}).get("assigned")
    ]
    return {"count": len(assigned), "vehicles": assigned}


# --- Check-In / QR Scans ---

def log_scan(vehicle_id, scanned_by, location_note=""):
    """A real, timestamped check-in event -- whether the trigger is a manual
    'log a scan' button or, in a future integration, real QR/barcode
    hardware. No actual scanning hardware is integrated in this system yet,
    but the LOG ITSELF is real, not a simulated figure."""
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    entry = {"scanned_by": scanned_by, "location_note": location_note, "at": _now()}
    log = v.attributes.get("scan_log") or []
    log.append(entry)
    v.attributes["scan_log"] = log
    save_graph(GRAPH_PATH)
    return {"vehicle_id": vehicle_id, "scan_log": log}


def get_scan_log(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}
    return {"vehicle_id": vehicle_id, "scan_log": v.attributes.get("scan_log") or []}


# --- Composed view ---

def get_lot_control_view(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    return {
        "vehicle": _vehicle_brief(v),
        "lot_position": v.attributes.get("lot_position"),
        "key_status": v.attributes.get("key_status") or {"status": "on_lot", "holder": None},
        "key_log": v.attributes.get("key_log") or [],
        "damage_reports": list_damage_reports(vehicle_id=vehicle_id)["reports"],
        "showroom_assignment": v.attributes.get("showroom_assignment"),
        "scan_log": v.attributes.get("scan_log") or [],
    }
