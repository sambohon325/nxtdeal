"""
core/device_management.py -- the fifth slice of Sam's Retail Automotive Lending
Platform expansion (2026-07-17), backing TWO Finance Top Menu items -- "GPS & Device
Management" and "Starter Interrupt Management" -- off ONE real entity,
InstalledDevice. Deliberate scoping decision, not an oversight: a GPS/starter-
interrupt unit is one real physical device installed on a financed vehicle with two
distinct operational capabilities (location tracking, starter disable/enable), not
two separate real-world objects -- building two parallel device registries would
duplicate the same install/remove lifecycle for no real reason. Each menu item gets
its own view function (gps_devices()/starter_interrupt() in core/finance_menu.py)
over this one engine, same "one engine, multiple lenses" precedent this codebase's
Sales Deal Desk / Operations Vehicle Lifecycle arcs already established internally.

GPS location telemetry is honestly SIMULATED -- no real GPS hardware or telematics
API (e.g. a Spireon/PassTime-style integration) is connected anywhere in this
sandbox. Deterministically seeded via hashlib.sha256 off the device's own id (plus a
coarse day-bucket for slow "movement" over time), same convention
core/pricing_desk.py/core/acquisitions.py already established, so a given device's
location reads consistently within a day rather than flipping on every call. Every
simulated location payload carries basis="simulated_gps_data" plus an explicit
disclaimer, never presented as real telemetry.

Starter Interrupt is the real, stored half: a starter-interrupt-capable device has a
real armed/disarmed state and a real enabled/disabled starter status, with a real,
enforced business rule -- disable_starter() refuses to run unless a warning has
already been recorded via send_warning() first. This isn't a specific cited statute
(no state-by-state starter-interrupt notice law is modeled here -- see
core/compliance_rules.py's NOT_LEGAL_ADVICE_NOTICE, reused directly on every
starter-interrupt response), just a real, honest consumer-protection-shaped gate
matching common BHPH industry practice, same "real business rule without
overclaiming a specific legal citation" discipline this codebase applies elsewhere.
Re-enabling never requires a warning -- that's a customer-favorable action.

One real per-loan constraint: only one ACTIVE device may be registered per loan at a
time (removed devices don't count), matching real BHPH practice of one tracked unit
per financed vehicle.
"""

import hashlib
from datetime import datetime, timezone, date, timedelta

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import INSTALLED_DEVICE, FINANCE_CONTRACT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.compliance_rules import NOT_LEGAL_ADVICE_NOTICE
from core.loan_servicing import (
    _get_loan, _safe_float, _today, _customer_brief, _vehicle_brief,
    _linked_customer_id, _linked_vehicle_id,
)

DEVICE_TYPES = ("gps_only", "gps_starter_interrupt")
DEVICE_STATUSES = ("active", "removed")
STARTER_STATUSES = ("enabled", "disabled")

SIMULATED_GPS_BASIS = "simulated_gps_data"
_DISCLAIMER_GPS = (
    "SIMULATED GPS location -- no real GPS hardware or telematics API is connected "
    "in this system yet. Deterministically generated from this device's own id plus "
    "the current day, so location reads consistently within a day rather than "
    "flipping on every call, not real vehicle telemetry."
)

# A plausible metro-area anchor point for simulated jitter -- not tied to any real
# dealership location, purely a believable center for demo coordinates.
_ANCHOR_LAT = 39.0997
_ANCHOR_LNG = -94.5786


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today_iso():
    return _today().isoformat()


def _seeded_float(seed_str, low, high):
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    span = high - low
    frac = (int(digest[:12], 16) % 10_000_000) / 10_000_000.0
    return round(low + frac * span, 6)


def _seeded_choice(seed_str, options):
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    return options[int(digest, 16) % len(options)]


def _all_devices():
    return [e for e in ledger.get_all().values() if e.entity_type == INSTALLED_DEVICE]


def _get_device(device_id):
    e = ledger.get_entity(device_id)
    if not e or e.entity_type != INSTALLED_DEVICE:
        return None
    return e


def _active_device_for_loan(loan_id):
    for d in _all_devices():
        if d.attributes.get("loan_id") == loan_id and d.attributes.get("status") == "active":
            return d
    return None


def _device_brief(device):
    return {
        "id": device.id,
        "loan_id": device.attributes.get("loan_id"),
        "device_type": device.attributes.get("device_type"),
        "serial_number": device.attributes.get("serial_number"),
        "status": device.attributes.get("status"),
        "starter_status": device.attributes.get("starter_status"),
        "starter_interrupt_armed": device.attributes.get("starter_interrupt_armed"),
        "install_date": device.attributes.get("install_date"),
        "last_warning_at": device.attributes.get("last_warning_at"),
    }


# ---------------------------------------------------------------------------
# Device registry
# ---------------------------------------------------------------------------

