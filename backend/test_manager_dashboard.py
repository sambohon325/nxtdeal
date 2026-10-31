from core.assignment_storage import (
    load_assignments
)

from core.workflow_storage import (
    load_workflows
)

from core.manager_dashboard import (
    get_manager_dashboard
)

load_assignments(
    "storage/assignments.json"
)

load_workflows(
    "storage/workflows.json"
)

print(
    get_manager_dashboard()
)