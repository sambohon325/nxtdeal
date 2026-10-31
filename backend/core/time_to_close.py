"""Rewritten 2026-07-13 to read from the graph (core/pipeline_state.py) instead of a
WorkflowInstance's .history — see CLAUDE.md's "one graph" note. PipelineCreatedAt is set
once when a lead enters the pipeline; PipelineStateSince is updated on every transition,
so for a lead currently in SOLD, PipelineStateSince is exactly when it became SOLD —
the same two timestamps the old .history[0]/.history[-1] gave us."""

from core.pipeline_state import (
    get_pipeline_state,
    get_pipeline_created_at,
    get_pipeline_state_since
)


def get_time_to_close_days(entity_id):

    if get_pipeline_state(entity_id) != "SOLD":

        return None

    start_time = get_pipeline_created_at(entity_id)

    end_time = get_pipeline_state_since(entity_id)

    if start_time is None or end_time is None:

        return None

    return (
        end_time - start_time
    ).days


def get_average_time_to_close(entity_ids):

    times = []

    for entity_id in entity_ids:

        days = get_time_to_close_days(
            entity_id
        )

        if days is not None:

            times.append(
                days
            )

    if not times:

        return 0

    return round(
        sum(times) / len(times),
        2
    )
