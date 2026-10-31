from core.lead_assignment import (
    get_employee_leads
)

from core.pipeline_state import (
    get_pipeline_state
)


def get_salesperson_dashboard(
    employee_id
):

    lead_ids = (
        get_employee_leads(
            employee_id
        )
    )

    active = 0

    closed = 0

    for lead_id in lead_ids:

        state = get_pipeline_state(
            lead_id
        )

        if state is None:

            continue

        if state in [
            "SOLD",
            "LOST"
        ]:

            closed += 1

        else:

            active += 1

    return {

        "employee_id":
            employee_id,

        "assigned_leads":
            len(lead_ids),

        "active_leads":
            active,

        "closed_leads":
            closed
    }
