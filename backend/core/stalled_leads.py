"""Rewritten 2026-07-13: takes a list of lead entity_ids instead of WorkflowInstance
objects, matching core/escalation.py and core/follow_up_queue.py — see CLAUDE.md's
"one graph" note. Not currently wired into any dashboard/route (core/manager_analytics.py
computes its own "stalled" count inline instead) — kept for parity/future use."""

from core.lead_aging import (
    get_lead_age_days
)


def get_stalled_leads(
    entity_ids,
    threshold_days=7
):

    stalled = []

    for entity_id in entity_ids:

        age = get_lead_age_days(
            entity_id
        )

        if age >= threshold_days:

            stalled.append(
                entity_id
            )

    return stalled
