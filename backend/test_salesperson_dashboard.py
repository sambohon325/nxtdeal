from core.workflow_storage import (
    load_workflows
)

from core.lead_assignment import (
    assign_lead
)

from core.salesperson_dashboard import (
    get_salesperson_dashboard
)

load_workflows(
    "storage/workflows.json"
)

assign_lead(
    "LEAD-99999",
    "EMP-00001"
)

print(
    get_salesperson_dashboard(
        "EMP-00001"
    )
)