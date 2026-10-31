"""
core/bot_fleet.py — the agentic-bot FLEET (2026-07-23, Pillar 4 slice 1). Sam's
architectural pillar #4: scale NXTDeal's single agentic bot into "a fleet of team
agents that each record their team's workflows and can be admin-activated."

Today NXTDeal has ONE bot: core/bot_tasks.py generates per-section daily tasks,
core/bot_learning.py records per-employee act/dismiss signals, core/bot_coverage.py lets
an admin run the bot "as" one absent employee, core/bot_actions.py is the tiny safe
auto-action whitelist, core/bot_scheduler.py is the single background loop, and
core/bot_permissions.py is the default-deny capability layer. This module adds the
FLEET layer on top of those, without replacing any of them:

  * A **TeamAgent** — one per section (Sales/Service/Marketing/Inventory/Finance/
    Operations/Administration/Readiness/Network, the same nine sections the existing
    per-section task engine already serves). It is an ordinary graph entity (same single
    ledger as everything else — see Pillar 3's one-graph invariant, guarded by
    tests/test_single_graph_invariant.py), holding the team it represents, its
    activation status/mode, and who activated it — NOT a separate store.

  * **Workflow recording** — each team agent records its team's real, observed workflow
    steps (a TeamWorkflowEvent per step: who, which action, when, optionally a
    workflow_key delimiting one run) and derives the team's RECURRING multi-step
    workflows from them. Same honesty bar as core/bot_learning.py: this is real,
    explainable frequent-sequence mining over actually-recorded steps — a sequence is
    only surfaced as a "recognized workflow" once it has genuinely recurred
    (MIN_WORKFLOW_OCCURRENCES). Nothing is fabricated, and no passive behaviour is
    inferred; a step exists only because a caller explicitly recorded it.

Safety posture is inherited, not relaxed: activating a team agent in "auto" mode is
gated by the SAME default-deny core/bot_permissions.py capability
(`bot.coverage.auto_mode`, department scope) that core/bot_coverage.py's auto mode is —
so the fleet can never unattendedly do more than the existing whitelist already allows.
Slice 1 records workflows and manages activation state; it deliberately adds NO new
unattended mutation surface (team-agent auto-execution of derived workflows is future
work, and will still have to route through core/bot_actions.py's whitelist +
core/bot_permissions.py grants when it lands).
"""

from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import TEAM_AGENT, TEAM_WORKFLOW_EVENT, TEAM_AGENT_RUN
from core.audit import audit_log
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


MODE_DRAFT = "draft"
MODE_AUTO = "auto"
VALID_MODES = (MODE_DRAFT, MODE_AUTO)

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"

# The nine sections the existing per-section task engine (core/bot_tasks.py) already
# serves — one team agent each. Stored canonically lowercase; normalize_section() accepts
# any casing so a frontend passing "Sales" and a script passing "sales" hit the same agent.
FLEET_SECTIONS = (
    "sales",
    "service",
    "marketing",
    "inventory",
    "finance",
    "operations",
    "administration",
    "readiness",
    "network",
)

# A recorded step-sequence has to recur at least this many times across the team before
# it's surfaced as a "recognized workflow" rather than a one-off — the same "don't claim
# a pattern you haven't actually seen twice" honesty core/bot_learning.py applies to its
# suppression streak.
MIN_WORKFLOW_OCCURRENCES = 2

# Longest consecutive action sequence considered a single workflow (keeps the frequent-
# sequence mining bounded and the surfaced workflows human-readable).
_MAX_SEQUENCE_LEN = 4

# How many recorded steps back get_team_workflows() mines / shows, per team.
_LOOKBACK_STEPS = 500


def _now():
    return datetime.now(timezone.utc).isoformat()


def normalize_section(section):
    """Fold any-casing / surrounding whitespace to a canonical FLEET_SECTIONS key, or
    None if it isn't one of the nine real sections."""

    if not section:
        return None

    key = str(section).strip().lower()

    return key if key in FLEET_SECTIONS else None


