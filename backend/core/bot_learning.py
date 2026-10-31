"""
core/bot_learning.py — heuristic adaptation for the agentic bot (2026-07-13, session
36). Sam asked for the bot to be "continuously learning the role... and improving
efficiencies." With no ML infrastructure in this project (and no intention to fabricate
one -- same honesty bar as Department Intelligence's KPI substitutions), this is real, explainable,
rule-based adaptation: an employee explicitly acting on a suggested task (clicking it
into chat) or explicitly dismissing it are the only two signals recorded -- there's no
attempt to infer "ignored" from passive behavior like scroll position or time-on-screen,
since this backend has no way to observe that honestly.

A BotTaskEvent is an ordinary entity in the same ledger as everything else (see
core/entity_types.py's note), not a separate store or a real model. get_task_affinity()
reads an employee's history for one task key and feeds two things back into
core/bot_tasks.py's generate_tasks(): a priority_boost (acted_count - dismissed_count,
so consistently-useful suggestions float up) and a suppressed flag (three dismissals in
a row with no act in between drops the task entirely -- one act resets the streak).
"""

from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import BOT_TASK_EVENT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 36) --
# every real act/dismiss signal the bot's heuristic prioritization learns from had
# been silently discarded on server restart, meaning the bot could never actually
# accumulate learning across a restart. Fixed below.

SUPPRESS_AFTER_CONSECUTIVE_DISMISSALS = 3
_LOOKBACK_EVENTS = 20

VALID_EVENT_TYPES = ("acted", "dismissed")


def _now():
    return datetime.now(timezone.utc).isoformat()


def record_task_event(employee_id, task_key, event_type):

    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(
            f"Unknown event_type '{event_type}' -- must be one of {VALID_EVENT_TYPES}"
        )

    entity_id = id_generator.generate("BOTEVT")

    event = Entity(
        id=entity_id,
        entity_type=BOT_TASK_EVENT,
        attributes={
            "employee_id": employee_id,
            "task_key": task_key,
            "event_type": event_type,
            "recorded_at": _now(),
        },
    )

    ledger.add_entity(event)

    save_graph(GRAPH_PATH)

    return entity_id


def _events_for(employee_id, task_key):

    events = [
        e for e in ledger.get_all().values()
        if e.entity_type == BOT_TASK_EVENT
        and e.attributes.get("employee_id") == employee_id
        and e.attributes.get("task_key") == task_key
    ]

    events.sort(key=lambda e: e.attributes.get("recorded_at", ""))

    return events[-_LOOKBACK_EVENTS:]


def get_task_affinity(employee_id, task_key):
    """Returns {"suppressed", "priority_boost", "acted_count", "dismissed_count"} for
    this employee/task-key pair, computed from real recorded events only -- an employee
    with no history for a task type gets a neutral {suppressed: False,
    priority_boost: 0}."""

    events = _events_for(employee_id, task_key)

    acted_count = sum(1 for e in events if e.attributes.get("event_type") == "acted")
    dismissed_count = sum(
        1 for e in events if e.attributes.get("event_type") == "dismissed"
    )

    trailing_dismiss_streak = 0

    for event in reversed(events):

        event_type = event.attributes.get("event_type")

        if event_type == "dismissed":
            trailing_dismiss_streak += 1
        elif event_type == "acted":
            break

    return {
        "suppressed": trailing_dismiss_streak >= SUPPRESS_AFTER_CONSECUTIVE_DISMISSALS,
        "priority_boost": acted_count - dismissed_count,
        "acted_count": acted_count,
        "dismissed_count": dismissed_count,
    }
