"""
core/call_center.py -- Phase 2: Communications Platform, Voice (2026-07-22). Sam's own
kickoff: "Voice * Call Recording * Call Routing * Voicemail." See core/entity_types.py's
own CALL docstring for the full design rationale; restated briefly here.

A Call is its own first-class, own-lifecycle entity (ringing -> connected ->
ended/missed/voicemail), not a dict on Employee/Lead/Customer -- a phone line
accumulates many distinct call events over time, each with its own real routing
decision, duration, and (simulated) recording, matching the "own lifecycle" reasoning
OperationsTask/DamageReport/Payment/Communication already established elsewhere in
this codebase.

Routing reuses the SHAPE of core/lead_routing.py's least-busy-by-active-count pattern
(get_active_workload -> min(workloads, key=workloads.get)), but scoped to this
module's own Call entities and its own department-roster lookup -- deliberately
self-contained rather than importing Lead-specific functions, so Call Center has no
coupling to Lead pipeline state.

Voicemail is SIMULATED, following this codebase's session-110 disclosed-simulation
convention verbatim (a deterministic hashlib.sha256-seeded audio_url/transcript/
duration, always carrying a basis + disclaimer, never presented as a real captured
message) -- mirroring core/communications_hub.py's own _seed_int()/
_simulate_call_recording() pattern exactly, just scoped to a one-way voicemail
message rather than a two-way conversation.

The Coaching Score (Phase 2's "AI Voice: Coaching"/"BDC Center: Call Scoring") and the
QA Review (BDC Center) are both reserved, embedded dict fields on the Call entity --
`coaching_score`/`qa_review` -- populated by a later module (core/call_coaching.py,
Task #8) rather than by this one. This module only creates and manages the Call
lifecycle itself.

Every terminal call (ended/missed/voicemail) synthesizes exactly ONE
core/communications_hub.py Communication record via log_communication() rather than
parallel-logging a second contact-history store -- so a call shows up in the same
Unified Communications feed/Customer 360 timeline every other channel already
populates. A genuinely new, small, additive parameter was added to log_communication()
for this: `skip_recording_simulation=False` (default False, fully backward compatible
with every existing caller). This module passes True for missed/voicemail calls, since
fabricating a two-way "conversation transcript" via that module's own
_simulate_call_recording() for a call that was never actually answered would
misrepresent what happened -- a missed call has no conversation to transcribe, and a
voicemail's own real message content already lives on THIS module's own `voicemail`
dict, not duplicated onto the Communication's `recording` field.
"""

import hashlib
from datetime import datetime, timezone

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CALL, EMPLOYEE
from core.id_generator import IDGenerator
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.communications_hub import log_communication
from core import integrations_registry

id_generator = IDGenerator()

# Mirrors core/website_chat.py's own DEPARTMENTS list exactly, for cross-channel
# consistency -- a call and a chat session use the same department vocabulary.
DEPARTMENTS = ["sales", "service", "finance", "general"]

DIRECTIONS = ["inbound", "outbound"]
CALL_STATUSES = ["ringing", "connected", "ended", "missed", "voicemail"]

# "general" has no dedicated Employee.Department roster to route against (matching
# core/website_chat.py's own department list, where "general" is a catch-all, not a
# real staffed department) -- a call routed to "general" is always manually assigned,
# never auto-routed.
_DEPARTMENT_ROSTER_MAP = {
    "sales": "Sales",
    "service": "Service",
    "finance": "Finance",
}

VOICEMAIL_BASIS = "simulated_voicemail"
VOICEMAIL_DISCLAIMER = (
    "SIMULATED -- no telephony/voicemail vendor is connected in this environment. "
    "This voicemail audio URL and transcript are a deterministic placeholder for "
    "demonstration purposes only, never a real captured message."
)

_VOICEMAIL_SNIPPETS = [
    "Hi, this is a message about my vehicle -- please give me a call back when you get a chance.",
    "I wanted to follow up on the appointment we discussed, call me back at your earliest convenience.",
    "Just checking in on the status of my paperwork, thanks.",
    "Sorry I missed you, please call me back today if possible.",
    "Hey, following up on the quote you sent over -- have a couple questions, call me back.",
]