def _display(section):
    return section[:1].upper() + section[1:]


# ------------------------------------------------------------------------------------
# TeamAgent entities — one per section, materialized lazily on first touch.
# ------------------------------------------------------------------------------------

def _find_agent(section):
    for entity in ledger.get_all().values():
        if entity.entity_type == TEAM_AGENT and entity.attributes.get("section") == section:
            return entity
    return None


def get_or_create_agent(section):
    """The TeamAgent entity for a canonical section, creating an inactive one on first
    use. Returns None for a non-fleet section. Persists only when it actually creates
    one (idempotent — safe to call on every read)."""

    section = normalize_section(section)
    if section is None:
        return None

    existing = _find_agent(section)
    if existing is not None:
        return existing

    agent = Entity(
        id=id_generator.generate("TAGT"),
        entity_type=TEAM_AGENT,
        attributes={
            "section": section,
            "display_name": f"{_display(section)} Team Agent",
            "status": STATUS_INACTIVE,
            "mode": MODE_DRAFT,
            "activated_by": None,
            "activated_at": None,
            "deactivated_by": None,
            "deactivated_at": None,
            "created_at": _now(),
        },
    )

    ledger.add_entity(agent)
    save_graph(GRAPH_PATH)

    return agent


def _agent_view(agent):
    section = agent.attributes.get("section")
    return dict(
        agent.attributes,
        id=agent.id,
        workflow_step_count=_step_count(section),
        recognized_workflow_count=len(_recognized_workflows(section)),
    )


def list_fleet():
    """Every one of the nine team agents (materializing any not created yet), each with
    its activation state plus how many workflow steps it has recorded and how many
    recurring workflows it has recognized so far."""

    return [_agent_view(get_or_create_agent(section)) for section in FLEET_SECTIONS]


def fleet_summary():
    fleet = list_fleet()
    return {
        "total_agents": len(fleet),
        "active_agents": sum(1 for a in fleet if a.get("status") == STATUS_ACTIVE),
        "auto_agents": sum(1 for a in fleet if a.get("status") == STATUS_ACTIVE and a.get("mode") == MODE_AUTO),
        "total_workflow_steps": sum(a.get("workflow_step_count", 0) for a in fleet),
        "total_recognized_workflows": sum(a.get("recognized_workflow_count", 0) for a in fleet),
    }


def activate_agent(section, mode, admin_id):
    """Admin-activate a team agent in draft or auto mode. Auto mode is gated by the same
    default-deny bot.coverage.auto_mode capability (department scope) as
    core/bot_coverage.py's auto mode — the fleet inherits that safety boundary rather
    than relaxing it."""

    section = normalize_section(section)
    if section is None:
        return {"error": "Unknown section -- must be one of the nine NXTDeal teams"}

    if mode not in VALID_MODES:
        return {"error": f"Unknown mode '{mode}' -- must be one of {VALID_MODES}"}

    if mode == MODE_AUTO:
        # Same gate core/bot_coverage.py's start_coverage() applies before an unattended
        # "auto" window — checked once at admin-click time so a denied request fails loud
        # here instead of silently activating an agent that could never actually act.
        from core.bot_permissions import is_capability_granted, normalize_department

        department = normalize_department(section)
        if not is_capability_granted("bot.coverage.auto_mode", department=department):
            return {
                "error": (
                    "Auto mode for this team agent is not granted"
                    + (f" for the {department} department" if department else "")
                    + " -- an ADMIN must grant the bot.coverage.auto_mode capability first "
                    "(Administration > Roles & Permissions > Bot Permissions)."
                )
            }

    agent = get_or_create_agent(section)

    agent.attributes["status"] = STATUS_ACTIVE
    agent.attributes["mode"] = mode
    agent.attributes["activated_by"] = admin_id
    agent.attributes["activated_at"] = _now()
    agent.attributes["deactivated_by"] = None
    agent.attributes["deactivated_at"] = None

    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="team_agent_activated",
        summary=f"{admin_id} activated the {_display(section)} team agent in {mode} mode",
        entity_id=agent.id,
        actor=admin_id,
        details={"section": section, "mode": mode},
    )

    return {"agent": _agent_view(agent)}


