"""
core/ai_worker.py — the NXTDeal AI Workforce: customer-facing AI workers
(2026-07-24). Sam's spec: NXTDeal should provide an AI version of every role a
dealership already staffs — AI Receptionist, AI BDC, AI Sales Assistant, AI Service
Advisor, AI Marketing Agent, AI Finance Assistant, AI Collections Agent, and an AI
Operator — each working across the dealership's communication channels.

This is the missing abstraction the rest of the "NXTDeal Workforce AI" vision plugs
into. The existing pieces already cover the EMPLOYEE-facing side: core/screen_guidance.py
assists an employee, core/bot_coverage.py covers an ABSENT employee, core/coaching.py
coaches, core/bot_fleet.py records a team's workflows. None of them is a NAMED, role-
specialized worker that HANDLES a customer interaction itself — answers the call, texts
the lead, books the appointment. That is what an AiWorker is.

An AiWorker is an ordinary graph entity in the same single ledger as everything else
(Pillar 3's one-graph invariant), holding its role, the channels it works, and its
activation state/mode. Handling an interaction ALWAYS logs a real Communication
(core/communications_hub.py) and records each proposed action as an AiWorkerAction — so
the AI Dashboard (conversations handled, appointments set, tasks drafted) reads from real,
persisted records, not a fabricated feed.

SAFETY POSTURE — inherited, not relaxed. A worker runs in one of three modes:
  * draft       -- every proposed action is DRAFTED for a human; nothing executes.
  * assisted    -- proposed actions on WORKER_SAFE_ACTIONS execute; everything else drafts.
  * autonomous  -- same whitelist, but additionally gated by the AI kill switch AND the
                   new default-deny `ai.worker.autonomous` capability (department scope).
WORKER_SAFE_ACTIONS is a DELIBERATELY small set of genuinely-safe, reversible actions
(route a call, book a service/sales appointment, send a confirmation). Anything touching
money, deals, funding, payments, pricing, or repossession is NOT on it and ALWAYS drafts
for a human, in every mode — the AI workforce can schedule and inform on its own, but never
commit a financial or contractual action unattended. This mirrors core/bot_fleet.py's
FLEET_SAFE_ACTIONS choke point.

Response text is generated from transparent templates, not a fabricated "AI transcript"
(same honesty bar as core/call_coaching.py's rules-based rubric) -- so what the worker
would say is deterministic and auditable.
"""

from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import AI_WORKER, AI_WORKER_ACTION
from core.audit import audit_log
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# ------------------------------------------------------------------------------------
# The roles of the digital workforce (the original 8 communications roles + the 5
# Digital Retail customer-facing roles added in DR-7).
# ------------------------------------------------------------------------------------
WORKER_ROLES = (
    "receptionist",
    "bdc",
    "sales",
    "service",
    "marketing",
    "finance",
    "collections",
    "operator",
    # Digital Retail customer-facing roles (2026-07-24, DR-7) -- the AI Workforce that drives
    # the self-service purchase journey (DR-1..6 modules). Same activation/mode/gate machinery
    # as every other worker.
    "product_specialist",
    "trade_manager",
    "negotiator",
    "delivery_coordinator",
    "ownership_concierge",
)

ROLE_DISPLAY = {
    "receptionist": "AI Receptionist",
    "bdc": "AI BDC Agent",
    "sales": "AI Sales Assistant",
    "service": "AI Service Advisor",
    "marketing": "AI Marketing Agent",
    "finance": "AI Finance Assistant",
    "collections": "AI Collections Agent",
    "operator": "AI Operator",
    "product_specialist": "AI Product Specialist",
    "trade_manager": "AI Trade Manager",
    "negotiator": "AI Negotiator",
    "delivery_coordinator": "AI Delivery Coordinator",
    "ownership_concierge": "AI Ownership Concierge",
}

# Which channels each worker works by default (customer-facing). The operator is the
# internal screen assistant and has no customer channels.
CHANNELS = ("phone", "sms", "email", "chat", "website", "social")
ROLE_CHANNELS = {
    "receptionist": ("phone", "sms", "chat", "website"),
    "bdc": ("phone", "sms", "email", "chat"),
    "sales": ("sms", "email", "chat"),
    "service": ("phone", "sms", "email"),
    "marketing": ("email", "sms", "social"),
    "finance": ("email", "sms", "phone"),
    "collections": ("phone", "sms", "email"),
    "operator": (),
    "product_specialist": ("chat", "website", "sms", "email"),
    "trade_manager": ("chat", "email", "sms"),
    "negotiator": ("chat", "sms", "email"),
    "delivery_coordinator": ("sms", "email", "phone"),
    "ownership_concierge": ("email", "sms", "phone"),
}

# Real department a worker routes/logs under. communications_hub accepts a free-form
# department string; call_center only routes the four it staffs (sales/service/finance/
# general), so receptionist/operator/marketing/collections fall back to a routable one.
ROLE_CALL_DEPARTMENT = {
    "receptionist": "general",
    "bdc": "sales",
    "sales": "sales",
    "service": "service",
    "marketing": "sales",
    "finance": "finance",
    "collections": "finance",
    "operator": "general",
    "product_specialist": "sales",
    "trade_manager": "sales",
    "negotiator": "sales",
    "delivery_coordinator": "sales",
    "ownership_concierge": "service",
}

# communications_hub CHANNELS are phone/text/email/chat/social -- map the worker's
# channel vocabulary onto them for logging.
_COMM_CHANNEL = {
    "phone": "phone", "sms": "text", "email": "email",
    "chat": "chat", "website": "chat", "social": "social",
}

MODE_DRAFT = "draft"
MODE_ASSISTED = "assisted"
MODE_AUTONOMOUS = "autonomous"
VALID_MODES = (MODE_DRAFT, MODE_ASSISTED, MODE_AUTONOMOUS)

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"

