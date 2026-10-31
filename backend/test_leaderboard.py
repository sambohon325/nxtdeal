from core.assignment_storage import (
    load_assignments
)

from core.workflow_storage import (
    load_workflows
)

from core.leaderboard import (
    get_sales_leaderboard
)

load_assignments(
    "storage/assignments.json"
)

load_workflows(
    "storage/workflows.json"
)

print(
    get_sales_leaderboard()
)