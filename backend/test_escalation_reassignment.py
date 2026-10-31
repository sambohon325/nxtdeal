from core.assignment_storage import (
    load_assignments
)

from core.escalation_routing import (
    reassign_escalated_lead
)

load_assignments(
    "storage/assignments.json"
)

print(
    reassign_escalated_lead(
        "LEAD-99999"
    )
)