# The ONLY action keys an active worker may EXECUTE (vs. draft) -- and even then only in
# assisted/autonomous mode. Everything not listed here ALWAYS drafts for a human, in every
# mode. Genuinely-safe, reversible, non-financial actions only.
WORKER_SAFE_ACTIONS = {
    "route_call",
    "book_appointment",
    "send_confirmation",
    # Slice 2 (AI BDC): outbound informational customer touches -- a follow-up text/email
    # and an appointment confirmation/reminder. Still "inform", never financial/contractual.
    "send_outbound_message",
    "confirm_appointment",
}

AUTONOMOUS_CAPABILITY = "ai.worker.autonomous"


def _now():
    return datetime.now(timezone.utc).isoformat()


def normalize_role(role):
    if not role:
        return None
    key = str(role).strip().lower()
    return key if key in WORKER_ROLES else None


def _display(role):
    return ROLE_DISPLAY.get(role, role)


# ------------------------------------------------------------------------------------
# AiWorker entities -- one per role, materialized lazily on first touch.
# ------------------------------------------------------------------------------------

def _find_worker(role):
    for entity in ledger.get_all().values():
        if entity.entity_type == AI_WORKER and entity.attributes.get("role") == role:
            return entity
    return None


def get_or_create_worker(role):
    role = normalize_role(role)
    if role is None:
        return None
    existing = _find_worker(role)
    if existing is not None:
        return existing
    worker = Entity(
        id=id_generator.generate("AIW"),
        entity_type=AI_WORKER,
        attributes={
            "role": role,
            "display_name": _display(role),
            "channels": list(ROLE_CHANNELS.get(role, ())),
            "status": STATUS_INACTIVE,
            "mode": MODE_DRAFT,
            "activated_by": None,
            "activated_at": None,
            "deactivated_by": None,
            "deactivated_at": None,
            "created_at": _now(),
        },
    )
    ledger.add_entity(worker)
    save_graph(GRAPH_PATH)
    return worker


def _worker_view(worker):
    a = worker.attributes
    role = a.get("role")
    return {
        "id": worker.id,
        "role": role,
        "display_name": a.get("display_name") or _display(role),
        "channels": a.get("channels") or [],
        "status": a.get("status"),
        "mode": a.get("mode"),
        "activated_by": a.get("activated_by"),
        "activated_at": a.get("activated_at"),
        "deactivated_by": a.get("deactivated_by"),
        "deactivated_at": a.get("deactivated_at"),
        "created_at": a.get("created_at"),
        "interactions_handled": _interaction_count(role),
        "actions_executed": _action_count(role, "executed"),
        "actions_drafted": _action_count(role, "drafted"),
    }


def list_workforce():
    return [_worker_view(get_or_create_worker(role)) for role in WORKER_ROLES]


def workforce_summary():
    workers = [get_or_create_worker(r) for r in WORKER_ROLES]
    active = [w for w in workers if w.attributes.get("status") == STATUS_ACTIVE]
    return {
        "total_workers": len(workers),
        "active_workers": len(active),
        "autonomous_workers": len([w for w in active if w.attributes.get("mode") == MODE_AUTONOMOUS]),
        "total_interactions": sum(_interaction_count(r) for r in WORKER_ROLES),
        "total_actions_executed": sum(_action_count(r, "executed") for r in WORKER_ROLES),
        "total_actions_drafted": sum(_action_count(r, "drafted") for r in WORKER_ROLES),
    }


def activate_worker(role, mode, admin_id):
    """Admin-activate an AI worker in draft / assisted / autonomous mode. Autonomous is
    gated at activation by the default-deny ai.worker.autonomous capability (department
    scope) -- so a denied request fails loud here instead of silently activating a worker
    that could never actually act unattended."""

    role = normalize_role(role)
    if role is None:
        return {"error": "Unknown role -- must be one of the AI workforce roles"}

    if mode not in VALID_MODES:
        return {"error": f"Unknown mode '{mode}' -- must be one of {VALID_MODES}"}

    if mode == MODE_AUTONOMOUS:
        from core.bot_permissions import is_capability_granted, normalize_department
        department = normalize_department(ROLE_CALL_DEPARTMENT.get(role))
        if not is_capability_granted(AUTONOMOUS_CAPABILITY, department=department):
            return {
                "error": (
                    "Autonomous mode for this AI worker is not granted"
                    + (f" for the {department} department" if department else "")
                    + f" -- an ADMIN must grant the {AUTONOMOUS_CAPABILITY} capability first."
                )
            }

    worker = get_or_create_worker(role)
    worker.attributes["status"] = STATUS_ACTIVE
    worker.attributes["mode"] = mode
    worker.attributes["activated_by"] = admin_id
    worker.attributes["activated_at"] = _now()
    worker.attributes["deactivated_by"] = None
    worker.attributes["deactivated_at"] = None
    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="ai_worker_activated",
        summary=f"{admin_id} activated the {_display(role)} in {mode} mode",
        entity_id=worker.id,
        actor=admin_id,
        details={"role": role, "mode": mode},
    )
    return {"worker": _worker_view(worker)}


def deactivate_worker(role, admin_id):
    role = normalize_role(role)
    if role is None:
        return {"error": "Unknown role -- must be one of the AI workforce roles"}
    worker = get_or_create_worker(role)
    worker.attributes["status"] = STATUS_INACTIVE
    worker.attributes["mode"] = MODE_DRAFT
    worker.attributes["deactivated_by"] = admin_id
    worker.attributes["deactivated_at"] = _now()
    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="ai_worker_deactivated",
        summary=f"{admin_id} deactivated the {_display(role)}",
        entity_id=worker.id,
        actor=admin_id,
        details={"role": role},
    )
    return {"worker": _worker_view(worker)}


