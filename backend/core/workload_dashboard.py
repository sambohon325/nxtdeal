from core.lead_assignment import (
    get_assigned_employee_ids
)

from core.lead_routing import (
    get_active_workload
)


def get_workload_dashboard():

    employees = get_assigned_employee_ids()

    results = []

    for employee_id in employees:

        results.append(
            {
                "employee_id":
                    employee_id,

                "active_workload":
                    get_active_workload(
                        employee_id
                    )
            }
        )

    results.sort(
        key=lambda x:
            x["active_workload"]
    )

    return results
