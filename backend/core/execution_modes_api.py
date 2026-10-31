"""
core/execution_modes_api.py -- API layer for NXTDeal execution modes (2026-07-24, DR-2).
Viewing the workflow/mode matrix is open to any authenticated role (operational insight, same
posture as the fleet/workforce/connect/verify views). Changing a workflow's active mode is an
ADMIN management action -- it decides whether AI and/or the customer may drive that workflow.
"""

from core.permissions import ADMIN
from core.execution_modes import (
    list_workflows,
    get_workflow,
    set_execution_mode,
    execution_summary,
)


def get_execution_modes_api(role):
    data = list_workflows()
    data["summary"] = execution_summary()
    return data


def get_execution_workflow_api(role, workflow_key):
    return get_workflow(workflow_key)


def set_execution_mode_api(admin_role, admin_id, workflow_key, mode):
    if admin_role != ADMIN:
        return {"error": "Admin role required to change a workflow's execution mode"}
    return set_execution_mode(workflow_key, mode, admin_id)