# ------------------------------------------------------------------------------------
# The execution gate -- execute a proposed action, or draft it for a human.
# ------------------------------------------------------------------------------------

def _execution_gate(worker, action_key):
    """Returns (may_execute, reason). A worker EXECUTES an action only if it is active,
    the action is on WORKER_SAFE_ACTIONS, and its mode permits -- with autonomous mode
    additionally requiring the AI kill switch on and the default-deny capability."""

    if worker.attributes.get("status") != STATUS_ACTIVE:
        return False, "worker inactive -- drafted"
    if action_key not in WORKER_SAFE_ACTIONS:
        return False, "action not on the AI Worker safe-action whitelist -- drafted for a human"
    mode = worker.attributes.get("mode")
    if mode == MODE_DRAFT:
        return False, "draft mode -- drafted for a human"

    # The AI kill switch short-circuits EVERY execution path (assisted and autonomous), not just
    # autonomous — an emergency "kill everything" must also stop assisted workers auto-sending
    # messages / booking appointments. Draft mode returns above (it never executes anyway).
    from core.ai_kill_switch import is_bot_enabled
    if not is_bot_enabled():
        return False, "AI kill switch is off -- drafted"

    if mode == MODE_ASSISTED:
        return True, "assisted mode -- whitelisted action executed"
    if mode == MODE_AUTONOMOUS:
        from core.bot_permissions import is_capability_granted, normalize_department
        department = normalize_department(ROLE_CALL_DEPARTMENT.get(worker.attributes.get("role")))
        if not is_capability_granted(AUTONOMOUS_CAPABILITY, department=department):
            return False, "ai.worker.autonomous not granted -- drafted"
        return True, "autonomous mode -- whitelisted action executed"
    return False, "unknown mode -- drafted"


def _record_action(role, channel, intent, action_key, status, params, result, communication_id, actor):
    action = Entity(
        id=id_generator.generate("AIWA"),
        entity_type=AI_WORKER_ACTION,
        attributes={
            "role": role,
            "channel": channel,
            "intent": intent,
            "action_key": action_key,
            "status": status,          # "executed" | "drafted"
            "params": params,
            "result": result,
            "communication_id": communication_id,
            "actor": actor,
            "recorded_at": _now(),
        },
    )
    ledger.add_entity(action)
    return action


def _actions_for(role):
    return [
        e for e in ledger.get_all().values()
        if e.entity_type == AI_WORKER_ACTION and e.attributes.get("role") == role
    ]


def _action_count(role, status):
    return len([a for a in _actions_for(role) if a.attributes.get("status") == status])


def _interaction_count(role):
    # one interaction == one distinct communication_id handled by this worker
    ids = {a.attributes.get("communication_id") for a in _actions_for(role)}
    ids.discard(None)
    return len(ids)


# ------------------------------------------------------------------------------------
# Intent detection -- transparent keyword rules, not a fabricated LLM classification.
# ------------------------------------------------------------------------------------

_INTENT_KEYWORDS = [
    ("schedule_service", ("oil change", "service", "maintenance", "brake", "tire", "recall", "repair")),
    ("schedule_sales", ("test drive", "test-drive", "come in", "showroom", "see the", "look at")),
    ("hours", ("hours", "open", "close", "closing", "what time")),
    ("inventory", ("do you have", "looking for", "in stock", "price of", "how much is", "available")),
    ("status", ("ready", "status", "is my", "done yet", "finished")),
]


def _detect_intent(message):
    text = (message or "").lower()
    for intent, keywords in _INTENT_KEYWORDS:
        if any(k in text for k in keywords):
            return intent
    return "general"


# ------------------------------------------------------------------------------------
# Handling an interaction.
# ------------------------------------------------------------------------------------

def _log_inbound(role, channel, message, actor, linked_entity_id):
    from core.communications_hub import log_communication
    comm_channel = _COMM_CHANNEL.get(channel, "chat")
    department = ROLE_CALL_DEPARTMENT.get(role, "general")
    comm, error = log_communication(
        department=department,
        channel=comm_channel,
        direction="inbound",
        body=message or "",
        created_by=f"ai_worker:{role}",
        linked_entity_id=linked_entity_id,
        skip_recording_simulation=True,
    )
    if error:
        return None
    return comm


