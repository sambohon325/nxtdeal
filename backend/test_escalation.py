"""Updated 2026-07-13 for the graph-backed pipeline — see CLAUDE.md's "one graph" note.
get_escalated_leads() now takes a list of entity_ids straight off the graph."""

from core.entities import Entity
from core.dealeros import ledger
from core.entity_types import LEAD

from core.lead_workflows import create_lead_workflow, advance_lead_workflow

from core.pipeline_state import get_all_pipeline_entity_ids

from core.escalation import (
    get_escalated_leads
)

ledger.add_entity(Entity(id="LEAD-ESC-1", entity_type=LEAD, attributes={}))
create_lead_workflow("LEAD-ESC-1")
advance_lead_workflow("LEAD-ESC-1", "CONTACTED")

print(
    get_escalated_leads(
        get_all_pipeline_entity_ids(),
        threshold_days=0
    )
)
