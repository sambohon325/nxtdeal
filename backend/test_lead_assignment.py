from core.lead_assignment import (
    assign_lead,
    get_assigned_employee,
    get_employee_leads
)

assign_lead(
    "LEAD-99999",
    "EMP-00001"
)

print(
    "Owner:"
)

print(
    get_assigned_employee(
        "LEAD-99999"
    )
)

print()

print(
    "Employee Leads:"
)

print(
    get_employee_leads(
        "EMP-00001"
    )
)