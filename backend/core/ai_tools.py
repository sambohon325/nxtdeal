"""
Phase 11 wrap-up — graph-traversal tools for the AI assistant (core/ai_assistant.py).
Gives ask_ai() real OpenAI function-calling access to the ledger/repository, instead of
only the pre-built dashboard functions core/ai_api.py's ask() already fast-paths to
(workload/leaderboard/escalation keyword shortcuts) or a single free-text question with
no data access at all.

Every tool here is read-only and enforces the same core/security.py can_access_entity()
role check Phase 9 wired into GET /search, GET /entity/{id}, and POST /question — the
assistant must not become a way to read data a role couldn't otherwise see through the
regular API. `role` is threaded in from core/ai_api.py's ask(), which gets it from the
authenticated token payload in api/app.py's /ai/chat — never from the model or from
tool-call arguments, so a prompt can't talk its way past the access check.

IMPORTANT data-flow note (flagged to Sam, see BUILD_QUEUE.md Phase 11): once a tool is
called, whatever entity data it returns (which can include customer PII and finance
contract details) gets sent to OpenAI as part of the conversation, not just the user's
free-text question like before this change. Same third-party exposure as any OpenAI
tool-calling integration — worth keeping in mind for GLBA/PII-handling purposes.

Workflow Engine v2 — AI workflow awareness: get_workflow_instance_status/
list_workflow_instances/get_workflow_dashboard/get_stalled_workflow_instances give the
assistant real, read-only visibility into core/workflow_engine_v2.py's real workflow
instances — Operations' original 21-workflow pilot catalog plus Sales' own 18-workflow
lifecycle catalog (Prospecting/Engagement/Deals/Finance/Retention), added session
2026-07-21 — across whichever department a given instance belongs to (current step,
next step, blocked steps + reasons, pending approvals, open tasks, suggested next
actions, SLA-stalled instances). Department is derived from the instance's own
workflow key (e.g. "sales.desking_v2" -> "Sales"), never hardcoded to one department,
so these 4 tools need no further change as more departments migrate onto this engine.
Same underlying ACL as everything else in this module (core/workflow_engine_v2_api.py's
own _VIEW_ROLES), just read through this module's role-first call_tool() boundary like
every other tool here. These are query-only: the assistant can see and describe a
workflow instance's real state, it cannot advance/block/approve/escalate one — those
stay real human (or Bot-Automation-tier) actions taken through the Step Progression UI
or core/bot_actions.py, not something a chat message can trigger.
"""

from core.queries import (
    search_graph,
    get_entity_relationships,
)
from core.repository import repository
from core.security import can_access_entity
from core.workflow_engine_v2_api import (
    get_dashboard_v2_api,
    get_instance_ai_state_api,
    get_stalled_instances_v2_api,
    list_instances_v2_api,
)


def _serialize_entity(entity):

    return {
        "id": entity.id,
        "entity_type": entity.entity_type,
        "attributes": entity.attributes,
    }


def search_entities(role, query):
    """Search the graph by free-text query, same as GET /search — results filtered to
    entity types `role` is allowed to see. Capped at 20 results to keep tool output small
    (it feeds back into the model's context on every round)."""

    results = search_graph(query)

    return [
        _serialize_entity(entity)
        for entity in results
        if can_access_entity(role, entity.entity_type)
    ][:20]


def get_entity_by_id(role, entity_id):
    """Look up a single entity by its exact ID, same access rule as GET /entity/{id}."""

    entity = repository.get_entity(entity_id)

    if not entity:

        return {"error": "Entity not found"}

    if not can_access_entity(role, entity.entity_type):

        return {"error": "Forbidden: your role cannot access this entity type"}

    return _serialize_entity(entity)


def get_related_entities(role, entity_id):
    """List entities directly connected (one hop) to entity_id, filtered per related
    entity's type. Lets the assistant answer things like 'what vehicles does this
    customer own' or 'who financed this contract' without a purpose-built dashboard for
    every possible traversal."""

    relationships = get_entity_relationships(entity_id)

    results = []

    for relationship in relationships:

        other_id = (
            relationship.target_id
            if relationship.source_id == entity_id
            else relationship.source_id
        )

        other = repository.get_entity(other_id)

        if not other:
            continue

        if not can_access_entity(role, other.entity_type):
            continue

        results.append({
            "relationship_type": relationship.relationship_type,
            "entity": _serialize_entity(other),
        })

    return results[:20]


