from core.workflow_repository import (
    workflow_repository
)

from core.workflow_storage import (
    load_workflows
)

load_workflows(
    "storage/workflows.json"
)

print(
    "Workflow Count:"
)

print(
    len(
        workflow_repository.workflows
    )
)

print()

print(
    "Workflows:"
)

print(
    workflow_repository.workflows
)