"""Rewritten 2026-07-13: age is now "days since the entity's PipelineStateSince
timestamp" read straight off the graph, instead of `workflow.history[-1]["timestamp"]`
on a separate WorkflowInstance — see CLAUDE.md's "one graph" note. Same meaning (days in
current state), different backing store."""

from datetime import datetime

from core.pipeline_state import get_pipeline_state_since


def get_lead_age_days(entity_id):

    since = get_pipeline_state_since(entity_id)

    if since is None:

        return 0

    age = datetime.now() - since

    return age.days