def _proposed_actions(role, intent, scheduled_start, from_number):
    """The actions this worker proposes for the detected intent. Each is (action_key,
    params, response_fragment). Only the receptionist has deep per-intent handling in this
    slice; other roles propose a safe default (answer, and draft a follow-up)."""

    if role in ("receptionist", "bdc", "sales", "service"):
        if intent == "schedule_service":
            if scheduled_start:
                return [("book_appointment",
                         {"department": "Service", "appointment_type": "service", "scheduled_start": scheduled_start},
                         "Absolutely — you're booked in for service. I'll text you a confirmation."),
                        ("send_confirmation",
                         {"body": "Your service appointment is confirmed. Reply here with any questions."},
                         None)]
            return [("book_appointment",
                     {"department": "Service", "appointment_type": "service", "scheduled_start": None},
                     "Absolutely. What day works best for you?")]
        if intent == "schedule_sales":
            if scheduled_start:
                return [("book_appointment",
                         {"department": "Sales", "appointment_type": "showroom_visit", "scheduled_start": scheduled_start},
                         "Great — I've set up your visit. I'll send a confirmation."),
                        ("send_confirmation",
                         {"body": "Your showroom visit is confirmed. See you soon!"},
                         None)]
            return [("book_appointment",
                     {"department": "Sales", "appointment_type": "showroom_visit", "scheduled_start": None},
                     "I'd be happy to set that up. What day and time works for you?")]
        if intent == "hours":
            return [("answer", {"topic": "hours"},
                     "We're open Monday–Saturday, 9am–7pm, and closed Sundays. Anything else I can help with?")]
        if intent == "inventory":
            return [("answer", {"topic": "inventory"},
                     "I can check that for you — could you tell me the year, make, and model you're interested in?")]
        if intent == "status":
            return [("answer", {"topic": "status"},
                     "Let me look that up. Can you give me your name or repair-order number?")]
        # general -- greet + offer to route a call
        actions = [("answer", {"topic": "general"},
                    "Thanks for reaching out! How can I help — sales, service, or something else?")]
        if from_number:
            actions.append(("route_call", {"from_number": from_number}, None))
        return actions

    if role == "operator":
        # The internal AI Operator ("help me with this screen") -- no customer channels;
        # it assists the employee. Full screen-context guidance lives in
        # core/screen_guidance.py; here the worker acknowledges and orients the user.
        return [("answer", {"topic": "screen_help"},
                 "I can help with that. Tell me which screen you're on and what you're trying "
                 "to do, and I'll walk you through the next step or flag what needs attention.")]

    # Remaining roles: acknowledge + draft a follow-up for the owning team.
    return [("answer", {"topic": intent},
             f"Thanks — I've noted this and the {ROLE_CALL_DEPARTMENT.get(role, 'team')} team will follow up."),
            ("draft_follow_up", {"intent": intent}, None)]


def _execute_action(role, action_key, params, actor, linked_entity_id):
    """Actually perform a whitelisted action. Returns (result_dict, human_note)."""
    if action_key == "book_appointment":
        if not params.get("scheduled_start"):
            return {"error": "no time provided"}, "needs a preferred time before it can be booked"
        from core.appointments import create_appointment
        created = create_appointment(
            department=params["department"],
            appointment_type=params["appointment_type"],
            scheduled_start=params["scheduled_start"],
            created_by=f"ai_worker:{role}",
            customer_id=linked_entity_id if str(linked_entity_id or "").startswith("CUST") else None,
            lead_id=linked_entity_id if str(linked_entity_id or "").startswith("LEAD") else None,
        )
        # create_appointment returns an error dict on failure, else the raw Entity --
        # coerce to a plain, JSON-serializable summary for the AiWorkerAction record.
        if isinstance(created, dict) and created.get("error"):
            return created, None
        appt_id = getattr(created, "id", None) or (created.get("id") if isinstance(created, dict) else None)
        return {
            "appointment_id": appt_id,
            "department": params["department"],
            "appointment_type": params["appointment_type"],
            "scheduled_start": params["scheduled_start"],
        }, None
    if action_key == "send_confirmation":
        from core.communications_hub import log_communication
        comm, error = log_communication(
            department=ROLE_CALL_DEPARTMENT.get(role, "general"),
            channel="text",
            direction="outbound",
            body=params.get("body", "Confirmed."),
            created_by=f"ai_worker:{role}",
            linked_entity_id=linked_entity_id,
            skip_recording_simulation=True,
        )
        return ({"error": error} if error else {"communication_id": comm["id"]}), None
    if action_key == "route_call":
        from core.call_center import route_incoming_call
        call, error = route_incoming_call(
            department=ROLE_CALL_DEPARTMENT.get(role, "general"),
            from_number=params.get("from_number", "unknown"),
            linked_entity_id=linked_entity_id,
            created_by=f"ai_worker:{role}",
        )
        return ({"error": error} if error else {"call_id": call["id"]}), None
    if action_key in ("send_outbound_message", "confirm_appointment"):
        from core.communications_hub import log_communication
        comm, error = log_communication(
            department=ROLE_CALL_DEPARTMENT.get(role, "general"),
            channel="text",
            direction="outbound",
            body=params.get("body", ""),
            created_by=f"ai_worker:{role}",
            linked_entity_id=linked_entity_id,
            skip_recording_simulation=True,
        )
        return ({"error": error} if error else {"communication_id": comm["id"]}), None
    return {"error": f"no executor for '{action_key}'"}, None


def handle_interaction(role, channel, message, actor, scheduled_start=None,
                       linked_entity_id=None, from_number=None):
    """The backbone: an AI worker handles one inbound customer interaction. Always logs the
    inbound touch as a real Communication, detects the intent, proposes the appropriate
    actions, and either EXECUTES each (if the gate permits) or DRAFTS it for a human --
    recording every proposed action as an AiWorkerAction. Returns the response the worker
    would send plus the per-action outcome."""

    role = normalize_role(role)
    if role is None:
        return {"error": "Unknown role -- must be one of the AI workforce roles"}

    worker = get_or_create_worker(role)
    comm = _log_inbound(role, channel, message, actor, linked_entity_id)
    communication_id = comm["id"] if comm else None

    intent = _detect_intent(message)
    proposals = _proposed_actions(role, intent, scheduled_start, from_number)

    response_parts = []
    action_results = []
    for action_key, params, fragment in proposals:
        if fragment:
            response_parts.append(fragment)

        # "answer" and "draft_follow_up" are inherent, never executed side-effects:
        # answer just replies; draft_follow_up is always a drafted suggestion.
        if action_key == "answer":
            continue
        if action_key == "draft_follow_up":
            _record_action(role, channel, intent, action_key, "drafted", params, None, communication_id, actor)
            action_results.append({"action_key": action_key, "status": "drafted", "reason": "follow-up drafted for the team"})
            save_graph(GRAPH_PATH)
            continue

        may_execute, reason = _execution_gate(worker, action_key)
        if may_execute:
            result, human_note = _execute_action(role, action_key, params, actor, linked_entity_id)
            if isinstance(result, dict) and result.get("error"):
                # couldn't execute (e.g. missing time) -> drafted instead
                _record_action(role, channel, intent, action_key, "drafted", params, result, communication_id, actor)
                action_results.append({"action_key": action_key, "status": "drafted",
                                       "reason": human_note or result.get("error")})
            else:
                _record_action(role, channel, intent, action_key, "executed", params, result, communication_id, actor)
                action_results.append({"action_key": action_key, "status": "executed", "result": result})
        else:
            _record_action(role, channel, intent, action_key, "drafted", params, None, communication_id, actor)
            action_results.append({"action_key": action_key, "status": "drafted", "reason": reason})
        save_graph(GRAPH_PATH)

    return {
        "role": role,
        "display_name": _display(role),
        "mode": worker.attributes.get("mode"),
        "status": worker.attributes.get("status"),
        "channel": channel,
        "intent": intent,
        "response": " ".join(response_parts).strip(),
        "communication_id": communication_id,
        "actions": action_results,
        "note": (
            "Response text is templated (transparent), not a fabricated AI transcript. "
            "Actions execute only when the worker is armed and the action is on the safe "
            "whitelist; everything else is drafted for a human."
        ),
    }


