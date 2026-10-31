"""Updated 2026-07-13 for the graph-backed pipeline — see CLAUDE.md's "one graph" note.
get_lead_age_days() now takes an entity_id, reading PipelineStateSince straight off the
graph, instead of a WorkflowInstance object."""

from core.entities import Entity
from core.dealeros import ledger
from core.entity_types import LEAD

from core.lead_workflows import create_lead_workflow

from core.pipeline_state import get_pipeline_state

from core.lead_aging import (
    get_lead_age_days
)

ledger.add_entity(Entity(id="LEAD-99999", entity_type=LEAD, attributes={}))
create_lead_workflow("LEAD-99999")

print(
    "Current State:"
)

print(
    get_pipeline_state("LEAD-99999")
)

print()

print(
    "Age (Days):"
)

print(
    get_lead_age_days("LEAD-99999")
)