def deactivate_agent(section, admin_id):

    section = normalize_section(section)
    if section is None:
        return {"error": "Unknown section -- must be one of the nine NXTDeal teams"}

    agent = get_or_create_agent(section)

    agent.attributes["status"] = STATUS_INACTIVE
    agent.attributes["mode"] = MODE_DRAFT
    agent.attributes["deactivated_by"] = admin_id
    agent.attributes["deactivated_at"] = _now()

    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="team_agent_deactivated",
        summary=f"{admin_id} deactivated the {_display(section)} team agent",
        entity_id=agent.id,
        actor=admin_id,
        details={"section": section},
    )

    return {"agent": _agent_view(agent)}


# ------------------------------------------------------------------------------------
# Workflow recording + recurring-sequence derivation.
# ------------------------------------------------------------------------------------

def record_workflow_step(section, actor, action_key, step_label=None, workflow_key=None):
    """Record one real, observed step in a team's workflow. `action_key` is the stable
    key of what was done (e.g. "open_lead", "log_call", "advance_pipeline"); `actor` is
    the employee who did it; the optional `workflow_key` lets a caller delimit one
    discrete run of a multi-step workflow (steps sharing an (actor, workflow_key) form one
    sequence). Same shape as core/bot_learning.py's record_task_event — an ordinary
    graph entity, persisted, never a side store."""

    section = normalize_section(section)
    if section is None:
        return {"error": "Unknown section -- must be one of the nine NXTDeal teams"}

    if not action_key:
        return {"error": "action_key is required"}

    event = Entity(
        id=id_generator.generate("TWFE"),
        entity_type=TEAM_WORKFLOW_EVENT,
        attributes={
            "section": section,
            "actor": actor,
            "action_key": str(action_key),
            "step_label": step_label,
            "workflow_key": workflow_key,
            "recorded_at": _now(),
        },
    )

    ledger.add_entity(event)
    save_graph(GRAPH_PATH)

    return {"event_id": event.id, "section": section}


def _events_for(section):
    events = [
        e for e in ledger.get_all().values()
        if e.entity_type == TEAM_WORKFLOW_EVENT and e.attributes.get("section") == section
    ]
    events.sort(key=lambda e: e.attributes.get("recorded_at", ""))
    return events[-_LOOKBACK_STEPS:]


def _step_count(section):
    return len(_events_for(section))


def _sequences(section):
    """Group a team's recorded steps into ordered action-key sequences, one per
    (actor, workflow_key) — so two different employees, or two runs a caller tagged with
    different workflow_keys, are separate sequences and never spuriously chained."""

    groups = {}
    for event in _events_for(section):
        attrs = event.attributes
        key = (attrs.get("actor"), attrs.get("workflow_key"))
        groups.setdefault(key, []).append(attrs.get("action_key"))
    return list(groups.values())