def get_worker_detail(role, limit=15):
    role = normalize_role(role)
    if role is None:
        return {"available": False, "note": "Unknown role -- not one of the AI workforce roles."}
    worker = get_or_create_worker(role)
    actions = sorted(_actions_for(role), key=lambda a: a.attributes.get("recorded_at", ""))
    recent = [
        {
            "action_key": a.attributes.get("action_key"),
            "intent": a.attributes.get("intent"),
            "channel": a.attributes.get("channel"),
            "status": a.attributes.get("status"),
            "communication_id": a.attributes.get("communication_id"),
            "recorded_at": a.attributes.get("recorded_at"),
        }
        for a in actions[-limit:]
    ]
    view = _worker_view(worker)
    view["available"] = True
    view["safe_actions"] = sorted(WORKER_SAFE_ACTIONS)
    view["recent_actions"] = recent
    return view


# ------------------------------------------------------------------------------------
# Slice 2 -- OUTBOUND: a worker works its queue. Today the AI BDC agent (the deck's most
# BDC-heavy role): follow up untouched internet leads, confirm upcoming appointments, and
# recover no-shows -- each an outbound touch that EXECUTES or DRAFTS via the same gate.
# ------------------------------------------------------------------------------------

def _entity_id(x):
    return getattr(x, "id", None) or (x.get("id") if isinstance(x, dict) else None)


def _run_outbound(worker, role, channel, action_key, params, actor, linked_entity_id):
    """Apply one proposed outbound action through the same execution gate as inbound
    handling: execute it if the worker is armed and it's whitelisted, otherwise draft it.
    Records an AiWorkerAction either way."""
    kind = params.get("kind")
    may, reason = _execution_gate(worker, action_key)
    if may:
        result, human_note = _execute_action(role, action_key, params, actor, linked_entity_id)
        if isinstance(result, dict) and result.get("error"):
            _record_action(role, channel, kind, action_key, "drafted", params, result, None, actor)
            outcome = {"action_key": action_key, "kind": kind, "status": "drafted",
                       "reason": human_note or result.get("error"), "linked_entity_id": linked_entity_id}
        else:
            comm_id = result.get("communication_id") if isinstance(result, dict) else None
            _record_action(role, channel, kind, action_key, "executed", params, result, comm_id, actor)
            outcome = {"action_key": action_key, "kind": kind, "status": "executed",
                       "linked_entity_id": linked_entity_id}
    else:
        _record_action(role, channel, kind, action_key, "drafted", params, None, None, actor)
        outcome = {"action_key": action_key, "kind": kind, "status": "drafted",
                   "reason": reason, "linked_entity_id": linked_entity_id}
    save_graph(GRAPH_PATH)
    return outcome


_QUEUE_ROLES = ("bdc", "sales", "service", "collections", "finance", "marketing")


def work_queue(role, actor, limit=10):
    """An AI worker works its outbound queue. Implemented for BDC, Sales, Service,
    Collections, Finance, and Marketing; the Operator is inbound-only (screen help) and has
    no queue. Every touch runs through the same _execution_gate."""

    role = normalize_role(role)
    if role is None:
        return {"error": "Unknown role -- must be one of the AI workforce roles"}
    worker = get_or_create_worker(role)

    if role == "bdc":
        return _bdc_queue(worker, actor, limit)
    if role == "sales":
        return _sales_queue(worker, actor, limit)
    if role == "service":
        return _service_queue(worker, actor, limit)
    if role == "collections":
        return _collections_queue(worker, actor, limit)
    if role == "finance":
        return _finance_queue(worker, actor, limit)
    if role == "marketing":
        return _marketing_queue(worker, actor, limit)
    if role == "trade_manager":
        return _trade_manager_queue(worker, actor, limit)
    if role == "negotiator":
        return _negotiator_queue(worker, actor, limit)
    if role == "delivery_coordinator":
        return _delivery_coordinator_queue(worker, actor, limit)
    if role == "ownership_concierge":
        return _ownership_concierge_queue(worker, actor, limit)

    return {
        "available": False,
        "role": role,
        "note": f"The {_display(role)} is inbound-only (real-time shopping/screen assistance) "
                "and has no outbound queue -- use handle_interaction instead.",
    }


def _queue_result(worker, role, actions, buckets):
    """Common result shape: the per-action outcomes plus a summary that counts executed vs.
    drafted and each named bucket. `buckets` is {name: [items]}, merged into the result."""
    summary = {
        "executed": len([a for a in actions if a["status"] == "executed"]),
        "drafted": len([a for a in actions if a["status"] == "drafted"]),
    }
    for name, items in buckets.items():
        summary[name] = len(items)
    return {
        "role": role,
        "display_name": _display(role),
        "mode": worker.attributes.get("mode"),
        "status": worker.attributes.get("status"),
        "actions": actions,
        "summary": summary,
        **buckets,
    }


