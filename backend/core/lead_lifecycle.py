from core.lead_workflows import (
    create_lead_workflow
)


def register_lead(
    lead_id
):

    workflow = (
        create_lead_workflow(
            lead_id
        )
    )

    return workflow