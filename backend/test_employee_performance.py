from core.assignment_storage import (
    load_assignments
)

from core.workflow_storage import (
    load_workflows
)

from core.employee_performance import (
    get_employee_conversion_rate
)

load_assignments(
    "storage/assignments.json"
)

load_workflows(
    "storage/workflows.json"
)

print(
    get_employee_conversion_rate(
        "EMP-00001"
    )
)