def register_device(loan_id, device_type, serial_number, by, install_date=None):
    if device_type not in DEVICE_TYPES:
        return {"error": f"device_type must be one of {DEVICE_TYPES}"}
    if not serial_number:
        return {"error": "serial_number is required"}

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    existing = _active_device_for_loan(loan_id)
    if existing:
        return {"error": f"Loan '{loan_id}' already has an active device ({existing.id}) -- remove it before registering a new one"}

    device_id = id_generator.generate("DEV")
    customer_id = _linked_customer_id(loan)
    vehicle_id = _linked_vehicle_id(loan)

    device = Entity(
        id=device_id,
        entity_type=INSTALLED_DEVICE,
        attributes={
            "loan_id": loan_id,
            "customer_id": customer_id,
            "vehicle_id": vehicle_id,
            "device_type": device_type,
            "serial_number": serial_number,
            "install_date": install_date or _today_iso(),
            "installed_by": by,
            "status": "active",
            "starter_interrupt_armed": False,
            "starter_status": "enabled" if device_type == "gps_starter_interrupt" else None,
            "last_warning_at": None,
            "last_warning_message": None,
            "last_warning_by": None,
            "command_history": [{"action": "registered", "by": by, "reason": "", "at": _now()}],
            "removed_at": None,
            "removed_by": None,
            "removed_reason": None,
        },
    )

    ledger.add_entity(device)
    save_graph(GRAPH_PATH)

    return device


def remove_device(device_id, by, reason=""):
    device = _get_device(device_id)
    if not device:
        return {"error": f"Device '{device_id}' not found"}
    if device.attributes.get("status") == "removed":
        return {"error": "Device is already removed"}

    device.attributes["status"] = "removed"
    device.attributes["removed_at"] = _now()
    device.attributes["removed_by"] = by
    device.attributes["removed_reason"] = reason
    device.attributes.setdefault("command_history", []).append({"action": "removed", "by": by, "reason": reason, "at": _now()})
    save_graph(GRAPH_PATH)

    return device


def list_devices(status=None, loan_id=None, device_type=None):
    devices = _all_devices()
    if status:
        devices = [d for d in devices if d.attributes.get("status") == status]
    if loan_id:
        devices = [d for d in devices if d.attributes.get("loan_id") == loan_id]
    if device_type:
        devices = [d for d in devices if d.attributes.get("device_type") == device_type]
    devices.sort(key=lambda d: d.attributes.get("install_date") or "", reverse=True)
    return {"count": len(devices), "devices": [_device_brief(d) for d in devices]}


# ---------------------------------------------------------------------------
# GPS -- honestly SIMULATED
# ---------------------------------------------------------------------------

def get_simulated_location(device_id):
    device = _get_device(device_id)
    if not device:
        return {"error": f"Device '{device_id}' not found"}

    day_bucket = _today_iso()
    seed = f"{device_id}|{day_bucket}"

    lat = round(_ANCHOR_LAT + _seeded_float(f"{seed}|lat", -0.35, 0.35), 6)
    lng = round(_ANCHOR_LNG + _seeded_float(f"{seed}|lng", -0.35, 0.35), 6)
    speed = _seeded_choice(f"{seed}|speed", [0, 0, 0, 12, 25, 34, 45, 58, 65])
    street_num = 100 + (int(hashlib.sha256(f"{seed}|street".encode()).hexdigest(), 16) % 9800)
    street_name = _seeded_choice(f"{seed}|streetname", [
        "Main St", "Elm Ave", "Oak Blvd", "Highway 40", "Broadway", "5th St",
        "Industrial Pkwy", "Riverside Dr", "Commerce Way", "Sunset Blvd",
    ])

    return {
        "device_id": device_id,
        "loan_id": device.attributes.get("loan_id"),
        "latitude": lat,
        "longitude": lng,
        "approximate_address": f"{street_num} {street_name}",
        "speed_mph": speed,
        "moving": speed > 0,
        "last_ping_at": _now(),
        "basis": SIMULATED_GPS_BASIS,
        "disclaimer": _DISCLAIMER_GPS,
    }


def get_location_history(device_id, days=7):
    device = _get_device(device_id)
    if not device:
        return {"error": f"Device '{device_id}' not found"}

    entries = []
    for i in range(days):
        day = (_today() - timedelta(days=i)).isoformat()
        seed = f"{device_id}|{day}"
        lat = round(_ANCHOR_LAT + _seeded_float(f"{seed}|lat", -0.35, 0.35), 6)
        lng = round(_ANCHOR_LNG + _seeded_float(f"{seed}|lng", -0.35, 0.35), 6)
        entries.append({"date": day, "latitude": lat, "longitude": lng})

    return {
        "device_id": device_id,
        "days": days,
        "entries": entries,
        "basis": SIMULATED_GPS_BASIS,
        "disclaimer": _DISCLAIMER_GPS,
    }


# ---------------------------------------------------------------------------
# Starter Interrupt -- real, stored state
# ---------------------------------------------------------------------------

def _require_starter_capable(device):
    if device.attributes.get("device_type") != "gps_starter_interrupt":
        return {"error": "This device does not have starter-interrupt capability (device_type is 'gps_only')"}
    return None


