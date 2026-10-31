from core.workflow_instances import (
    WorkflowInstance
)

from core.pipeline import (
    get_pipeline_summary
)

lead1 = WorkflowInstance(
    "LEAD-00001",
    "Lead Workflow",
    "NEW"
)

lead2 = WorkflowInstance(
    "LEAD-00002",
    "Lead Workflow",
    "CONTACTED"
)

lead3 = WorkflowInstance(
    "LEAD-00003",
    "Lead Workflow",
    "CONTACTED"
)

lead4 = WorkflowInstance(
    "LEAD-00004",
    "Lead Workflow",
    "SOLD"
)

pipeline = get_pipeline_summary(
    [
        lead1,
        lead2,
        lead3,
        lead4
    ]
)

print(
    "Lead Pipeline"
)

print()

for state, count in pipeline.items():

    print(
        f"{state}: {count}"
    )