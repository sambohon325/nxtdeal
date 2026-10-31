from core.lead_assignment import (
    get_assigned_employee_ids
)

from core.manager_analytics import (
    get_employee_metrics
)


def get_manager_dashboard():

    employees = get_assigned_employee_ids()

    return [
        get_employee_metrics(
            employee_id
        )
        for employee_id in employees
    ]
