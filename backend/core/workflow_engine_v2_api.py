"""
Thin ACL layer over core/workflow_engine_v2.py, matching this codebase's established
"*_api.py" convention (validate role, call the real function, flatten the raw Entity
into a plain {id, **attributes} dict for the API boundary -- core/operations_tasks_api.py's
own _serialize() docstring documents exactly why this flattening step matters: FastAPI's
default JSON encoding otherwise serializes a raw Entity as {"id", "entity_type",
"attributes": {...}}, one level deeper than every frontend consumer expects).

Role split matches core/operations_tasks_api.py's own precedent for this exact
department -- viewing is broad (every department genuinely cares whether a real v2
workflow instance touching their own work is blocked/stalled/escalated), mutating
(starting/advancing/blocking/approving/escalating/force-closing an instance, or
adding a task/evidence/comment to one) is ADMIN/OPERATIONS/SALES/SERVICE. SALES was
added alongside the Sales Workflow Engine v2 rollout (Prospecting/Engagement/Deals/
Finance/Retention) -- Sales reps need to be able to work their own Lead Management/
Desking/Trade Appraisal/etc. instances directly, matching core/deals_api.py's own
established "SALES can desk a deal" convention. Vehicle Lifecycle/Operations Tasks'
own ADMIN/OPERATIONS/SERVICE set is unchanged elsewhere; this module's engine is
shared across every department that's been migrated onto it (department is derived
from the workflow_key's own "<department>." prefix, e.g. "operations."/"sales.").
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.workflow_definitions_v2 import list_workflow_defs_v2, get_workflow_def_v2
from core.workflow_engine_v2 import (
    INSTANCE_STATUSES,
    STEP_STATUSES,
    start_workflow_instance_v2,
    advance_step,
    add_step_task,
    complete_step_task,
    add_step_evidence,
    add_step_comment,
    block_step,
    unblock_step,
    request_step_approval,
    decide_step_approval,
    escalate_instance,
    resolve_escalation,
    force_close_instance,
    list_instances_v2,
    get_dashboard_v2,
    get_stalled_instances_v2,
    get_instance_ai_state,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE)


def _denied():
    return {"error": "You don't have access to this Workflow"}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def get_catalog_v2_api(role):
    """The real v2 workflow definition catalog -- distinct from
    core/workflow_tracking_api.py's own get_workflow_catalog_api(), which serves the
    older, flatter 36-entry v1 catalog every other department's job-workflow buttons
    still read from. Spans every department migrated onto this engine so far
    (Operations' 21 entries plus Sales' own Prospecting/Engagement/Deals/Finance/
    Retention entries) -- each workflow's department is derived from its own key
    prefix ("operations."/"sales."), not a hardcoded per-department list here."""

    if role not in _VIEW_ROLES:
        return _denied()

    return {
        "workflows": list_workflow_defs_v2(),
        "instance_statuses": list(INSTANCE_STATUSES),
        "step_statuses": list(STEP_STATUSES),
    }


def get_workflow_def_v2_api(role, workflow_key):
    if role not in _VIEW_ROLES:
        return _denied()

    workflow_def = get_workflow_def_v2(workflow_key)
    if not workflow_def:
        return {"error": f"unknown v2 workflow_key '{workflow_key}'"}

    return workflow_def


def get_dashboard_v2_api(role, department=None):
    if role not in _VIEW_ROLES:
        return _denied()

    return get_dashboard_v2(department=department)


def get_stalled_instances_v2_api(role, department=None):
    if role not in _VIEW_ROLES:
        return _denied()

    return {"stalled": get_stalled_instances_v2(department=department)}


def list_instances_v2_api(role, department=None, workflow_key=None, status=None, category=None,
                           linked_entity_id=None, limit=100):
    if role not in _VIEW_ROLES:
        return _denied()

    if status is not None and status not in INSTANCE_STATUSES:
        return {"error": f"unknown status '{status}'"}

    instances = list_instances_v2(
        department=department,
        workflow_key=workflow_key,
        status=status,
        category=category,
        linked_entity_id=linked_entity_id,
        limit=limit,
    )

    return {"instances": [_serialize(e) for e in instances], "count": len(instances)}


def get_instance_v2_api(role, instance_id):
    if role not in _VIEW_ROLES:
        return _denied()

    from core.workflow_engine_v2 import _get_instance

    instance, error = _get_instance(instance_id)
    if error:
        return {"error": error}

    return _serialize(instance)


def get_instance_ai_state_api(role, instance_id):
    if role not in _VIEW_ROLES:
        return _denied()

    state, error = get_instance_ai_state(instance_id)
    if error:
        return {"error": error}

    return state


def start_workflow_instance_v2_api(role, employee_id, workflow_key, linked_entity_id=None, notes=None):
    if role not in _MUTATE_ROLES:
        return _denied()

    if not employee_id:
        return {"error": "employee_id is required"}

    instance, error = start_workflow_instance_v2(
        workflow_key=workflow_key,
        started_by=employee_id,
        linked_entity_id=linked_entity_id,
        notes=notes,
    )

    if error:
        return {"error": error}

    return _serialize(instance)


def advance_step_api(role, employee_id, instance_id, notes=None):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = advance_step(instance_id, actor=employee_id, notes=notes)

    if error:
        return {"error": error}

    return _serialize(instance)


def add_step_task_api(role, employee_id, instance_id, step_key, description, assigned_to=None):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = add_step_task(instance_id, step_key, description, actor=employee_id, assigned_to=assigned_to)

    if error:
        return {"error": error}

    return _serialize(instance)


def complete_step_task_api(role, employee_id, instance_id, step_key, task_id):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = complete_step_task(instance_id, step_key, task_id, actor=employee_id)

    if error:
        return {"error": error}

    return _serialize(instance)


def add_step_evidence_api(role, employee_id, instance_id, step_key, description, url=None):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = add_step_evidence(instance_id, step_key, description, actor=employee_id, url=url)

    if error:
        return {"error": error}

    return _serialize(instance)


def add_step_comment_api(role, employee_id, instance_id, step_key, text):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = add_step_comment(instance_id, step_key, text, actor=employee_id)

    if error:
        return {"error": error}

    return _serialize(instance)


def block_step_api(role, employee_id, instance_id, step_key, reason):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = block_step(instance_id, step_key, reason, actor=employee_id)

    if error:
        return {"error": error}

    return _serialize(instance)


def unblock_step_api(role, employee_id, instance_id, step_key, notes=None):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = unblock_step(instance_id, step_key, actor=employee_id, notes=notes)

    if error:
        return {"error": error}

    return _serialize(instance)


def request_step_approval_api(role, employee_id, instance_id, step_key, note=None):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = request_step_approval(instance_id, step_key, requested_by=employee_id, note=note)

    if error:
        return {"error": error}

    return _serialize(instance)


def decide_step_approval_api(role, employee_id, instance_id, step_key, approval_id, approved, note=None):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = decide_step_approval(
        instance_id, step_key, approval_id, approved=approved, decided_by=employee_id, note=note
    )

    if error:
        return {"error": error}

    return _serialize(instance)


def escalate_instance_api(role, employee_id, instance_id, reason):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = escalate_instance(instance_id, actor=employee_id, reason=reason)

    if error:
        return {"error": error}

    return _serialize(instance)


def resolve_escalation_api(role, employee_id, instance_id, notes=None):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = resolve_escalation(instance_id, actor=employee_id, notes=notes)

    if error:
        return {"error": error}

    return _serialize(instance)


def force_close_instance_api(role, employee_id, instance_id, reason):
    if role not in _MUTATE_ROLES:
        return _denied()

    instance, error = force_close_instance(instance_id, actor=employee_id, reason=reason)

    if error:
        return {"error": error}

    return _serialize(instance)
