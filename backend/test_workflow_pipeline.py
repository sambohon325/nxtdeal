from core.workflow_instances import (
    WorkflowInstance
)

from core.workflow_repository import (
    workflow_repository
)

workflow_repository.add_workflow(
    WorkflowInstance(
        "LEAD-00001",
        "Lead Workflow",
        "NEW"
    )
)

workflow_repository.add_workflow(
    WorkflowInstance(
        "LEAD-00002",
        "Lead Workflow",
        "CONTACTED"
    )
)

workflow_repository.add_workflow(
    WorkflowInstance(
        "LEAD-00003",
        "Lead Workflow",
        "CONTACTED"
    )
)

workflow_repository.add_workflow(
    WorkflowInstance(
        "LEAD-00004",
        "Lead Workflow",
        "SOLD"
    )
)

pipeline = (
    workflow_repository.get_pipeline_summary()
)

print(
    "Lead Pipeline"
)

print()

for state, count in pipeline.items():

    print(
        f"{state}: {count}"
    )