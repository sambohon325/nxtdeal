"""
core/up_system.py -- the Up System (session 100 follow-up), the first of Sam's ~10
"completely missing" dealership workflows. A real walk-in/phone-up log with a genuine
round-robin floor rotation -- deliberately distinct from core/lead_routing.py's
existing least-busy-employee auto-assignment (that algorithm optimizes total pipeline
load; a real dealership "up board" instead rotates strictly through whoever's
currently working the floor, in a fixed order, so every rep gets a fair shot
regardless of how many older leads they're still carrying).

A logged Up is not a new entity type -- it IS a real Lead, created through the exact
same core/lead_intake.py.create_lead() every other manual lead uses (Source "Walk-In"
or "Phone-Up", both already VALID_SOURCES entries since session 47), then re-assigned
from the person who logged it (often a receptionist/greeter, not a salesperson) to
whoever's actually next in the rotation -- the same mirror-both-the-relationship-and-
the-attribute discipline core/lead_assignment_api.py's transfer_lead_api() already
established, to avoid the exact drift bug that fix was written for. Floor-specific
state lives as a handful of extra attributes on that Lead (up_type/up_status/
up_logged_by/up_logged_at) rather than a parallel object.

The rotation itself (who's on the floor right now, in what order, who's next) is one
singleton UpRotation graph entity -- same no-separate-store rule as everything else in
this codebase.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import UP_ROTATION, EMPLOYEE, LEAD
from core.lead_intake import create_lead
from core.lead_assignment import assign_lead
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

UP_TYPES = ("walk_in", "phone_up")
UP_STATUSES = ["working", "demo", "worksheet", "be_back", "sold", "no_sale"]
_TERMINAL_UP_STATUSES = ("sold", "no_sale")

_ROTATION_ID = "UPROT-00001"


def _now():
    return datetime.now(timezone.utc)


def _now_iso():
    return _now().isoformat()


def _sales_employee_ids():
    return sorted(
        e.id for e in ledger.get_all().values()
        if e.entity_type == EMPLOYEE and (e.attributes.get("Department") or "").strip().lower() == "sales"
    )


def get_rotation():
    """Lazily seeds the rotation from the current real Sales roster the first time
    it's ever asked for -- every employee active by default."""

    rotation = ledger.get_entity(_ROTATION_ID)

    if rotation and rotation.entity_type == UP_ROTATION:
        return rotation

    board = [{"employee_id": eid, "active": True} for eid in _sales_employee_ids()]

    rotation = Entity(
        id=_ROTATION_ID,
        entity_type=UP_ROTATION,
        attributes={"board": board, "next_index": 0, "updated_at": _now_iso()},
    )

    ledger.add_entity(rotation)
    save_graph(GRAPH_PATH)

    return rotation


def set_board_active(employee_id, active):
    """Toggle a rep in/out of today's rotation without losing their place in line
    (stepping out for lunch, going home, etc.) -- an inactive rep is simply skipped,
    not removed."""

    rotation = get_rotation()
    board = rotation.attributes.get("board", [])

    found = False
    for slot in board:
        if slot["employee_id"] == employee_id:
            slot["active"] = active
            found = True
            break

    if not found:
        board.append({"employee_id": employee_id, "active": active})

    rotation.attributes["board"] = board
    rotation.attributes["updated_at"] = _now_iso()
    save_graph(GRAPH_PATH)

    return rotation


def set_board_order(employee_ids):
    """A manager explicitly re-orders (or re-seeds) the board -- e.g. adding a rep
    who wasn't on the original roster snapshot, or resetting the line for a new
    shift. Preserves each employee's current active flag where they already exist on
    the board; new entries default active."""

    rotation = get_rotation()
    existing = {slot["employee_id"]: slot.get("active", True) for slot in rotation.attributes.get("board", [])}

    board = [{"employee_id": eid, "active": existing.get(eid, True)} for eid in employee_ids]

    rotation.attributes["board"] = board
    rotation.attributes["next_index"] = 0
    rotation.attributes["updated_at"] = _now_iso()
    save_graph(GRAPH_PATH)

    return rotation


