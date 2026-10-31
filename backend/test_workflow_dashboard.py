from core.workflow_instances import (
    WorkflowInstance
)

from core.workflow_repository import (
    workflow_repository
)

from core.workflow_dashboard import (
    get_lead_pipeline_dashboard
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

dashboard = (
    get_lead_pipeline_dashboard()
)

print(
    "Lead Pipeline Dashboard"
)

print()

for state, count in dashboard.items():

    print(
        f"{state}: {count}"
    )