from core.workflow_repository import (
    workflow_repository
)

from core.workflow_storage import (
    load_workflows
)

load_workflows(
    "storage/workflows.json"
)

for workflow in (
    workflow_repository.get_all_workflows()
):

    print(
        "Entity:",
        workflow.entity_id
    )

    print(
        "Current State:",
        workflow.current_state
    )

    print()