from core.workflow_instances import (
    WorkflowInstance
)

from core.workflow_repository import (
    workflow_repository
)

lead_workflow = WorkflowInstance(
    entity_id="LEAD-00001",
    workflow_name="Lead Workflow",
    initial_state="NEW"
)

workflow_repository.add_workflow(
    lead_workflow
)

workflow = (
    workflow_repository.get_workflow(
        "LEAD-00001"
    )
)

print(
    "Entity:",
    workflow.entity_id
)

print(
    "Current State:",
    workflow.current_state
)