def arm_starter_interrupt(device_id, by):
    device = _get_device(device_id)
    if not device:
        return {"error": f"Device '{device_id}' not found"}
    err = _require_starter_capable(device)
    if err:
        return err
    if device.attributes.get("status") != "active":
        return {"error": "Cannot arm a removed device"}

    device.attributes["starter_interrupt_armed"] = True
    device.attributes.setdefault("command_history", []).append({"action": "armed", "by": by, "reason": "", "at": _now()})
    save_graph(GRAPH_PATH)

    return device


def send_warning(device_id, by, message=""):
    device = _get_device(device_id)
    if not device:
        return {"error": f"Device '{device_id}' not found"}
    err = _require_starter_capable(device)
    if err:
        return err

    device.attributes["last_warning_at"] = _now()
    device.attributes["last_warning_message"] = message or "Your vehicle's starter may be disabled if this loan remains delinquent. Please contact us."
    device.attributes["last_warning_by"] = by
    device.attributes.setdefault("command_history", []).append({"action": "warning_sent", "by": by, "reason": message, "at": _now()})
    save_graph(GRAPH_PATH)

    return device


def disable_starter(device_id, by, reason=""):
    """Real, enforced gate: refuses to disable unless a warning is already on file
    via send_warning(). Not a cited statute -- an honest, real consumer-protection-
    shaped business rule matching common BHPH industry practice. See
    NOT_LEGAL_ADVICE_NOTICE."""

    device = _get_device(device_id)
    if not device:
        return {"error": f"Device '{device_id}' not found"}
    err = _require_starter_capable(device)
    if err:
        return err
    if device.attributes.get("status") != "active":
        return {"error": "Cannot issue a disable command to a removed device"}
    if not device.attributes.get("starter_interrupt_armed"):
        return {"error": "Device must be armed before it can be disabled -- see arm_starter_interrupt()"}
    if not device.attributes.get("last_warning_at"):
        return {"error": "A warning must be sent to the customer before the starter can be disabled -- see send_warning(). " + NOT_LEGAL_ADVICE_NOTICE}
    if device.attributes.get("starter_status") == "disabled":
        return {"error": "Starter is already disabled"}

    device.attributes["starter_status"] = "disabled"
    device.attributes.setdefault("command_history", []).append({"action": "disabled", "by": by, "reason": reason, "at": _now()})
    save_graph(GRAPH_PATH)

    return device


def enable_starter(device_id, by, reason=""):
    """Re-enabling never requires a prior warning -- it's a customer-favorable
    action (restoring the ability to start the vehicle)."""

    device = _get_device(device_id)
    if not device:
        return {"error": f"Device '{device_id}' not found"}
    err = _require_starter_capable(device)
    if err:
        return err
    if device.attributes.get("starter_status") == "enabled":
        return {"error": "Starter is already enabled"}

    device.attributes["starter_status"] = "enabled"
    device.attributes.setdefault("command_history", []).append({"action": "enabled", "by": by, "reason": reason, "at": _now()})
    save_graph(GRAPH_PATH)

    return device


# ---------------------------------------------------------------------------
# Composed views
# ---------------------------------------------------------------------------

def get_device_detail(device_id):
    device = _get_device(device_id)
    if not device:
        return {"error": f"Device '{device_id}' not found"}

    location = get_simulated_location(device_id) if device.attributes.get("status") == "active" else None

    return {
        "id": device.id,
        "customer": _customer_brief(device.attributes.get("customer_id")),
        "vehicle": _vehicle_brief(device.attributes.get("vehicle_id")),
        **device.attributes,
        "location": location,
        "not_legal_advice_notice": NOT_LEGAL_ADVICE_NOTICE,
    }


def get_device_management_dashboard():
    devices = _all_devices()
    active = [d for d in devices if d.attributes.get("status") == "active"]
    gps_only = [d for d in active if d.attributes.get("device_type") == "gps_only"]
    gps_si = [d for d in active if d.attributes.get("device_type") == "gps_starter_interrupt"]

    return {
        "total_devices": len(devices),
        "active_devices": len(active),
        "removed_devices": len(devices) - len(active),
        "gps_only_count": len(gps_only),
        "gps_starter_interrupt_count": len(gps_si),
        "basis": SIMULATED_GPS_BASIS,
        "disclaimer": _DISCLAIMER_GPS,
    }


def get_starter_interrupt_dashboard():
    devices = [d for d in _all_devices() if d.attributes.get("device_type") == "gps_starter_interrupt" and d.attributes.get("status") == "active"]

    armed = [d for d in devices if d.attributes.get("starter_interrupt_armed")]
    disabled = [d for d in devices if d.attributes.get("starter_status") == "disabled"]
    pending_warning = [d for d in armed if not d.attributes.get("last_warning_at") and d.attributes.get("starter_status") != "disabled"]

    return {
        "starter_interrupt_capable_devices": len(devices),
        "armed_count": len(armed),
        "disabled_count": len(disabled),
        "pending_warning_count": len(pending_warning),
        "not_legal_advice_notice": NOT_LEGAL_ADVICE_NOTICE,
        "devices": [_device_brief(d) for d in devices],
    }
