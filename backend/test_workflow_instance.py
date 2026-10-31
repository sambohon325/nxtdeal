from core.workflow_instances import (
    WorkflowInstance
)

workflow = WorkflowInstance(
    entity_id="LEAD-00001",
    workflow_name="Lead Workflow",
    initial_state="NEW"
)

print(
    "Entity:",
    workflow.entity_id
)

print(
    "Current State:",
    workflow.current_state
)

workflow.add_state(
    "CONTACTED"
)

print()

print(
    "Current State:",
    workflow.current_state
)

print()

print(
    "History:"
)

for state in workflow.history:

    print(state)