def _bdc_queue(worker, actor, limit):
    """AI BDC agent: follow up untouched internet leads, confirm upcoming sales
    appointments, recover no-shows."""
    leads_followed_up, appointments_confirmed, no_shows_recovered, actions = [], [], [], []

    from core.bdc import get_untouched_queue
    for brief in get_untouched_queue()[:limit]:
        lead_id = brief.get("id")
        name = brief.get("first_name") or "there"
        params = {"kind": "lead_follow_up",
                  "body": f"Hi {name}, thanks for your interest! I'd love to help — "
                          "what day and time works for you to come take a look?"}
        outcome = _run_outbound(worker, "bdc", "sms", "send_outbound_message", params, actor, lead_id)
        actions.append(outcome)
        leads_followed_up.append({"lead_id": lead_id, "status": outcome["status"]})

    from core.appointments import list_upcoming_within, list_appointments
    for appt in list_upcoming_within(48, department="Sales")[:limit]:
        appt_id = _entity_id(appt)
        params = {"kind": "confirmation",
                  "body": "Reminder: your appointment with us is coming up. "
                          "Reply here to confirm, or let me know if you'd like to reschedule."}
        outcome = _run_outbound(worker, "bdc", "sms", "confirm_appointment", params, actor, appt_id)
        actions.append(outcome)
        appointments_confirmed.append({"appointment_id": appt_id, "status": outcome["status"]})

    for appt in list_appointments(status="no_show")[:limit]:
        appt_id = _entity_id(appt)
        params = {"kind": "no_show_recovery",
                  "body": "Sorry we missed you! Let's get you back on the calendar — "
                          "what day works better for you?"}
        outcome = _run_outbound(worker, "bdc", "sms", "send_outbound_message", params, actor, appt_id)
        actions.append(outcome)
        no_shows_recovered.append({"appointment_id": appt_id, "status": outcome["status"]})

    return _queue_result(worker, "bdc", actions, {
        "leads_followed_up": leads_followed_up,
        "appointments_confirmed": appointments_confirmed,
        "no_shows_recovered": no_shows_recovered,
    })


def _sales_queue(worker, actor, limit):
    """AI Sales Assistant: follow up OPEN sales leads that have gone quiet (past the
    follow-up threshold), skipping any already in a terminal (sold/lost) state."""
    from core.entity_types import LEAD
    from core.follow_up_queue import get_follow_up_queue

    lead_ids = [e.id for e in ledger.get_all().values() if e.entity_type == LEAD]
    terminal = ("sold", "lost", "dead", "delivered", "closed", "bought")
    stale = [
        row for row in get_follow_up_queue(lead_ids, threshold_days=3)
        if not any(t in (str(row.get("current_state") or "").lower()) for t in terminal)
    ]

    followed, actions = [], []
    for row in stale[:limit]:
        lead_id = row["lead_id"]
        params = {"kind": "sales_follow_up",
                  "body": "Hi! Just circling back on the vehicle you were looking at — "
                          "still interested? I'm happy to hold it or set up a time for you to come see it."}
        outcome = _run_outbound(worker, "sales", "sms", "send_outbound_message", params, actor, lead_id)
        actions.append(outcome)
        followed.append({"lead_id": lead_id, "status": outcome["status"]})

    return _queue_result(worker, "sales", actions, {"leads_followed_up": followed})


def _service_queue(worker, actor, limit):
    """AI Service Advisor: notify customers whose vehicle is ready for pickup (the RO's
    'Delivery' stage) and send a service follow-up on ROs in the 'Follow-Up' stage."""
    from core.repair_orders import get_ro_board
    board = get_ro_board()

    ready, follow_ups, actions = [], [], []
    for ro in (board.get("Delivery") or [])[:limit]:
        ro_id = ro.get("id")
        params = {"kind": "ready_for_pickup",
                  "body": "Great news — your vehicle is ready for pickup! "
                          "Let me know when you're on the way, or reply with any questions."}
        outcome = _run_outbound(worker, "service", "sms", "send_outbound_message", params, actor, ro_id)
        actions.append(outcome)
        ready.append({"ro_id": ro_id, "status": outcome["status"]})

    for ro in (board.get("Follow-Up") or [])[:limit]:
        ro_id = ro.get("id")
        params = {"kind": "service_follow_up",
                  "body": "Thanks for visiting our service department! "
                          "How's everything running? Reply here if there's anything we can help with."}
        outcome = _run_outbound(worker, "service", "sms", "send_outbound_message", params, actor, ro_id)
        actions.append(outcome)
        follow_ups.append({"ro_id": ro_id, "status": outcome["status"]})

    # DVI / estimate approvals (2026-07-24): ROs sitting in the "Customer Approval" stage need
    # the customer to approve the estimate + flagged DVI findings. Generate the real public
    # approval link (core/approval_center.py) and send it. Approving stays the CUSTOMER's action.
    from core.approval_center import generate_approval_link
    approvals = []
    for ro in (board.get("Customer Approval") or [])[:limit]:
        ro_id = ro.get("id")
        link = generate_approval_link(ro_id, actor)
        path = link.get("path") if isinstance(link, dict) and not link.get("error") else None
        body = ("Your service estimate is ready for your approval. "
                + (f"Review and approve it here: {path}. " if path else "")
                + "Reply here with any questions.")
        params = {"kind": "dvi_approval_request", "body": body, "approval_path": path}
        outcome = _run_outbound(worker, "service", "sms", "send_outbound_message", params, actor, ro_id)
        actions.append(outcome)
        approvals.append({"ro_id": ro_id, "approval_path": path, "status": outcome["status"]})

    return _queue_result(worker, "service", actions, {
        "ready_for_pickup": ready,
        "service_follow_ups": follow_ups,
        "approvals_requested": approvals,
    })


