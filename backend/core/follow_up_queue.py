"""Rewritten 2026-07-13: takes a list of lead entity_ids instead of WorkflowInstance
objects — see CLAUDE.md's "one graph" note."""

from core.lead_aging import (
    get_lead_age_days
)

from core.pipeline_state import (
    get_pipeline_state
)


def get_follow_up_queue(
    entity_ids,
    threshold_days=7
):

    queue = []

    for entity_id in entity_ids:

        age = get_lead_age_days(
            entity_id
        )

        if age >= threshold_days:

            queue.append(
                {
                    "lead_id":
                        entity_id,

                    "current_state":
                        get_pipeline_state(
                            entity_id
                        ),

                    "days_in_state":
                        age
                }
            )

    return queue
