"""Updated 2026-07-13 for the graph-backed pipeline (core/pipeline_state.py) — see
CLAUDE.md's "one graph" note. register_lead() now requires the Lead entity to already
exist on the graph (it just sets attributes on it) and returns the state string, not a
WorkflowInstance object."""

from core.entities import Entity
from core.dealeros import ledger
from core.entity_types import LEAD

from core.lead_lifecycle import (
    register_lead
)

ledger.add_entity(
    Entity(id="LEAD-00010", entity_type=LEAD, attributes={})
)

state = register_lead(
    "LEAD-00010"
)

print(
    "Lead:",
    "LEAD-00010"
)

print(
    "State:",
    state
)