def _collections_queue(worker, actor, limit):
    """AI Collections Agent (BHPH): send a payment reminder for every past-due account in
    the real collections work queue. Every touch is logged (compliance) as a Communication
    plus an AiWorkerAction, and only informational reminders are ever sent -- never a
    financial or contractual action."""
    from core.collections import get_collection_queue

    reminders, actions = [], []
    queue = get_collection_queue()
    for loan in (queue.get("loans") or [])[:limit]:
        loan_id = loan.get("loan_id")
        name = loan.get("customer_name") or "there"
        dpd = loan.get("days_past_due")
        params = {"kind": "payment_reminder",
                  "body": f"Hi {name}, a friendly reminder that your account is "
                          f"{dpd} days past due. Please reach out to make a payment or set up "
                          "arrangements — we're here to help."}
        outcome = _run_outbound(worker, "collections", "sms", "send_outbound_message", params, actor, loan_id)
        actions.append(outcome)
        reminders.append({"loan_id": loan_id, "days_past_due": dpd, "status": outcome["status"]})

    return _queue_result(worker, "collections", actions, {"payment_reminders": reminders})


# The standard funding-document checklist the AI Finance Assistant collects (2026-07-24). The
# stips a real F&I office needs before a deal funds. draft_document_request is deliberately NOT
# a WORKER_SAFE_ACTION, so the checklist is always DRAFTED for a human to review/send.
_FINANCE_DOC_CHECKLIST = [
    "Government-issued photo ID (driver license)",
    "Proof of income (two most recent pay stubs)",
    "Proof of residence (utility bill or lease)",
    "Proof of insurance (declarations page)",
    "References (BHPH deals)",
]


def _finance_queue(worker, actor, limit):
    """AI Finance Assistant: send a funding-status update on every deal awaiting a lender
    decision (`deals.list_pending_financing`) -- keeping the customer informed while the
    application is out -- and DRAFT a personalized document-collection request (the F&I stips
    the deal still needs). Informational only; approving/funding stays a human action, and the
    document request always drafts for a human to send."""
    from core.deals import list_pending_financing

    updates, document_requests, actions = [], [], []
    for deal in list_pending_financing()[:limit]:
        deal_id = _entity_id(deal)
        params = {"kind": "funding_status_update",
                  "body": "Quick update on your financing: your application is with the lender. "
                          "We'll reach out the moment we have a decision — reply here with any questions."}
        outcome = _run_outbound(worker, "finance", "sms", "send_outbound_message", params, actor, deal_id)
        actions.append(outcome)
        updates.append({"deal_id": deal_id, "status": outcome["status"]})

        # A drafted document-collection request (always drafts -- never auto-sent).
        checklist = list(_FINANCE_DOC_CHECKLIST)
        doc_body = ("To finalize your financing, we still need a few documents: "
                    + "; ".join(checklist) + ". Reply here and I'll help you get them over.")
        doc_params = {"kind": "document_request", "body": doc_body, "checklist": checklist}
        doc_outcome = _run_outbound(worker, "finance", "email", "draft_document_request",
                                    doc_params, actor, deal_id)
        actions.append(doc_outcome)
        document_requests.append({"deal_id": deal_id, "checklist": checklist, "status": doc_outcome["status"]})

    return _queue_result(worker, "finance", actions,
                         {"funding_updates": updates, "document_requests": document_requests})


# The AI Marketing Agent proposes standard marketing assets each run. `draft_marketing_asset`
# is deliberately NOT on WORKER_SAFE_ACTIONS, so these ALWAYS draft for a human to review and
# publish -- the AI never sends marketing to customers on its own.
_MARKETING_ASSET_IDEAS = [
    ("re_engagement_email", "Re-engagement email to leads who've gone quiet in the last 30 days."),
    ("inventory_highlight_social", "Social post highlighting three aged units to help move them."),
    ("service_reminder_sms", "SMS campaign reminding customers who are due for service this month."),
]


# Real DRAFT campaigns the AI Marketing Agent materializes (2026-07-24). A draft Campaign
# (core/campaigns.py -- status "draft") sends NOTHING; it's a concrete, reviewable campaign a
# marketer publishes. Creating drafts never violates "the AI never publishes/sends on its own."
# Idempotent by name so repeated runs don't pile up duplicates.
_MARKETING_CAMPAIGN_DRAFTS = [
    ("retention", "AI Draft — Service Retention", "email", {"months_since_service": 6}),
    ("inventory_ads", "AI Draft — Inventory Conquest", "sms", {}),
    ("finance_renewal", "AI Draft — Finance Renewal / Payoff", "email", {"months_to_maturity": 3}),
]


