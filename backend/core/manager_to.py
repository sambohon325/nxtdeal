"""
core/manager_to.py -- Manager TO / Turn-Over (session 101 follow-up), the third of
Sam's ~10 "completely missing" dealership workflows. Both core/sales_menu.py's
reporting() and core/sales_overview.py's get_manager_dashboard() had already
independently flagged this exact gap ("No Manager Turn-Over (TO) data model exists
yet") rather than fake it -- this is that model.

A real TO is a timed hand-off: a salesperson working a customer (usually mid-Up on
the floor, or mid-desking) can't close and asks a manager to take a fresh crack at
it. Three real states -- requested (waiting on a manager), claimed (a manager has
picked it up), resolved (saved/lost/escalated, with a real outcome and elapsed
time). Linked to whatever entity the TO is actually about (a Lead or a Deal) via
linked_entity_id, same convention as core/field_notes.py/core/lead_tasks.py/
core/appointments.py -- not a foreign key, not overloading FieldNote's plain
body/category shape (a TO has real timed state FieldNote doesn't carry).
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import TURN_OVER, LEAD, DEAL

from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

REASONS = ["price", "payment", "trade_value", "financing", "just_looking", "spouse_approval", "product_objection", "other"]
STATUSES = ["requested", "claimed", "resolved"]
OUTCOMES = ["saved", "lost", "escalated"]

_LINKABLE_TYPES = (LEAD, DEAL)


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


def request_to(linked_entity_id, requested_by, reason, notes=""):

    entity = ledger.get_entity(linked_entity_id)

    if not entity or entity.entity_type not in _LINKABLE_TYPES:
        return {"error": f"'{linked_entity_id}' is not a Lead or Deal"}

    if reason not in REASONS:
        return {"error": f"reason must be one of {REASONS}"}

    to_id = id_generator.generate("TO")

    to_entity = Entity(
        id=to_id,
        entity_type=TURN_OVER,
        attributes={
            "linked_entity_id": linked_entity_id,
            "linked_entity_type": entity.entity_type,
            "requested_by": requested_by,
            "reason": reason,
            "notes": notes or "",
            "status": "requested",
            "requested_at": _now_iso(),
            "claimed_by": None,
            "claimed_at": None,
            "resolved_by": None,
            "resolved_at": None,
            "outcome": None,
            "resolution_notes": "",
        },
    )

    ledger.add_entity(to_entity)
    save_graph(GRAPH_PATH)

    return to_entity


def claim_to(to_id, manager_id):

    to_entity = ledger.get_entity(to_id)

    if not to_entity or to_entity.entity_type != TURN_OVER:
        return {"error": "TO not found"}

    if to_entity.attributes.get("status") != "requested":
        return {"error": f"TO is already '{to_entity.attributes.get('status')}'"}

    to_entity.attributes["status"] = "claimed"
    to_entity.attributes["claimed_by"] = manager_id
    to_entity.attributes["claimed_at"] = _now_iso()

    save_graph(GRAPH_PATH)

    return to_entity


def resolve_to(to_id, manager_id, outcome, notes=""):

    to_entity = ledger.get_entity(to_id)

    if not to_entity or to_entity.entity_type != TURN_OVER:
        return {"error": "TO not found"}

    if to_entity.attributes.get("status") == "resolved":
        return {"error": "TO is already resolved"}

    if outcome not in OUTCOMES:
        return {"error": f"outcome must be one of {OUTCOMES}"}

    # A manager can resolve directly from "requested" (claim + resolve in one motion)
    # -- claiming first isn't mandatory, just the honest common case.
    if to_entity.attributes.get("status") == "requested":
        to_entity.attributes["claimed_by"] = manager_id
        to_entity.attributes["claimed_at"] = _now_iso()

    to_entity.attributes["status"] = "resolved"
    to_entity.attributes["resolved_by"] = manager_id
    to_entity.attributes["resolved_at"] = _now_iso()
    to_entity.attributes["outcome"] = outcome
    to_entity.attributes["resolution_notes"] = notes or ""

    save_graph(GRAPH_PATH)

    return to_entity


def list_tos(status=None):

    tos = [e for e in ledger.get_all().values() if e.entity_type == TURN_OVER]

    if status:
        tos = [t for t in tos if t.attributes.get("status") == status]

    tos.sort(key=lambda t: t.attributes.get("requested_at") or "", reverse=True)

    return tos


def list_open_tos():
    """Requested + claimed -- still waiting on a manager or still being worked.
    Sorted oldest-first: the longest-waiting customer is the most urgent, exactly
    the same urgency convention as core/bdc.py's untouched queue."""

    tos = [t for t in list_tos() if t.attributes.get("status") in ("requested", "claimed")]
    tos.sort(key=lambda t: t.attributes.get("requested_at") or "")

    return tos


def get_stats():
    """Real numbers off real resolved records -- save rate and average wait/resolve
    times. Empty/None where there's no sample yet, never a fabricated figure."""

    resolved = list_tos(status="resolved")

    if not resolved:
        return {"sample_size": 0, "save_rate_pct": None, "avg_claim_wait_minutes": None, "avg_resolution_minutes": None}

    saved = sum(1 for t in resolved if t.attributes.get("outcome") == "saved")

    claim_waits = [
        _minutes_between(t.attributes.get("requested_at"), t.attributes.get("claimed_at"))
        for t in resolved
        if t.attributes.get("claimed_at")
    ]
    claim_waits = [m for m in claim_waits if m is not None]

    resolution_times = [
        _minutes_between(t.attributes.get("requested_at"), t.attributes.get("resolved_at"))
        for t in resolved
    ]
    resolution_times = [m for m in resolution_times if m is not None]

    return {
        "sample_size": len(resolved),
        "save_rate_pct": round(100 * saved / len(resolved), 1),
        "avg_claim_wait_minutes": round(sum(claim_waits) / len(claim_waits), 1) if claim_waits else None,
        "avg_resolution_minutes": round(sum(resolution_times) / len(resolution_times), 1) if resolution_times else None,
    }
