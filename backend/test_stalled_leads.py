"""Updated 2026-07-13 for the graph-backed pipeline — see CLAUDE.md's "one graph" note.
get_stalled_leads() now takes a list of entity_ids straight off the graph."""

from core.entities import Entity
from core.dealeros import ledger
from core.entity_types import LEAD

from core.lead_workflows import create_lead_workflow

from core.pipeline_state import get_all_pipeline_entity_ids, get_pipeline_state

from core.stalled_leads import (
    get_stalled_leads
)

ledger.add_entity(Entity(id="LEAD-STALL-1", entity_type=LEAD, attributes={}))
create_lead_workflow("LEAD-STALL-1")

stalled = get_stalled_leads(
    get_all_pipeline_entity_ids(),
    threshold_days=0
)

print(
    "Stalled Leads:"
)

print()

for entity_id in stalled:

    print(entity_id)

    print(get_pipeline_state(entity_id))

    print()
