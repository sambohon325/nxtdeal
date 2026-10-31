"""
core/execution_modes.py -- NXTDeal execution modes (Digital Retail slice DR-2, 2026-07-24).
Sam's Digital Retail spec: "Every workflow in NXTDeal must support: Human, AI, Customer,
Hybrid." The same Sales / Finance / Operations workflows can be executed by a human employee,
by the AI Workforce, by the customer themselves (self-service), or by a mix -- and the dealer
decides, per workflow, which is active.

This is NOT the same thing as core/ai_execution_tier.py, which classifies AI AUTONOMY
(informational / assisted / autonomous -- "does a human review before it takes effect?").
This module answers a different question: WHO is permitted to drive a workflow -- a human, an
AI worker, or the customer. Both governance layers compose; neither replaces the other.

It's a thin configuration + gate layer, not an executor. A per-dealer singleton
ExecutionPolicy entity (prefix XPOL) holds the active mode for each workflow; other modules
call `require_actor(workflow_key, actor_kind)` to check whether a given actor may proceed
(e.g. DR-4's self-service deal flow asks require_actor("desking", "customer") before letting a
verified customer build a deal). Humans are never locked out of their own dealership -- every
mode still permits a human actor; the mode only governs whether AI and/or the CUSTOMER are
additionally enabled.
"""

from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import EXECUTION_POLICY
from core.audit import audit_log
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# ------------------------------------------------------------------------------------
# Actors and modes.
# ------------------------------------------------------------------------------------

ACTOR_HUMAN = "human"
ACTOR_AI = "ai"
ACTOR_CUSTOMER = "customer"
ACTOR_KINDS = (ACTOR_HUMAN, ACTOR_AI, ACTOR_CUSTOMER)

MODE_HUMAN = "human"
MODE_AI = "ai"
MODE_CUSTOMER = "customer"
MODE_HYBRID = "hybrid"
ALL_MODES = (MODE_HUMAN, MODE_AI, MODE_CUSTOMER, MODE_HYBRID)

MODE_LABELS = {
    MODE_HUMAN: "Human",
    MODE_AI: "AI",
    MODE_CUSTOMER: "Customer",
    MODE_HYBRID: "Hybrid",
}

# Which actors a mode PERMITS. A human employee may always act on their own dealership's
# workflow -- the mode governs whether AI and/or the customer are ADDITIONALLY enabled -- so
# every mode includes the human actor. Hybrid opens all three.
MODE_ALLOWED_ACTORS = {
    MODE_HUMAN: (ACTOR_HUMAN,),
    MODE_AI: (ACTOR_HUMAN, ACTOR_AI),
    MODE_CUSTOMER: (ACTOR_HUMAN, ACTOR_CUSTOMER),
    MODE_HYBRID: (ACTOR_HUMAN, ACTOR_AI, ACTOR_CUSTOMER),
}

# ------------------------------------------------------------------------------------
# The workflow catalog -- which modes each workflow SUPPORTS, and its conservative default.
# Per Sam's spec: most workflows support all four; Lead Management omits Customer (a lead is
# not a self-service purchase step). Defaults are HUMAN everywhere -- nothing silently runs as
# AI or self-service until the dealer explicitly turns it on.
# ------------------------------------------------------------------------------------

_ALL4 = (MODE_HUMAN, MODE_AI, MODE_CUSTOMER, MODE_HYBRID)
_HUMAN_AI = (MODE_HUMAN, MODE_AI, MODE_HYBRID)

WORKFLOW_CATALOG = {
    "lead_management": {
        "label": "Lead Management",
        "description": "Capturing, routing, and following up on leads.",
        "supported_modes": _HUMAN_AI,
    },
    "desking": {
        "label": "Desking",
        "description": "Building deal scenarios (price, down payment, term, payment).",
        "supported_modes": _ALL4,
    },
    "negotiation": {
        "label": "Negotiation",
        "description": "Price / payment discussions within dealer-approved ranges.",
        "supported_modes": _ALL4,
    },
    "trade": {
        "label": "Trade Appraisal",
        "description": "Trade-in evaluation, VIN decode, condition, and offer.",
        "supported_modes": _ALL4,
    },
    "credit": {
        "label": "Credit Application",
        "description": "Applicant intake, credit application, and lender matching.",
        "supported_modes": _ALL4,
    },
    "fi": {
        "label": "F&I",
        "description": "Presenting and deciding F&I products (VSC/GAP/etc.).",
        "supported_modes": _ALL4,
    },
    "contracting": {
        "label": "Contracting",
        "description": "Contract preparation and e-signature.",
        "supported_modes": _ALL4,
    },
    "delivery": {
        "label": "Delivery",
        "description": "Delivery / pickup scheduling and coordination.",
        "supported_modes": _ALL4,
    },
    "service": {
        "label": "Service",
        "description": "Service scheduling, updates, and ownership follow-up.",
        "supported_modes": _HUMAN_AI,
    },
}

DEFAULT_MODE = MODE_HUMAN


def _now():
    return datetime.now(timezone.utc).isoformat()


def normalize_workflow(workflow_key):
    if not workflow_key:
        return None
    key = str(workflow_key).strip().lower()
    return key if key in WORKFLOW_CATALOG else None


def normalize_mode(mode):
    if not mode:
        return None
    m = str(mode).strip().lower()
    return m if m in ALL_MODES else None


def supported_modes(workflow_key):
    entry = WORKFLOW_CATALOG.get(workflow_key)
    return list(entry["supported_modes"]) if entry else []


# ------------------------------------------------------------------------------------
# The per-dealer singleton policy entity.
# ------------------------------------------------------------------------------------