def peek_next():
    """Who's next, without advancing the pointer -- for display."""

    rotation = get_rotation()
    board = rotation.attributes.get("board", [])

    if not board:
        return None

    n = len(board)
    idx = rotation.attributes.get("next_index", 0) % n

    for i in range(n):
        slot = board[(idx + i) % n]
        if slot.get("active"):
            return slot["employee_id"]

    return None


def _advance():
    """Selects the next active employee and moves the pointer past them. Returns
    None if nobody's currently on the board."""

    rotation = get_rotation()
    board = rotation.attributes.get("board", [])

    if not board:
        return None

    n = len(board)
    idx = rotation.attributes.get("next_index", 0) % n

    for i in range(n):
        pos = (idx + i) % n
        slot = board[pos]
        if slot.get("active"):
            rotation.attributes["next_index"] = (pos + 1) % n
            rotation.attributes["updated_at"] = _now_iso()
            save_graph(GRAPH_PATH)
            return slot["employee_id"]

    return None


def log_up(up_type, logged_by, first_name, last_name, phone=None, email=None, notes=""):

    if up_type not in UP_TYPES:
        return {"error": f"up_type must be one of {list(UP_TYPES)}"}

    if not first_name and not last_name:
        return {"error": "A name is required to log an Up"}

    next_employee = _advance()

    if not next_employee:
        return {"error": "No one is currently on the floor rotation -- add reps to the board first"}

    source = "Walk-In" if up_type == "walk_in" else "Phone-Up"

    lead = create_lead(logged_by, first_name or "Walk-In", last_name or "Customer", source, phone=phone, email=email)

    if next_employee != logged_by:
        assign_lead(lead.id, next_employee)
        lead.attributes["AssignedSalesperson"] = next_employee

    lead.attributes["up_type"] = up_type
    lead.attributes["up_status"] = "working"
    lead.attributes["up_logged_by"] = logged_by
    lead.attributes["up_logged_at"] = _now_iso()

    if notes:
        lead.attributes["up_notes"] = notes

    save_graph(GRAPH_PATH)

    return lead


def update_up_status(lead_id, new_status, updated_by):

    lead = ledger.get_entity(lead_id)

    if not lead or lead.entity_type != LEAD or not lead.attributes.get("up_type"):
        return {"error": "Up not found"}

    if new_status not in UP_STATUSES:
        return {"error": f"status must be one of {UP_STATUSES}"}

    if lead.attributes.get("up_status") in _TERMINAL_UP_STATUSES:
        return {"error": f"This Up is already '{lead.attributes.get('up_status')}'"}

    lead.attributes["up_status"] = new_status
    lead.attributes.setdefault("up_status_history", []).append(
        {"status": new_status, "at": _now_iso(), "by": updated_by}
    )

    save_graph(GRAPH_PATH)

    return lead


def list_ups(status=None, up_type=None, assigned_to=None, date=None):

    ups = [e for e in ledger.get_all().values() if e.entity_type == LEAD and e.attributes.get("up_type")]

    if status:
        ups = [u for u in ups if u.attributes.get("up_status") == status]

    if up_type:
        ups = [u for u in ups if u.attributes.get("up_type") == up_type]

    if assigned_to:
        ups = [u for u in ups if u.attributes.get("AssignedSalesperson") == assigned_to]

    if date:
        ups = [u for u in ups if str(u.attributes.get("up_logged_at") or "").startswith(date)]

    ups.sort(key=lambda u: u.attributes.get("up_logged_at") or "", reverse=True)

    return ups


def get_be_back_board():
    """Leads whose floor visit ended without a sale but who are expected to return --
    a real, distinct dealership floor concept from a fully dead/LOST lead."""

    return list_ups(status="be_back")
