"""
core/demo_drive.py -- Demo Drive (session 102 follow-up), the fourth of Sam's ~10
"completely missing" dealership workflows. A real test-drive log: which prospect drove
which vehicle, with which salesperson, driver's-license capture/verification, out/in
odometer, and a live start -> out -> returned lifecycle.

Distinct from core/appointments.py's Appointment on purpose. An Appointment is a
scheduled future slot on a calendar; a DemoDrive is the live event of a real vehicle
actually leaving the lot -- it carries a driver's-license capture (the real compliance
gate before keys ever change hands, per every dealership's insurance requirements) and
out/in odometer readings an Appointment has no place for. Same "ordinary entity in the
one graph, linked by plain attribute id" convention as core/field_notes.py /
core/lead_tasks.py / core/appointments.py / core/manager_to.py -- the DemoDrive stores
the Lead id it's about and the Vehicle id being driven, never a copied snapshot of
either.

Honest scope note: license "verification" here is a real captured flag a salesperson
sets after eyeballing the license -- there is no DMV/AAMVA license-validation API
connected in this sandbox, so it is not a real cryptographic/authoritative check, and
this module never pretends it is. It IS a real, enforced gate: a drive cannot be
started without it.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import DEMO_DRIVE, LEAD, CUSTOMER, VEHICLE, EMPLOYEE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

STATUSES = ["out", "returned", "cancelled"]
INTEREST_LEVELS = ["hot", "warm", "cold"]

_DRIVER_TYPES = (LEAD, CUSTOMER)


def _now():
    return datetime.now(timezone.utc)


def _now_iso():
    return _now().isoformat()


def _parse(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _minutes_between(start_iso, end_iso):
    start = _parse(start_iso)
    end = _parse(end_iso)
    if not start or not end:
        return None
    return round((end - start).total_seconds() / 60, 1)


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def start_demo_drive(linked_entity_id, vehicle_id, salesperson_id, license_number="",
                     license_verified=False, odometer_out=None, notes=""):
    """Logs a vehicle actually going out on a test drive right now (status "out").
    Requires a verified license -- the real, enforced compliance gate. Returns an
    error dict rather than raising so the API/UI layers can surface it cleanly, same
    convention as core/manager_to.py / core/up_system.py."""

    driver = ledger.get_entity(linked_entity_id)
    if not driver or driver.entity_type not in _DRIVER_TYPES:
        return {"error": f"'{linked_entity_id}' is not a Lead or Customer"}

    vehicle = ledger.get_entity(vehicle_id)
    if not vehicle or vehicle.entity_type != VEHICLE:
        return {"error": f"'{vehicle_id}' is not a Vehicle"}

    salesperson = ledger.get_entity(salesperson_id)
    if not salesperson or salesperson.entity_type != EMPLOYEE:
        return {"error": f"'{salesperson_id}' is not an Employee"}

    if not license_verified:
        return {"error": "Driver's license must be verified before a demo drive can start"}

    demo_id = id_generator.generate("DEMO")

    demo = Entity(
        id=demo_id,
        entity_type=DEMO_DRIVE,
        attributes={
            "linked_entity_id": linked_entity_id,
            "linked_entity_type": driver.entity_type,
            "vehicle_id": vehicle_id,
            "salesperson_id": salesperson_id,
            "license_number": license_number or "",
            "license_verified": bool(license_verified),
            "status": "out",
            "odometer_out": _to_int(odometer_out),
            "odometer_in": None,
            "miles_driven": None,
            "start_at": _now_iso(),
            "end_at": None,
            "duration_minutes": None,
            "interest_level": None,
            "notes": notes or "",
            "feedback": "",
        },
    )

    ledger.add_entity(demo)
    save_graph(GRAPH_PATH)

    return demo


def return_demo_drive(demo_id, odometer_in=None, interest_level=None, feedback=""):
    """Closes out a drive when the vehicle comes back (status "returned"). Computes
    real duration and, if both odometer readings are present, real miles driven --
    None where a reading is missing rather than a fabricated number."""

    demo = ledger.get_entity(demo_id)
    if not demo or demo.entity_type != DEMO_DRIVE:
        return {"error": "Demo drive not found"}

    if demo.attributes.get("status") != "out":
        return {"error": f"This demo drive is already '{demo.attributes.get('status')}'"}

    if interest_level and interest_level not in INTEREST_LEVELS:
        return {"error": f"interest_level must be one of {INTEREST_LEVELS}"}

    end_iso = _now_iso()
    odo_in = _to_int(odometer_in)
    odo_out = demo.attributes.get("odometer_out")

    demo.attributes["status"] = "returned"
    demo.attributes["odometer_in"] = odo_in
    demo.attributes["end_at"] = end_iso
    demo.attributes["duration_minutes"] = _minutes_between(demo.attributes.get("start_at"), end_iso)
    demo.attributes["interest_level"] = interest_level or None
    demo.attributes["feedback"] = feedback or ""

    if odo_in is not None and odo_out is not None and odo_in >= odo_out:
        demo.attributes["miles_driven"] = odo_in - odo_out

    save_graph(GRAPH_PATH)

    return demo


def cancel_demo_drive(demo_id):

    demo = ledger.get_entity(demo_id)
    if not demo or demo.entity_type != DEMO_DRIVE:
        return {"error": "Demo drive not found"}

    if demo.attributes.get("status") == "returned":
        return {"error": "A returned demo drive can't be cancelled"}

    demo.attributes["status"] = "cancelled"
    demo.attributes["end_at"] = _now_iso()

    save_graph(GRAPH_PATH)

    return demo


def list_demo_drives(status=None, salesperson_id=None, vehicle_id=None):

    demos = [e for e in ledger.get_all().values() if e.entity_type == DEMO_DRIVE]

    if status:
        demos = [d for d in demos if d.attributes.get("status") == status]

    if salesperson_id:
        demos = [d for d in demos if d.attributes.get("salesperson_id") == salesperson_id]

    if vehicle_id:
        demos = [d for d in demos if d.attributes.get("vehicle_id") == vehicle_id]

    demos.sort(key=lambda d: d.attributes.get("start_at") or "", reverse=True)

    return demos


def list_active_demo_drives():
    """Vehicles currently off the lot on a test drive (status "out") -- the real
    "keys are out right now" board a sales desk actually watches, sorted longest-out
    first (a car gone too long is the thing a manager needs to notice)."""

    active = list_demo_drives(status="out")
    active.sort(key=lambda d: d.attributes.get("start_at") or "")

    return active


def get_stats():
    """Real numbers off real records -- counts by status, license-verification rate,
    and average duration/miles over returned drives. Empty/None where there's no
    sample yet, never a fabricated figure."""

    all_demos = list_demo_drives()

    if not all_demos:
        return {
            "total": 0,
            "active": 0,
            "returned": 0,
            "cancelled": 0,
            "license_verified_pct": None,
            "avg_duration_minutes": None,
            "avg_miles_driven": None,
        }

    returned = [d for d in all_demos if d.attributes.get("status") == "returned"]
    durations = [d.attributes.get("duration_minutes") for d in returned if d.attributes.get("duration_minutes") is not None]
    miles = [d.attributes.get("miles_driven") for d in returned if d.attributes.get("miles_driven") is not None]
    verified = sum(1 for d in all_demos if d.attributes.get("license_verified"))

    return {
        "total": len(all_demos),
        "active": sum(1 for d in all_demos if d.attributes.get("status") == "out"),
        "returned": len(returned),
        "cancelled": sum(1 for d in all_demos if d.attributes.get("status") == "cancelled"),
        "license_verified_pct": round(100 * verified / len(all_demos), 1),
        "avg_duration_minutes": round(sum(durations) / len(durations), 1) if durations else None,
        "avg_miles_driven": round(sum(miles) / len(miles), 1) if miles else None,
    }