def get_workflow_instance_status(role, instance_id):
    """The real AI-facing state of one v2 workflow instance -- Operations' original
    ~21-workflow catalog (Vehicle Intake, Recon, Deal Jacket Audit, etc.) or Sales'
    18-workflow lifecycle catalog (Lead Management, Desking, Trade Appraisal, etc.) --
    current_step, next_step, every blocked step with its reason, any approval still
    waiting on a decision, open tasks surfaced as missing_information, and a real list
    of suggested_actions. This is the exact same payload core/workflow_engine_v2.py's
    get_instance_ai_state() computes for the Step Progression UI -- call this whenever
    the user asks about a specific workflow instance's status, what's blocking it, or
    what to do next, so you can answer with the real current/next step and real
    blockers instead of guessing. Department is derived from the instance's own
    workflow key, so this works the same regardless of which department it belongs
    to."""

    return get_instance_ai_state_api(role, instance_id)


def list_workflow_instances(role, department=None, workflow_key=None, status=None, category=None):
    """List real, active v2 workflow instances across whichever department they
    belong to -- Operations (Vehicle Intake, Recon, Merchandising, Deal Jacket Audit,
    Title Exception, Interdepartment SLA, New Employee Onboarding, etc.) or Sales
    (Lead Management, BDC Workflow, Appointment Workflow, Showroom Workflow, Trade
    Appraisal, Desking, Credit Application, F&I Handoff, Delivery Experience, Equity
    Mining, etc.), optionally filtered by department, a specific workflow_key, status
    (not_started/in_progress/blocked/waiting_approval/completed/escalated), or
    category. Operations' categories are vehicle/compliance/operational/employee;
    Sales' categories are prospecting/engagement/deals/finance/retention. Use this to
    find which real instances exist before asking about one by ID, or to answer a
    broad question like "what Sales workflows are blocked right now" (pass
    department='Sales', status='blocked')."""

    return list_instances_v2_api(
        role,
        department=department,
        workflow_key=workflow_key,
        status=status,
        category=category,
    )


def get_workflow_dashboard(role, department=None):
    """The real Workflow Dashboard for a department (Operations or Sales) -- every v2
    workflow definition for that department (even ones with zero active instances
    right now) alongside its real active-instance counts broken down by status
    (in_progress/blocked/waiting_approval/escalated). Omit department to see every
    department's workflows at once. Use this to answer a broad question like "how many
    recon workflows are in progress" or "what Sales workflows have escalations right
    now" across a whole department, rather than one instance at a time."""

    return get_dashboard_v2_api(role, department=department)


def get_stalled_workflow_instances(role, department=None):
    """Real v2 workflow instances (any department -- Operations or Sales) that are
    past their current step's SLA and have not advanced -- the proactive "surface
    blockers before being asked" signal the workflow engine tracks. Call this when the
    user asks what's falling behind, what needs attention, or what's overdue in a
    department's workflows, so you can proactively name the real stalled instances
    rather than waiting to be asked about each one by ID."""

    return get_stalled_instances_v2_api(role, department=department)


def list_report_sources(role):
    """List every Top Menu item across all 9 departments the model can build a chat-
    requested report from (e.g. "build me a report on service revenue") -- the same
    department/item_key catalog backing each department's Reporting tab
    (core/menu_catalog.py). Call this before get_department_data/propose_report so the
    model picks a real department+item_key pair instead of guessing one.

    Lazy-imports core.menu_catalog rather than importing it at module load time:
    core.menu_data.py (which this module's get_department_data also lazy-imports)
    pulls in core.operations_menu and its per-department siblings, several of which
    themselves `from core.ai_tools import search_entities, get_entity_by_id,
    get_related_entities` at THEIR module level -- importing core.menu_data (or
    anything that transitively imports it) at the top of this file would deadlock that
    cycle the moment Python tries to load core.ai_tools itself. Importing inside the
    function body instead defers it until after every module involved has already
    finished loading, which is safe."""

    from core.menu_catalog import MENU_CATALOG

    return {
        department: [
            {
                "item_key": item["key"],
                "label": item["label"],
                "description": item.get("description", ""),
            }
            for item in items
        ]
        for department, items in MENU_CATALOG.items()
    }


def get_department_data(role, department, item_key):
    """Fetch the real data behind one Top Menu item -- the same data GET /menu/data
    serves, role-gated the same way (each core/*_menu.py fetch function checks `role`
    itself). Use this to see the actual shape/fields of a department's data before
    calling propose_report with a field_path/label_column/numeric_columns guess -- see
    list_report_sources' docstring for why this is a lazy import."""

    from core.menu_data import get_menu_data

    return get_menu_data(role, department, item_key)


