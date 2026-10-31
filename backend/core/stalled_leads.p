from core.lead_aging import (
    get_lead_age_days
)


def get_stalled_leads(
    workflows,
    threshold_days=7
):

    stalled = []

    for workflow in workflows:

        age = get_lead_age_days(
            workflow
        )

        if age >= threshold_days:

            stalled.append(
                workflow
            )

    return stalled