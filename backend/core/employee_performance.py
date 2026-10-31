from core.lead_assignment import (
    get_employee_leads
)

from core.pipeline_state import (
    get_pipeline_state
)


def get_employee_conversion_rate(
    employee_id
):

    lead_ids = (
        get_employee_leads(
            employee_id
        )
    )

    total = len(
        lead_ids
    )

    if total == 0:

        return 0

    sold = 0

    for lead_id in lead_ids:

        state = get_pipeline_state(
            lead_id
        )

        if state == "SOLD":

            sold += 1

    return round(
        (sold / total) * 100,
        2
    )