def _resolve_field_path(data, field_path):
    """Walks `data` down a list of object keys / array indices to the array-of-objects
    being charted -- same logic as frontend/lib/useVisualizationWorkspace.ts's
    resolveFieldPath, kept in sync deliberately since both are re-deriving the same
    array from the same GET /menu/data shape."""

    current = data

    for key in field_path:
        if isinstance(current, list):
            try:
                current = current[int(key)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(key)
        else:
            return None

    if isinstance(current, list) and all(isinstance(row, dict) for row in current):
        return current

    return None


def propose_report(
    role,
    department,
    item_key,
    source_label,
    field_path,
    label_column,
    numeric_columns,
    chart_type="bar",
):
    """The model's final step when building a chat-requested report -- hands back a
    chart configuration NXTDeal can drop straight onto the user's Workspace board as a
    live chart + AI-written note. Re-fetches the real data live and checks
    field_path/label_column/numeric_columns actually resolve against it rather than
    trusting the model's fields blindly -- same 'always real data, never a fabricated
    precise-looking number' rule the rest of this codebase follows (see
    core/workflow_tab_data.py's REAL_SOURCES for the established precedent). A rejected
    call returns {"error": ...} so the model can inspect the real available fields and
    retry rather than silently emitting a broken suggestion."""

    from core.menu_catalog import get_department_menu

    items = get_department_menu(department)

    if not any(item["key"] == item_key for item in items):
        return {"error": f"Unknown menu item '{item_key}' for department '{department}'"}

    data = get_department_data(role, department, item_key)

    if isinstance(data, dict) and data.get("error"):
        return {"error": data["error"]}

    field_path = [str(p) for p in field_path] if isinstance(field_path, list) else []
    rows = _resolve_field_path(data, field_path)

    if rows is None:
        return {
            "error": (
                f"field_path {field_path} did not resolve to a list of records for "
                f"{department}/{item_key} -- call get_department_data first and pick a "
                "real array field."
            )
        }

    if not rows:
        return {"error": "That data set is currently empty -- nothing to chart."}

    sample_keys = set()
    for row in rows[:5]:
        sample_keys.update(row.keys())

    if label_column not in sample_keys:
        return {
            "error": f"label_column '{label_column}' not found -- available fields: {sorted(sample_keys)}"
        }

    numeric_columns = [c for c in numeric_columns if isinstance(c, str)] if isinstance(numeric_columns, list) else []
    bad_columns = [c for c in numeric_columns if c not in sample_keys]

    if bad_columns:
        return {
            "error": f"numeric_columns not found: {bad_columns} -- available fields: {sorted(sample_keys)}"
        }

    if not numeric_columns:
        return {"error": "numeric_columns can't be empty -- pick at least one real numeric field."}

    if chart_type not in ("bar", "line", "pie"):
        chart_type = "bar"

    return {
        "ok": True,
        "department": department,
        "item_key": item_key,
        "source_label": source_label if isinstance(source_label, str) and source_label.strip() else item_key,
        "field_path": field_path,
        "label_column": label_column,
        "numeric_columns": numeric_columns,
        "chart_type": chart_type,
        "row_count": len(rows),
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_entities",
            "description": (
                "Search NXTDeal's graph (customers, vehicles, leads, finance contracts, "
                "lenders, service records, documents, images) by free-text query, e.g. a "
                "customer name or VIN."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search term.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_by_id",
            "description": (
                "Look up a single NXTDeal entity by its exact ID "
                "(e.g. CUS-00001, VEH-00042)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The exact entity ID.",
                    }
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_entities",
            "description": (
                "List entities directly connected to a given entity ID — e.g. the "
                "vehicles a customer owns, the finance contract covering a vehicle, or "
                "the service records tied to a vehicle."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The exact entity ID to find connections for.",
                    }
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workflow_instance_status",
            "description": (
                "Get the real current status of one v2 workflow instance, from any "
                "department using the v2 engine (e.g. Operations' Vehicle Intake, "
                "Recon, or Deal Jacket Audit, or Sales' Desking, Trade Appraisal, or "
                "Credit Application; ID like WF2-00001): its current step, next step, "
                "any blocked steps and why, any approval waiting on a decision, open "
                "tasks, and concrete suggested next actions. Call this whenever the "
                "user asks about a specific workflow instance's status or what's "
                "blocking it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instance_id": {
                        "type": "string",
                        "description": "The exact workflow instance ID, e.g. WF2-00001.",
                    }
                },
                "required": ["instance_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_workflow_instances",
            "description": (
                "List real active v2 workflow instances across any department using "
                "the v2 engine (Operations or Sales), optionally filtered by "
                "department, workflow_key, status (not_started/in_progress/blocked/"
                "waiting_approval/completed/escalated), or category. Operations' "
                "categories are vehicle/compliance/operational/employee; Sales' "
                "categories are prospecting/engagement/deals/finance/retention. Use "
                "this to find which real instances exist, or to answer a broad "
                "question like 'what Sales workflows are blocked right now' by "
                "filtering on department and status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "e.g. 'Operations' or 'Sales'."},
                    "workflow_key": {
                        "type": "string",
                        "description": "e.g. 'operations.vehicle_intake_v2' or 'sales.desking_v2'.",
                    },
                    "status": {
                        "type": "string",
                        "enum": [
                            "not_started",
                            "in_progress",
                            "blocked",
                            "waiting_approval",
                            "completed",
                            "escalated",
                        ],
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "vehicle",
                            "compliance",
                            "operational",
                            "employee",
                            "prospecting",
                            "engagement",
                            "deals",
                            "finance",
                            "retention",
                        ],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workflow_dashboard",
            "description": (
                "The real Workflow Dashboard for a department (Operations or Sales): "
                "every workflow definition for that department with its real "
                "active-instance counts by status. Omit department to see every "
                "department's workflows at once. Use this to answer a broad question "
                "like 'how many recon workflows are in progress' or 'what Sales "
                "workflows have escalations right now' across a whole department."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "e.g. 'Operations' or 'Sales'."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stalled_workflow_instances",
            "description": (
                "Real v2 workflow instances (any department -- Operations or Sales) "
                "that are past their current step's SLA and haven't advanced -- "
                "proactively surface these when the user asks what's falling behind, "
                "overdue, or needs attention in a department's workflows."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "e.g. 'Operations' or 'Sales'."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_report_sources",
            "description": (
                "List every real department + Top Menu item NXTDeal can build a chart-"
                "ready report from (e.g. Sales/reporting, Service/repair_orders, "
                "Finance/funding). Call this FIRST when the user asks you to build, "
                "chart, graph, or pull numbers for a report — pick the closest matching "
                "department/item_key from here rather than guessing one."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_department_data",
            "description": (
                "Fetch the real data behind one Top Menu item (a department + item_key "
                "pair from list_report_sources). Inspect the returned JSON to find the "
                "array of records to chart and which fields on it are the label vs. the "
                "numeric values, then call propose_report."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "e.g. 'Sales', 'Service', 'Finance'."},
                    "item_key": {"type": "string", "description": "e.g. 'reporting', 'repair_orders', 'funding'."},
                },
                "required": ["department", "item_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_report",
            "description": (
                "Final step for a chat-requested report: hand back a validated chart "
                "configuration so NXTDeal can drop a live, editable chart onto the "
                "user's Workspace board along with an explanatory note. Only call this "
                "after get_department_data — field_path/label_column/numeric_columns "
                "must be real fields you actually saw in that response, not guesses."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string"},
                    "item_key": {"type": "string"},
                    "source_label": {
                        "type": "string",
                        "description": "A short human title for the chart, e.g. 'Service Revenue by Month'.",
                    },
                    "field_path": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Object keys (and/or array indices, as strings) from the "
                            "get_department_data response root down to the array of "
                            "records to chart, e.g. ['repair_orders']."
                        ),
                    },
                    "label_column": {
                        "type": "string",
                        "description": "Which field on each record to use as the chart's category label.",
                    },
                    "numeric_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Which numeric field(s) on each record to plot.",
                    },
                    "chart_type": {
                        "type": "string",
                        "enum": ["bar", "line", "pie"],
                    },
                },
                "required": ["department", "item_key", "source_label", "field_path", "label_column", "numeric_columns"],
            },
        },
    },
]


DISPATCH = {
    "search_entities": search_entities,
    "get_entity_by_id": get_entity_by_id,
    "get_related_entities": get_related_entities,
    "get_workflow_instance_status": get_workflow_instance_status,
    "list_workflow_instances": list_workflow_instances,
    "get_workflow_dashboard": get_workflow_dashboard,
    "get_stalled_workflow_instances": get_stalled_workflow_instances,
    "list_report_sources": list_report_sources,
    "get_department_data": get_department_data,
    "propose_report": propose_report,
}


def call_tool(name, role, arguments):
    """Dispatch a single tool call by name. `role` is a positional trust boundary — it
    always comes from the authenticated caller (see module docstring), never from
    `arguments`, which is model/user-controlled."""

    func = DISPATCH.get(name)

    if not func:

        return {"error": f"Unknown tool '{name}'"}

    return func(role, **arguments)