def _marketing_queue(worker, actor, limit):
    """AI Marketing Agent: propose a set of marketing assets (always DRAFTED, never published)
    AND materialize real DRAFT Campaign entities (core/campaigns.py) a marketer can review and
    publish. A draft campaign sends nothing, so this never publishes/sends on its own."""
    asset_drafts, actions = [], []
    for asset_key, description in _MARKETING_ASSET_IDEAS[:limit]:
        params = {"kind": "marketing_asset", "asset": asset_key, "description": description}
        outcome = _run_outbound(worker, "marketing", "email", "draft_marketing_asset", params, actor, None)
        actions.append(outcome)
        asset_drafts.append({"asset": asset_key, "description": description, "status": outcome["status"]})

    # Create real draft campaigns (idempotent by name -- skip any that already exist).
    from core.campaigns import create_campaign
    from core.entity_types import CAMPAIGN
    existing_names = {e.attributes.get("name") for e in ledger.get_all().values()
                      if e.entity_type == CAMPAIGN}
    campaigns_drafted = []
    for type_key, name, channel, params in _MARKETING_CAMPAIGN_DRAFTS[:limit]:
        if name in existing_names:
            continue
        created = create_campaign(type_key, name, channel, actor, params)
        if isinstance(created, dict) and created.get("error"):
            continue
        cid = _entity_id(created)
        campaigns_drafted.append({"campaign_id": cid, "name": name, "type": type_key, "status": "draft"})

    return _queue_result(worker, "marketing", actions,
                         {"asset_drafts": asset_drafts, "campaigns_drafted": campaigns_drafted})


# ------------------------------------------------------------------------------------
# Digital Retail AI Workforce queues (2026-07-24, DR-7). Each composes a DR-1..6 module
# and sends an informational customer touch (send_outbound_message, a WORKER_SAFE_ACTION);
# nothing financial/contractual auto-executes -- the negotiation/finance/contract mutations
# still route through their own gated engines. The AI Product Specialist is inbound-only
# (real-time shopping questions via handle_interaction), like the Operator.
# ------------------------------------------------------------------------------------

def _trade_manager_queue(worker, actor, limit):
    """AI Trade Manager: for every deal carrying a customer-submitted trade that hasn't been
    appraiser-approved yet, send the customer a preliminary trade acknowledgement. The actual
    appraisal/ACV stays a human (or desk) action."""
    from core.entity_types import DEAL

    reviewed, actions = [], []
    deals_with_trade = [
        e for e in ledger.get_all().values()
        if e.entity_type == DEAL and isinstance(e.attributes.get("trade_in"), dict)
        and (e.attributes["trade_in"].get("vin") or e.attributes["trade_in"].get("mileage"))
        and not e.attributes["trade_in"].get("approved")
    ]
    for deal in deals_with_trade[:limit]:
        params = {"kind": "trade_acknowledgement",
                  "body": "Thanks for sending your trade details! Our team is reviewing your "
                          "vehicle now — you'll have a trade offer shortly. Any recent service "
                          "records or photos help us get you top dollar."}
        outcome = _run_outbound(worker, "trade_manager", "sms", "send_outbound_message", params, actor, deal.id)
        actions.append(outcome)
        reviewed.append({"deal_id": deal.id, "status": outcome["status"]})

    return _queue_result(worker, "trade_manager", actions, {"trades_acknowledged": reviewed})


def _negotiator_queue(worker, actor, limit):
    """AI Negotiator: nudge every OPEN negotiation session forward. Purely an informational
    touch -- any actual price/payment move still goes through core/negotiation_engine.py, which
    keeps it inside the dealer profit envelope and escalates anything outside it to a manager."""
    from core.negotiation_engine import list_sessions

    nudged, actions = [], []
    for session in list_sessions(status="active")["sessions"][:limit]:
        params = {"kind": "negotiation_nudge",
                  "body": "We're close! I've put together a payment option I think works for "
                          "you — take a look and let me know, and I'll do my best to get it "
                          "across the finish line within our approved numbers."}
        outcome = _run_outbound(worker, "negotiator", "sms", "send_outbound_message", params, actor,
                                session.get("deal_id"))
        actions.append(outcome)
        nudged.append({"session_id": session.get("id"), "deal_id": session.get("deal_id"),
                       "status": outcome["status"]})

    return _queue_result(worker, "negotiator", actions, {"negotiations_nudged": nudged})


def _delivery_coordinator_queue(worker, actor, limit):
    """AI Delivery Coordinator: send a status update on every in-flight delivery (scheduled /
    preparing / out for delivery). Advancing the delivery itself stays a human/ops action."""
    from core.delivery_fulfillment import list_deliveries

    in_flight = ("scheduled", "preparing", "out_for_delivery")
    updated, actions = [], []
    for d in list_deliveries()["deliveries"]:
        if d.get("status") not in in_flight:
            continue
        if len(updated) >= limit:
            break
        params = {"kind": "delivery_update",
                  "body": f"Delivery update: your vehicle is '{d.get('status').replace('_', ' ')}'. "
                          "We'll text you the moment it's on the way — reply here with any questions."}
        outcome = _run_outbound(worker, "delivery_coordinator", "sms", "send_outbound_message",
                                params, actor, d.get("deal_id") or d.get("customer_id"))
        actions.append(outcome)
        updated.append({"delivery_id": d.get("id"), "status": outcome["status"]})

    return _queue_result(worker, "delivery_coordinator", actions, {"deliveries_updated": updated})


def _ownership_concierge_queue(worker, actor, limit):
    """AI Ownership Concierge: welcome every recently-funded customer into ownership -- a
    service introduction + retention touch. Informational only."""
    from core.deals import list_deals

    welcomed, actions = [], []
    for deal in list_deals(status="funded")[:limit]:
        deal_id = _entity_id(deal)
        cust_id = deal.attributes.get("customer_id") if hasattr(deal, "attributes") else None
        params = {"kind": "ownership_welcome",
                  "body": "Congratulations on your new vehicle! I'm your ownership concierge — "
                          "I'll keep you on top of maintenance and warranty, and I'm here whenever "
                          "you need service. Welcome to the family!"}
        outcome = _run_outbound(worker, "ownership_concierge", "email", "send_outbound_message",
                                params, actor, cust_id or deal_id)
        actions.append(outcome)
        welcomed.append({"deal_id": deal_id, "status": outcome["status"]})

    return _queue_result(worker, "ownership_concierge", actions, {"owners_welcomed": welcomed})
