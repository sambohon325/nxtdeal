"""
Lead pipeline (workflow) state, stored directly on the graph — replaces the old
core/workflow_repository.py + core/workflow_instances.py (WorkflowInstance objects kept in
a separate in-memory dict, persisted to storage/workflows.json). See CLAUDE.md's "one
graph" note (2026-07-13): pipeline state is now just three attributes on the Lead entity
itself, saved by the same core/storage.py save_graph()/load_graph() that already persists
everything else.

Attributes written onto the entity (all plain strings, ISO timestamps):
    PipelineState       - current state, e.g. "NEW", "CONTACTED", "SOLD", "LOST"
    PipelineCreatedAt    - when the entity entered the workflow (set once, never changes)
    PipelineStateSince   - when the entity entered its *current* state (updated on every
                           transition, including the initial one) — this is what
                           core/lead_aging.py uses for "days in state"

Full transition-by-transition history is intentionally NOT duplicated here — the audit
log (core/audit.py) already records a "workflow_transition" event with entity_id and
{"from":..., "to":...} on every call to set_pipeline_state(), so that's the durable
record of history if it's ever needed. This file only tracks current state, matching what
every dashboard actually reads.
"""

from datetime import datetime

from core.dealeros import ledger
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module itself had ZERO save_graph() calls -- most callers (core/lead_workflows.py,
# core/lost_sale_recovery.py) already save separately right after calling into here, but
# core/bot_actions.py's _touch_overdue_leads() (the bot's "auto" coverage mode) calls
# set_pipeline_state() directly and neither it nor its own caller
# (core/bot_scheduler.py's tick loop) ever saved -- meaning every real pipeline-state
# touch the bot made while covering an absent employee was silently discarded on
# restart. Rather than patch every caller individually (and risk a future one making
# the same mistake), the save is added directly here, at the source -- callers that
# already save separately (lead_workflows.py/lost_sale_recovery.py) just do one
# harmless extra write, which is a strictly safer tradeoff than relying on every
# current and future caller to remember.


def _get_entity_or_raise(entity_id):

    entity = ledger.get_entity(entity_id)

    if not entity:
        raise ValueError(f"Unknown entity: {entity_id}")

    return entity


def start_pipeline(entity_id, initial_state="NEW", timestamp=None):
    """Puts an entity into the pipeline for the first time. Safe to call again on an
    entity that's already in the pipeline — it will NOT reset PipelineCreatedAt, only
    PipelineState/PipelineStateSince (matches the old create_lead_workflow behavior of
    being effectively idempotent per entity)."""

    entity = _get_entity_or_raise(entity_id)

    ts = timestamp or datetime.now().isoformat()

    if "PipelineCreatedAt" not in entity.attributes:
        entity.attributes["PipelineCreatedAt"] = ts

    entity.attributes["PipelineState"] = initial_state
    entity.attributes["PipelineStateSince"] = ts

    save_graph(GRAPH_PATH)

    return initial_state


def set_pipeline_state(entity_id, next_state, timestamp=None):

    entity = _get_entity_or_raise(entity_id)

    ts = timestamp or datetime.now().isoformat()

    entity.attributes["PipelineState"] = next_state
    entity.attributes["PipelineStateSince"] = ts

    save_graph(GRAPH_PATH)

    return next_state


def get_pipeline_state(entity_id):

    entity = ledger.get_entity(entity_id)

    if not entity:
        return None

    return entity.attributes.get("PipelineState")


def _parse_timestamp(entity, key):

    value = entity.attributes.get(key)

    if not value:
        return None

    return datetime.fromisoformat(value)


def get_pipeline_state_since(entity_id):

    entity = ledger.get_entity(entity_id)

    if not entity:
        return None

    return _parse_timestamp(entity, "PipelineStateSince")


def get_pipeline_created_at(entity_id):

    entity = ledger.get_entity(entity_id)

    if not entity:
        return None

    return _parse_timestamp(entity, "PipelineCreatedAt")


def is_in_pipeline(entity_id):

    return get_pipeline_state(entity_id) is not None


def get_all_pipeline_entity_ids():
    """Every entity currently tracked in the pipeline — replaces
    workflow_repository.get_all_workflows()."""

    return [
        entity.id
        for entity in ledger.get_all().values()
        if "PipelineState" in entity.attributes
    ]


def get_pipeline_summary():
    """{state: count} across every pipeline entity — replaces
    workflow_repository.get_pipeline_summary()."""

    summary = {}

    for entity_id in get_all_pipeline_entity_ids():

        state = get_pipeline_state(entity_id)

        summary[state] = summary.get(state, 0) + 1

    return summary
