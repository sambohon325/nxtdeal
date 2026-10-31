from core.lead_assignment import (
    get_assigned_employee_ids
)

from core.employee_performance import (
    get_employee_conversion_rate
)


def get_sales_leaderboard():

    employees = get_assigned_employee_ids()

    results = []

    for employee_id in employees:

        results.append(
            {
                "employee_id":
                    employee_id,

                "conversion_rate":
                    get_employee_conversion_rate(
                        employee_id
                    )
            }
        )

    results.sort(
        key=lambda x:
            x["conversion_rate"],
        reverse=True
    )

    return results
