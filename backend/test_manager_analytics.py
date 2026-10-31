from core.assignment_storage import (
    load_assignments
)

from core.workflow_storage import (
    load_workflows
)

from core.manager_analytics import (
    get_employee_metrics
)

load_assignments(
    "storage/assignments.json"
)

load_workflows(
    "storage/workflows.json"
)

print(
    get_employee_metrics(
        "EMP-00001"
    )
)