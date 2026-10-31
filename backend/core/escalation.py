"""Rewritten 2026-07-13: takes a list of lead entity_ids (pulled from the graph via
core/pipeline_state.py) instead of a list of WorkflowInstance objects — see CLAUDE.md's
"one graph" note."""

from core.lead_aging import (
    get_lead_age_days
)

from core.pipeline_state import (
    get_pipeline_state
)


def get_escalated_leads(
    entity_ids,
    threshold_days=14
):

    escalated = []

    for entity_id in entity_ids:

        state = get_pipeline_state(
            entity_id
        )

        if state in [
            "SOLD",
            "LOST"
        ]:

            continue

        age = get_lead_age_days(
            entity_id
        )

        if age >= threshold_days:

            escalated.append(
                {
                    "lead_id":
                        entity_id,

                    "current_state":
                        state,

                    "days_in_state":
                        age,

                    "status":
                        "ESCALATED"
                }
            )

    return escalated