def _recognized_workflows(section):
    """Frequent consecutive action-key sequences across the team, each seen at least
    MIN_WORKFLOW_OCCURRENCES times. Real frequent-sequence mining over recorded steps —
    an explainable count, not a model. A shorter sequence fully contained in a
    higher-or-equal-frequency longer one is dropped, so the surfaced set is the maximal
    recurring workflows rather than every sub-fragment."""

    counts = {}
    for sequence in _sequences(section):
        for length in range(2, min(_MAX_SEQUENCE_LEN, len(sequence)) + 1):
            for start in range(0, len(sequence) - length + 1):
                gram = tuple(sequence[start:start + length])
                if any(step is None for step in gram):
                    continue
                counts[gram] = counts.get(gram, 0) + 1

    qualifying = {gram: n for gram, n in counts.items() if n >= MIN_WORKFLOW_OCCURRENCES}

    # Drop any gram that is a contiguous sub-sequence of a longer qualifying gram with at
    # least the same occurrence count (it adds no information beyond the longer workflow).
    def _is_contiguous_subsequence(short, long_):
        n, m = len(short), len(long_)
        return any(long_[i:i + n] == short for i in range(0, m - n + 1))

    maximal = []
    for gram, n in qualifying.items():
        dominated = any(
            other is not gram
            and len(other) > len(gram)
            and qualifying[other] >= n
            and _is_contiguous_subsequence(gram, other)
            for other in qualifying
        )
        if not dominated:
            maximal.append((gram, n))

    maximal.sort(key=lambda item: (item[1], len(item[0])), reverse=True)

    return [
        {"steps": list(gram), "length": len(gram), "occurrences": n}
        for gram, n in maximal
    ]


def get_team_workflows(section):
    """The team agent's current picture of how its team works: the recognized recurring
    workflows plus honest transparency counts. Returns an "available: False" shape for a
    non-fleet section rather than raising."""

    section = normalize_section(section)
    if section is None:
        return {"available": False, "note": "Unknown section -- not one of the nine NXTDeal teams."}

    events = _events_for(section)
    distinct_actors = sorted({e.attributes.get("actor") for e in events if e.attributes.get("actor")})

    return {
        "available": True,
        "section": section,
        "display_name": f"{_display(section)} Team Agent",
        "step_count": len(events),
        "distinct_actors": distinct_actors,
        "recognized_workflows": _recognized_workflows(section),
        "recent_steps": [
            {
                "actor": e.attributes.get("actor"),
                "action_key": e.attributes.get("action_key"),
                "step_label": e.attributes.get("step_label"),
                "workflow_key": e.attributes.get("workflow_key"),
                "recorded_at": e.attributes.get("recorded_at"),
            }
            for e in events[-15:]
        ],
        "auto_execute_ready": _auto_execution_gate(section),
        "recent_runs": list_agent_runs(section, limit=5),
        "note": (
            "Recognized workflows are real recurring action sequences observed on this "
            f"team (each seen at least {MIN_WORKFLOW_OCCURRENCES} times) -- not fabricated, "
            "and only present once a pattern has actually repeated."
        ),
    }


# ------------------------------------------------------------------------------------
# Slice 4e: agentic AUTO-EXECUTION of a recognized workflow -- bounded, gated, drafted.
# ------------------------------------------------------------------------------------

# The ONLY workflow action_keys a team agent may EXECUTE unattended -- and even then only
# when its agent is active in auto mode, the Bot kill switch is on, and
# bot.fleet.auto_execute is granted. Ships EMPTY on purpose: every recognized workflow
# today is a real business mutation (desking a deal, advancing an RO, buying a car), none
# of which is safe to run unattended -- so every step DRAFTS for a human. Registering a key
# here is a deliberate, auditable human decision to let one specific safe action auto-run;
# this map is the single choke point, mirroring core/bot_actions.ACTION_HANDLERS for the
# existing single-bot surface. handler(section, actor, action_key, run_by) -> result dict.
FLEET_SAFE_ACTIONS = {}


def _auto_execution_gate(section):
    """Whether this section's agent may auto-EXECUTE a whitelisted safe step right now.
    ALL must hold: the agent is active in auto mode (its activation already passed the
    bot.coverage.auto_mode gate); the Bot kill switch is on; and bot.fleet.auto_execute is
    granted for the department. Re-checked at run time -- a grant can be revoked after
    activation -- exactly like core/bot_actions.run_action()'s own per-call re-check."""

    section = normalize_section(section)
    if section is None:
        return False

    agent = _find_agent(section)
    if agent is None:
        return False
    if agent.attributes.get("status") != STATUS_ACTIVE or agent.attributes.get("mode") != MODE_AUTO:
        return False

    from core.ai_kill_switch import is_bot_enabled
    if not is_bot_enabled():
        return False

    from core.bot_permissions import is_capability_granted, normalize_department
    department = normalize_department(section)
    return is_capability_granted("bot.fleet.auto_execute", department=department)


