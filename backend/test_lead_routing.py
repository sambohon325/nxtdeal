from core.assignment_storage import (
    load_assignments
)

from core.lead_routing import (
    auto_assign_lead
)

load_assignments(
    "storage/assignments.json"
)

employee = auto_assign_lead(
    "LEAD-88888"
)

print(
    "Assigned To:"
)

print(
    employee
)