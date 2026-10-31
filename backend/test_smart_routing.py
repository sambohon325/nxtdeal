from core.assignment_storage import (
    load_assignments
)

from core.workflow_storage import (
    load_workflows
)

from core.lead_routing import (
    get_active_workload
)

load_assignments(
    "storage/assignments.json"
)

load_workflows(
    "storage/workflows.json"
)

print(
    "EMP-00001 Active Workload:"
)

print(
    get_active_workload(
        "EMP-00001"
    )
)