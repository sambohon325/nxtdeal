"""
Thin API layer over core/workflow_tracking.py + core/workflow_catalog.py, matching
this codebase's "*_api.py" convention -- validate, call the real function, shape the
response for api/app.py's route handlers.
"""

from core.workflow_catalog import get_catalog, get_workflow_def, DEPARTMENTS
from core.workflow_tracking import (
    start_workflow_instance,
    advance_workflow_instance,
    cancel_workflow_instance,
    list_workflow_instances,
)


def _serialize(entity):
    return {
        "id": entity.id,
        **entity.attributes,
    }


def get_workflow_catalog_api():
    """Returns the full catalog, department-keyed, exactly as the frontend needs it to
    render each department's 4 buttons -- no reshaping required on the frontend
    side."""

    return get_catalog()


def start_workflow_api(workflow_key, employee_id, linked_entity_id=None, notes=None):

    if not workflow_key or not get_workflow_def(workflow_key):
        return {"error": f"unknown workflow_key '{workflow_key}'"}

    if not employee_id:
        return {"error": "employee_id is required"}

    instance, error = start_workflow_instance(
        workflow_key=workflow_key,
        started_by=employee_id,
        linked_entity_id=linked_entity_id,
        notes=notes,
    )

    if error:
        return {"error": error}

    return _serialize(instance)


def advance_workflow_api(instance_id, employee_id, notes=None):

    if not employee_id:
        return {"error": "employee_id is required"}

    instance, error = advance_workflow_instance(instance_id, employee_id, notes=notes)

    if error:
        return {"error": error}

    return _serialize(instance)


def cancel_workflow_api(instance_id, employee_id, notes=None):

    if not employee_id:
        return {"error": "employee_id is required"}

    instance, error = cancel_workflow_instance(instance_id, employee_id, notes=notes)

    if error:
        return {"error": error}

    return _serialize(instance)


def list_workflow_instances_api(department=None, workflow_key=None, status=None):

    if department is not None and department not in DEPARTMENTS:
        return {"error": f"unknown department '{department}'"}

    instances = list_workflow_instances(
        department=department,
        workflow_key=workflow_key,
        status=status,
    )

    return [_serialize(e) for e in instances]