def _top_workflow(section):
    workflows = _recognized_workflows(section)
    return workflows[0] if workflows else None


def list_agent_runs(section, limit=10):
    """This section's recorded workflow runs (TeamAgentRun), newest first."""

    section = normalize_section(section)
    if section is None:
        return []

    runs = [
        e for e in ledger.get_all().values()
        if e.entity_type == TEAM_AGENT_RUN and e.attributes.get("section") == section
    ]
    runs.sort(key=lambda e: e.attributes.get("created_at", ""), reverse=True)
    return [dict(e.attributes, id=e.id) for e in runs[:limit]]


def run_recognized_workflow(section, admin_id):
    """Run the team agent's top recognized workflow (Pillar 4 slice 4e). For each step: if
    the agent may auto-execute (see _auto_execution_gate) AND the step's action_key is on
    FLEET_SAFE_ACTIONS, the safe handler runs and the step is marked 'executed'; otherwise
    the step is 'drafted' -- a suggestion a human still has to carry out. The run is
    persisted as a TeamAgentRun and audited. This adds NO business-mutation surface: with
    FLEET_SAFE_ACTIONS empty every step drafts, in any mode; a step can only ever execute
    something a human explicitly whitelisted."""

    section = normalize_section(section)
    if section is None:
        return {"error": "Unknown section -- must be one of the nine NXTDeal teams"}

    agent = _find_agent(section)
    if agent is None or agent.attributes.get("status") != STATUS_ACTIVE:
        return {"error": "The team agent for this section is not active -- activate it first."}

    workflow = _top_workflow(section)
    if workflow is None:
        return {"error": "This agent has not recognized a recurring workflow yet -- nothing to run."}

    can_auto = _auto_execution_gate(section)
    mode = MODE_AUTO if can_auto else MODE_DRAFT

    steps = []
    executed = 0
    drafted = 0
    for action_key in workflow["steps"]:
        handler = FLEET_SAFE_ACTIONS.get(action_key) if can_auto else None
        if handler is not None:
            try:
                result = handler(section, agent.attributes.get("section"), action_key, admin_id)
                status = "executed"
                executed += 1
            except Exception as exc:  # a safe handler failing must never abort the run
                result = {"error": str(exc)}
                status = "drafted"
                drafted += 1
        else:
            result = None
            status = "drafted"
            drafted += 1
        steps.append({"action_key": action_key, "status": status, "result": result})

    run = Entity(
        id=id_generator.generate("TAGR"),
        entity_type=TEAM_AGENT_RUN,
        attributes={
            "section": section,
            "mode": mode,
            "workflow": list(workflow["steps"]),
            "steps": steps,
            "executed_count": executed,
            "drafted_count": drafted,
            "run_by": admin_id,
            "created_at": _now(),
        },
    )
    ledger.add_entity(run)
    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="team_agent_workflow_run",
        summary=(
            f"{admin_id} ran the {_display(section)} team agent's recognized workflow "
            f"({executed} executed, {drafted} drafted, mode={mode})"
        ),
        entity_id=run.id,
        actor=admin_id,
        details={"section": section, "mode": mode, "executed": executed, "drafted": drafted},
    )

    return {
        "run_id": run.id,
        "section": section,
        "mode": mode,
        "workflow": list(workflow["steps"]),
        "steps": steps,
        "executed_count": executed,
        "drafted_count": drafted,
        "note": (
            "Steps are 'drafted' (a suggestion for a human) unless the agent is active in "
            "auto mode with bot.fleet.auto_execute granted AND the step is on the fleet "
            "safe-action whitelist -- which ships empty, so real business steps never run "
            "unattended."
        ),
    }
