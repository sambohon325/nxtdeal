"""
Department job-workflow engine (session 53) -- the generic half of the pair with
core/workflow_catalog.py's data. One WorkflowInstance entity per in-progress or
completed run of a catalog workflow (e.g. "this specific vehicle's recon job"),
advancing through the catalog's `stages` list one at a time, optionally linked to
whatever entity the job is actually about via a TRACKS relationship.

Not to be confused with the pre-graph-unification core/workflow_repository.py /
core/workflow_instances.py / core/workflow_storage.py (orphaned since session 17,
flagged for deletion in BUILD_QUEUE.md) -- those lived in a separate
storage/workflows.json file, disconnected from the graph, which is exactly what "One
Graph Unification" undid. This module's WorkflowInstance is an ordinary Entity in
graph.json, same as Deal/Asset/Campaign/DepartmentSnapshot -- graph-native from the start,
not a resurrection of the old side-store pattern.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator, registry
from core.entities import Entity
from core.entity_types import WORKFLOW_INSTANCE
from core.relationships import Relationship
from core.relationship_types import TRACKS
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.workflow_catalog import get_workflow_def

VALID_STATUSES = ["in_progress", "completed", "cancelled"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _resolve_linked_entity(linked_entity_id):
    """Best-effort resolution of whatever the caller typed into the "linked entity"
    field -- a real graph id already (DEAL-00123, VEH-00042, ...), or a business key
    a field employee would actually think in (a VIN, a lead id, an employee id, ...).
    Mirrors core/field_notes.py's single-VIN version, generalized across every
    registry lookup that exists, since workflows span nearly every entity type in the
    catalog. Returns None (not an error) if nothing resolves -- a workflow instance is
    allowed to exist with no linked entity, same permissive precedent as FieldNote."""

    if not linked_entity_id:
        return None

    if ledger.get_entity(linked_entity_id):
        return linked_entity_id

    for finder in (
        registry.find_vehicle,
        registry.find_lead,
        registry.find_customer,
        registry.find_employee,
        registry.find_finance,
        registry.find_lender,
        registry.find_part,
    ):
        resolved = finder(linked_entity_id)
        if resolved:
            return resolved

    return None


def start_workflow_instance(workflow_key, started_by, linked_entity_id=None, notes=None):
    """Starts a new run of a catalog workflow at its first stage. Returns
    (instance, error) -- error is a plain string if workflow_key doesn't match
    anything in the catalog, matching this codebase's (entity, error) tuple
    convention (core/vehicle_intake.py, core/hub/provisioning.py, ...)."""

    workflow_def = get_workflow_def(workflow_key)

    if not workflow_def:
        return None, f"no workflow definition for key '{workflow_key}'"

    resolved_link = _resolve_linked_entity(linked_entity_id)

    instance_id = id_generator.generate("WF")

    entity = Entity(
        id=instance_id,
        entity_type=WORKFLOW_INSTANCE,
        attributes={
            "workflow_key": workflow_key,
            "department": _department_for_key(workflow_key),
            "title": workflow_def["title"],
            "stages": workflow_def["stages"],
            "current_stage_index": 0,
            "status": "in_progress",
            "linked_entity_id": resolved_link,
            "linked_entity_raw": linked_entity_id or None,
            "started_by": started_by,
            "started_at": _now(),
            "updated_at": _now(),
            "completed_at": None,
            "history": [
                {
                    "stage": workflow_def["stages"][0],
                    "action": "started",
                    "by": started_by,
                    "at": _now(),
                    "notes": notes or None,
                }
            ],
        },
    )

    ledger.add_entity(entity)

    if resolved_link:
        ledger.add_relationship(
            Relationship(
                source_id=instance_id,
                target_id=resolved_link,
                relationship_type=TRACKS,
            )
        )

    save_graph(GRAPH_PATH)

    return entity, None


def advance_workflow_instance(instance_id, actor, notes=None):
    """Moves a workflow instance to its next stage, or marks it "completed" if it was
    already on the last stage. Returns (instance, error)."""

    instance = ledger.get_entity(instance_id)

    if not instance or instance.entity_type != WORKFLOW_INSTANCE:
        return None, f"no workflow instance with id '{instance_id}'"

    if instance.attributes["status"] != "in_progress":
        return None, f"workflow instance '{instance_id}' is already {instance.attributes['status']}"

    stages = instance.attributes["stages"]
    next_index = instance.attributes["current_stage_index"] + 1

    if next_index >= len(stages):
        instance.attributes["status"] = "completed"
        instance.attributes["completed_at"] = _now()
        action = "completed"
        stage_label = stages[instance.attributes["current_stage_index"]]
    else:
        instance.attributes["current_stage_index"] = next_index
        action = "advanced"
        stage_label = stages[next_index]

    instance.attributes["updated_at"] = _now()
    instance.attributes["history"].append(
        {
            "stage": stage_label,
            "action": action,
            "by": actor,
            "at": _now(),
            "notes": notes or None,
        }
    )

    save_graph(GRAPH_PATH)
    if instance.attributes["status"] == "completed":
        from core.dealership_lab.engagement import on_work_completed
        on_work_completed(actor)

    return instance, None


def cancel_workflow_instance(instance_id, actor, notes=None):
    """Marks an in-progress workflow instance cancelled. Returns (instance, error)."""

    instance = ledger.get_entity(instance_id)

    if not instance or instance.entity_type != WORKFLOW_INSTANCE:
        return None, f"no workflow instance with id '{instance_id}'"

    if instance.attributes["status"] != "in_progress":
        return None, f"workflow instance '{instance_id}' is already {instance.attributes['status']}"

    instance.attributes["status"] = "cancelled"
    instance.attributes["updated_at"] = _now()
    instance.attributes["history"].append(
        {
            "stage": instance.attributes["stages"][instance.attributes["current_stage_index"]],
            "action": "cancelled",
            "by": actor,
            "at": _now(),
            "notes": notes or None,
        }
    )

    save_graph(GRAPH_PATH)

    return instance, None


def list_workflow_instances(department=None, workflow_key=None, status=None, limit=100):

    instances = [
        e for e in ledger.get_all().values()
        if e.entity_type == WORKFLOW_INSTANCE
        and (department is None or e.attributes.get("department") == department)
        and (workflow_key is None or e.attributes.get("workflow_key") == workflow_key)
        and (status is None or e.attributes.get("status") == status)
    ]

    instances.sort(key=lambda e: e.attributes.get("updated_at") or "", reverse=True)

    return instances[:limit]


def _department_for_key(workflow_key):
    """Workflow keys are "department.slug" (e.g. "operations.recon") by construction
    in core/workflow_catalog.py -- this just reads that back out rather than requiring
    every caller to also pass department separately."""

    return workflow_key.split(".", 1)[0].capitalize()