def _now():
    return datetime.now(timezone.utc).isoformat()


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


def _seed_int(call_id, salt, mod):
    """Deterministic per-call pseudo-random int, same convention
    core/communications_hub.py's own _seed_int()/core/pricing_desk.py's/
    core/acquisitions.py's own hashlib.sha256-seeded helpers already established --
    the same call always reads the same simulated result on repeat fetches."""

    digest = hashlib.sha256(f"{call_id}:{salt}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % mod


def _simulate_voicemail(call_id):

    duration = 10 + _seed_int(call_id, "vm_duration", 90)
    idx = _seed_int(call_id, "vm_snippet", len(_VOICEMAIL_SNIPPETS))

    return {
        "basis": VOICEMAIL_BASIS,
        "disclaimer": VOICEMAIL_DISCLAIMER,
        "duration_seconds": duration,
        "audio_url": f"https://simulated-voicemails.example/{call_id}.mp3",
        "transcript": _VOICEMAIL_SNIPPETS[idx],
        "left_at": _now(),
    }


def _department_employees(department):

    roster_title = _DEPARTMENT_ROSTER_MAP.get(department)

    if not roster_title:
        return []

    return [
        e for e in ledger.get_all().values()
        if e.entity_type == EMPLOYEE
        and (e.attributes.get("Department") or "").strip().lower() == roster_title.lower()
    ]


def _active_call_count(employee_id):
    """A real, live count of this employee's currently ringing/connected calls --
    the same "get_active_workload -> min(workloads)" shape core/lead_routing.py's
    auto_assign_lead() already established, scoped here to Call entities instead of
    Lead entities so this module has no coupling to Lead pipeline state."""

    count = 0

    for e in ledger.get_all().values():
        if e.entity_type != CALL:
            continue
        if e.attributes.get("assigned_to") != employee_id:
            continue
        if e.attributes.get("status") in ("ringing", "connected"):
            count += 1

    return count


def _least_busy_employee(department):

    employees = _department_employees(department)

    if not employees:
        return None, "no_roster"

    workloads = {e.id: _active_call_count(e.id) for e in employees}
    best_id = min(workloads, key=workloads.get)

    return best_id, None


def _call_brief(call):

    attrs = call.attributes

    return {
        "id": call.id,
        "department": attrs.get("department"),
        "direction": attrs.get("direction"),
        "status": attrs.get("status"),
        "from_number": attrs.get("from_number"),
        "to_number": attrs.get("to_number"),
        "assigned_to": attrs.get("assigned_to"),
        "linked_entity_id": attrs.get("linked_entity_id"),
        "created_by": attrs.get("created_by"),
        "created_at": attrs.get("created_at"),
        "connected_at": attrs.get("connected_at"),
        "ended_at": attrs.get("ended_at"),
        "duration_seconds": attrs.get("duration_seconds"),
        "notes": attrs.get("notes"),
        "voicemail": attrs.get("voicemail"),
        "coaching_score": attrs.get("coaching_score"),
        "qa_review": attrs.get("qa_review"),
        "communication_id": attrs.get("communication_id"),
        "routing_note": attrs.get("routing_note"),
    }


def _get_call(call_id):

    call = ledger.get_entity(call_id)

    if not call or call.entity_type != CALL:
        return None

    return call


def _create_call(department, direction, from_number, to_number, created_by,
                  linked_entity_id=None, assigned_to=None, routing_note=None):

    call_id = id_generator.generate("CALL")

    attributes = {
        "department": department,
        "direction": direction,
        "status": "ringing",
        "from_number": from_number,
        "to_number": to_number,
        "assigned_to": assigned_to,
        "linked_entity_id": linked_entity_id,
        "created_by": created_by,
        "created_at": _now(),
        "connected_at": None,
        "ended_at": None,
        "duration_seconds": None,
        "notes": None,
        "voicemail": None,
        "coaching_score": None,
        "qa_review": None,
        "communication_id": None,
        "routing_note": routing_note,
    }

    call = Entity(id=call_id, entity_type=CALL, attributes=attributes)
    ledger.add_entity(call)
    save_graph(GRAPH_PATH)

    return _call_brief(call), None


def route_incoming_call(department, from_number, to_number=None, linked_entity_id=None,
                         created_by="inbound_call_router"):
    """A real inbound call, auto-routed to whichever real Employee in this
    department's own roster currently has the fewest active (ringing/connected)
    calls -- least-busy-first, same shape core/lead_routing.py's auto_assign_lead()
    already established for Leads. If the department has no real roster to route
    against (e.g. "general", or a real department with zero staffed employees on
    file), the call is created unassigned and must be picked up via reassign_call()
    or manually connected by a dispatcher."""

    if department not in DEPARTMENTS:
        return None, f"Unknown department '{department}'. Must be one of {DEPARTMENTS}."

    assigned_to, reason = _least_busy_employee(department)

    if assigned_to:
        # _active_call_count() runs BEFORE this new call is created below, so it
        # already reflects this agent's OTHER active calls -- no off-by-one
        # adjustment needed (a prior draft subtracted 1 here, which underflowed
        # to a nonsensical "-1 other active call(s)" for an agent's very first
        # routed call).
        active_count = _active_call_count(assigned_to)
        routing_note = (
            f"Routed to least-busy available {department.title()} agent "
            f"({active_count} other active call(s) at time of routing)."
        )
    elif reason == "no_roster":
        routing_note = f"No staffed {department.title()} employees on roster -- call unassigned."
    else:
        routing_note = "Call unassigned."

    return _create_call(
        department=department,
        direction="inbound",
        from_number=from_number,
        to_number=to_number,
        created_by=created_by,
        linked_entity_id=linked_entity_id,
        assigned_to=assigned_to,
        routing_note=routing_note,
    )


def place_outbound_call(department, to_number, created_by, from_number=None,
                         linked_entity_id=None):
    """A real outbound call placed BY a specific employee -- always assigned to
    whoever is placing it, no routing decision needed."""

    if department not in DEPARTMENTS:
        return None, f"Unknown department '{department}'. Must be one of {DEPARTMENTS}."

    employee = ledger.get_entity(created_by)
    if not employee or employee.entity_type != EMPLOYEE:
        return None, f"Employee '{created_by}' not found."

    from core.contact_suppression import contact_suppression
    blocked = contact_suppression(to_number, linked_entity_id, channels=("voice",))
    if blocked:
        return None, blocked["error"]

    call, error = _create_call(
        department=department,
        direction="outbound",
        from_number=from_number,
        to_number=to_number,
        created_by=created_by,
        linked_entity_id=linked_entity_id,
        assigned_to=created_by,
        routing_note=f"Outbound call placed directly by {created_by}.",
    )

    # Route through the telephony seam (Phase 8). With no telephony adapter registered this
    # returns a simulated result and the call proceeds as an in-app simulation, exactly as
    # before; register a Twilio/RingCentral adapter and the SAME call dials for real.
    # _create_call returns a serialized brief -- mutate the persisted entity via the ledger.
    if call is not None and not error:
        entity = ledger.get_entity(call.get("id"))
        if entity is not None:
            dispatch = integrations_registry.place_call(to_number, from_number, {"call_id": entity.id, "department": department})
            if dispatch.get("error"):
                entity.attributes["status"] = "blocked"
                entity.attributes["telephony_mode"] = "blocked"
                save_graph(GRAPH_PATH)
                return None, dispatch["error"]
            entity.attributes["telephony_mode"] = "live" if not dispatch.get("simulated") else "simulated"
            entity.attributes["telephony_provider"] = dispatch.get("provider")
            if not dispatch.get("simulated") and dispatch.get("call_sid"):
                entity.attributes["provider_call_sid"] = dispatch.get("call_sid")
            save_graph(GRAPH_PATH)

    return call, error


def reassign_call(call_id, employee_id, reassigned_by):
    """A dispatcher manually pulling a still-ringing call to a specific agent --
    e.g. overriding an unassigned or auto-routed call before it's answered. Only
    valid while the call is still "ringing" -- once connected/ended/missed/
    voicemail, who handled it is a historical fact, not something to edit."""

    call = _get_call(call_id)

    if not call:
        return None, f"Call '{call_id}' not found."

    if call.attributes.get("status") != "ringing":
        return None, f"Call is '{call.attributes.get('status')}', not 'ringing' -- cannot reassign."

    employee = ledger.get_entity(employee_id)
    if not employee or employee.entity_type != EMPLOYEE:
        return None, f"Employee '{employee_id}' not found."

    call.attributes["assigned_to"] = employee_id
    call.attributes["routing_note"] = f"Manually reassigned to {employee_id} by {reassigned_by}."

    save_graph(GRAPH_PATH)

    return _call_brief(call), None


def connect_call(call_id):
    """The assigned agent picks up -- "ringing" -> "connected"."""

    call = _get_call(call_id)

    if not call:
        return None, f"Call '{call_id}' not found."

    if call.attributes.get("status") != "ringing":
        return None, f"Call is '{call.attributes.get('status')}', not 'ringing' -- cannot connect."

    if not call.attributes.get("assigned_to"):
        return None, "No agent is assigned to this call yet -- route or reassign before connecting."

    call.attributes["status"] = "connected"
    call.attributes["connected_at"] = _now()

    save_graph(GRAPH_PATH)

    return _call_brief(call), None


def end_call(call_id, ended_by, notes=None, duration_seconds=None):
    """A real, connected two-way conversation concludes -- "connected" -> "ended".
    Synthesizes a real Communication via log_communication() WITH the normal phone-
    channel recording simulation (a legitimate proxy for "what was discussed," since
    a conversation genuinely happened)."""

    call = _get_call(call_id)

    if not call:
        return None, f"Call '{call_id}' not found."

    if call.attributes.get("status") != "connected":
        return None, f"Call is '{call.attributes.get('status')}', not 'connected' -- cannot end."

    now_iso = _now()

    if duration_seconds is None:
        connected_at = _parse(call.attributes.get("connected_at"))
        ended_at = _parse(now_iso)
        if connected_at and ended_at:
            duration_seconds = max(0, round((ended_at - connected_at).total_seconds()))

    call.attributes["status"] = "ended"
    call.attributes["ended_at"] = now_iso
    call.attributes["duration_seconds"] = duration_seconds
    call.attributes["notes"] = notes

    comm, comm_error = log_communication(
        department=call.attributes.get("department"),
        channel="phone",
        direction=call.attributes.get("direction"),
        body=notes or f"Phone call ({call.attributes.get('direction')}) completed.",
        created_by=ended_by,
        linked_entity_id=call.attributes.get("linked_entity_id"),
        duration_seconds=duration_seconds,
    )

    if comm and not comm_error:
        call.attributes["communication_id"] = comm["id"]

    save_graph(GRAPH_PATH)

    return _call_brief(call), None


def mark_missed(call_id):
    """Nobody answered -- "ringing" -> "missed". Synthesizes a real Communication
    entry (a missed call is still a real, worth-logging touch) but with
    skip_recording_simulation=True -- fabricating a two-way "conversation
    transcript" for a call nobody ever answered would misrepresent what happened."""

    call = _get_call(call_id)

    if not call:
        return None, f"Call '{call_id}' not found."

    if call.attributes.get("status") != "ringing":
        return None, f"Call is '{call.attributes.get('status')}', not 'ringing' -- cannot mark missed."

    now_iso = _now()

    call.attributes["status"] = "missed"
    call.attributes["ended_at"] = now_iso
    call.attributes["duration_seconds"] = 0

    comm, comm_error = log_communication(
        department=call.attributes.get("department"),
        channel="phone",
        direction=call.attributes.get("direction"),
        body="Missed call -- no answer.",
        created_by=call.attributes.get("assigned_to") or "call_center_system",
        linked_entity_id=call.attributes.get("linked_entity_id"),
        duration_seconds=0,
        skip_recording_simulation=True,
    )

    if comm and not comm_error:
        call.attributes["communication_id"] = comm["id"]

    save_graph(GRAPH_PATH)

    return _call_brief(call), None


def send_to_voicemail(call_id):
    """The caller leaves a message instead -- "ringing" -> "voicemail". The real
    (if simulated) message content lives on THIS call's own `voicemail` dict;
    the synthesized Communication references it rather than duplicating a second
    fabricated recording onto the Communication's own `recording` field
    (skip_recording_simulation=True, same reasoning as mark_missed())."""

    call = _get_call(call_id)

    if not call:
        return None, f"Call '{call_id}' not found."

    if call.attributes.get("status") != "ringing":
        return None, f"Call is '{call.attributes.get('status')}', not 'ringing' -- cannot send to voicemail."

    voicemail = _simulate_voicemail(call_id)
    now_iso = _now()

    call.attributes["status"] = "voicemail"
    call.attributes["ended_at"] = now_iso
    call.attributes["duration_seconds"] = voicemail["duration_seconds"]
    call.attributes["voicemail"] = voicemail

    transcript_preview = voicemail["transcript"][:200]

    comm, comm_error = log_communication(
        department=call.attributes.get("department"),
        channel="phone",
        direction=call.attributes.get("direction"),
        body=f"Voicemail left: {transcript_preview}",
        created_by=call.attributes.get("assigned_to") or "call_center_system",
        linked_entity_id=call.attributes.get("linked_entity_id"),
        duration_seconds=voicemail["duration_seconds"],
        skip_recording_simulation=True,
    )

    if comm and not comm_error:
        call.attributes["communication_id"] = comm["id"]

    save_graph(GRAPH_PATH)

    return _call_brief(call), None


def get_call(call_id):

    call = _get_call(call_id)

    if not call:
        return None

    return _call_brief(call)


def list_calls(department=None, status=None, assigned_to=None, linked_entity_id=None,
                limit=200):

    calls = [e for e in ledger.get_all().values() if e.entity_type == CALL]

    if department:
        calls = [c for c in calls if c.attributes.get("department") == department]

    if status:
        calls = [c for c in calls if c.attributes.get("status") == status]

    if assigned_to:
        calls = [c for c in calls if c.attributes.get("assigned_to") == assigned_to]

    if linked_entity_id:
        calls = [c for c in calls if c.attributes.get("linked_entity_id") == linked_entity_id]

    calls.sort(key=lambda c: c.attributes.get("created_at") or "", reverse=True)

    return [_call_brief(c) for c in calls[:limit]]


def get_agent_workload(department=None):
    """A real, live per-agent active-call count -- the same signal
    _least_busy_employee() itself routes off, surfaced directly for a dispatch
    board."""

    departments = [department] if department else list(_DEPARTMENT_ROSTER_MAP.keys())
    result = []

    for dept in departments:
        for employee in _department_employees(dept):
            result.append({
                "employee_id": employee.id,
                "name": f"{employee.attributes.get('FirstName', '')} {employee.attributes.get('LastName', '')}".strip(),
                "department": dept,
                "active_calls": _active_call_count(employee.id),
            })

    return result


def get_call_center_stats(department=None):

    calls = [e for e in ledger.get_all().values() if e.entity_type == CALL]

    if department:
        calls = [c for c in calls if c.attributes.get("department") == department]

    by_status = {status: 0 for status in CALL_STATUSES}
    ended_durations = []

    for call in calls:
        status = call.attributes.get("status")
        if status in by_status:
            by_status[status] += 1
        if status == "ended" and call.attributes.get("duration_seconds") is not None:
            ended_durations.append(call.attributes["duration_seconds"])

    avg_duration = round(sum(ended_durations) / len(ended_durations), 1) if ended_durations else None

    return {
        "department": department,
        "total_calls": len(calls),
        "by_status": by_status,
        "active_calls": by_status["ringing"] + by_status["connected"],
        "average_ended_call_duration_seconds": avg_duration,
        "voicemails_left": by_status["voicemail"],
        "missed_calls": by_status["missed"],
    }
