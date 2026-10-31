from core.lead_assignment import (
    get_employee_leads
)

from core.pipeline_state import (
    get_pipeline_state
)

from core.lead_aging import (
    get_lead_age_days
)

from core.employee_performance import (
    get_employee_conversion_rate
)


def get_employee_metrics(
    employee_id
):

    lead_ids = (
        get_employee_leads(
            employee_id
        )
    )

    assigned = len(
        lead_ids
    )

    active = 0

    closed = 0

    stalled = 0

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

        if (
            get_lead_age_days(
                lead_id
            ) >= 7
        ):

            stalled += 1

    return {

        "employee_id":
            employee_id,

        "assigned_leads":
            assigned,

        "active_leads":
            active,

        "closed_leads":
            closed,

        "stalled_leads":
            stalled,

        "conversion_rate":
            get_employee_conversion_rate(
                employee_id
            )
    }
