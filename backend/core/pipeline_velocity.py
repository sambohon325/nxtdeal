"""Rewritten 2026-07-13 to read pipeline state straight off the graph (core/
pipeline_state.py) instead of workflow_repository — see CLAUDE.md's "one graph" note.
Same computation: average days-in-current-state, grouped by state."""

from core.pipeline_state import (
    get_all_pipeline_entity_ids,
    get_pipeline_state
)

from core.lead_aging import (
    get_lead_age_days
)


def get_pipeline_velocity():

    velocity = {}

    for entity_id in (
        get_all_pipeline_entity_ids()
    ):

        state = get_pipeline_state(
            entity_id
        )

        days = get_lead_age_days(
            entity_id
        )

        if state not in velocity:

            velocity[state] = []

        velocity[state].append(
            days
        )

    results = {}

    for state, values in (
        velocity.items()
    ):

        results[state] = round(
            sum(values) / len(values),
            2
        )

    return results