def _find_policy():
    for entity in ledger.get_all().values():
        if entity.entity_type == EXECUTION_POLICY:
            return entity
    return None


def get_or_create_policy():
    existing = _find_policy()
    if existing is not None:
        return existing
    policy = Entity(
        id=id_generator.generate("XPOL"),
        entity_type=EXECUTION_POLICY,
        attributes={
            "modes": {k: DEFAULT_MODE for k in WORKFLOW_CATALOG},
            "updated_by": None,
            "updated_at": _now(),
            "created_at": _now(),
            "history": [],
        },
    )
    ledger.add_entity(policy)
    save_graph(GRAPH_PATH)
    return policy


def _active_mode(policy, workflow_key):
    return policy.attributes.get("modes", {}).get(workflow_key, DEFAULT_MODE)


def set_execution_mode(workflow_key, mode, admin_id):
    """Set the active execution mode for one workflow. Rejects a mode the workflow doesn't
    support (e.g. Customer mode on Lead Management)."""
    wf = normalize_workflow(workflow_key)
    if wf is None:
        return {"error": f"Unknown workflow '{workflow_key}'"}
    m = normalize_mode(mode)
    if m is None:
        return {"error": f"Unknown mode '{mode}' -- must be one of {list(ALL_MODES)}"}
    if m not in WORKFLOW_CATALOG[wf]["supported_modes"]:
        return {"error": f"{WORKFLOW_CATALOG[wf]['label']} does not support "
                         f"{MODE_LABELS[m]} mode (supported: {supported_modes(wf)})"}

    policy = get_or_create_policy()
    previous = _active_mode(policy, wf)
    policy.attributes["modes"][wf] = m
    policy.attributes["updated_by"] = admin_id
    policy.attributes["updated_at"] = _now()
    policy.attributes["history"].append(
        {"at": _now(), "workflow": wf, "from": previous, "to": m, "by": admin_id}
    )
    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="execution_mode_changed",
        summary=f"{admin_id} set {WORKFLOW_CATALOG[wf]['label']} to {MODE_LABELS[m]} mode",
        entity_id=policy.id,
        actor=admin_id,
        details={"workflow": wf, "from": previous, "to": m},
    )
    return {"workflow": _workflow_view(policy, wf)}


# ------------------------------------------------------------------------------------
# The gate other modules call.
# ------------------------------------------------------------------------------------

def allowed_actors(workflow_key):
    """The actor kinds permitted by the workflow's currently-active mode."""
    wf = normalize_workflow(workflow_key)
    if wf is None:
        return ()
    policy = get_or_create_policy()
    return MODE_ALLOWED_ACTORS[_active_mode(policy, wf)]


def actor_allowed(workflow_key, actor_kind):
    return actor_kind in allowed_actors(workflow_key)


def require_actor(workflow_key, actor_kind):
    """Gate for OTHER modules: returns (ok, error). Fails closed on an unknown workflow or
    actor. The error names the workflow's active mode so the caller can explain the block."""
    wf = normalize_workflow(workflow_key)
    if wf is None:
        return False, f"Unknown workflow '{workflow_key}'"
    if actor_kind not in ACTOR_KINDS:
        return False, f"Unknown actor '{actor_kind}' -- must be one of {list(ACTOR_KINDS)}"
    policy = get_or_create_policy()
    mode = _active_mode(policy, wf)
    if actor_kind in MODE_ALLOWED_ACTORS[mode]:
        return True, None
    return False, (
        f"{WORKFLOW_CATALOG[wf]['label']} is in {MODE_LABELS[mode]} mode -- "
        f"a {actor_kind} actor may not drive it"
    )


# ------------------------------------------------------------------------------------
# Views / listings / summary.
# ------------------------------------------------------------------------------------

def _workflow_view(policy, workflow_key):
    entry = WORKFLOW_CATALOG[workflow_key]
    mode = _active_mode(policy, workflow_key)
    return {
        "key": workflow_key,
        "label": entry["label"],
        "description": entry["description"],
        "supported_modes": list(entry["supported_modes"]),
        "active_mode": mode,
        "active_mode_label": MODE_LABELS[mode],
        "allowed_actors": list(MODE_ALLOWED_ACTORS[mode]),
        "ai_enabled": ACTOR_AI in MODE_ALLOWED_ACTORS[mode],
        "customer_enabled": ACTOR_CUSTOMER in MODE_ALLOWED_ACTORS[mode],
    }


def list_workflows():
    policy = get_or_create_policy()
    return {
        "workflows": [_workflow_view(policy, k) for k in WORKFLOW_CATALOG],
        "modes": [{"mode": m, "label": MODE_LABELS[m],
                   "allowed_actors": list(MODE_ALLOWED_ACTORS[m])} for m in ALL_MODES],
    }


def get_workflow(workflow_key):
    wf = normalize_workflow(workflow_key)
    if wf is None:
        return {"error": f"Unknown workflow '{workflow_key}'"}
    return _workflow_view(get_or_create_policy(), wf)


def execution_summary():
    policy = get_or_create_policy()
    by_mode = {m: 0 for m in ALL_MODES}
    ai_enabled = 0
    customer_enabled = 0
    for k in WORKFLOW_CATALOG:
        mode = _active_mode(policy, k)
        by_mode[mode] += 1
        if ACTOR_AI in MODE_ALLOWED_ACTORS[mode]:
            ai_enabled += 1
        if ACTOR_CUSTOMER in MODE_ALLOWED_ACTORS[mode]:
            customer_enabled += 1
    return {
        "total_workflows": len(WORKFLOW_CATALOG),
        "by_mode": by_mode,
        "ai_enabled_workflows": ai_enabled,
        "customer_enabled_workflows": customer_enabled,
    }
