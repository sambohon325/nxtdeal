"""Updated 2026-07-13 for the graph-backed pipeline (core/pipeline_state.py) — see
CLAUDE.md's "one graph" note. Pipeline state now autosaves to storage/graph.json (via
core/storage.py's save_graph), not a separate storage/workflows.json."""

from core.entities import Entity
from core.dealeros import ledger
from core.entity_types import LEAD

from core.lead_workflows import (
    create_lead_workflow,
    advance_lead_workflow
)

ledger.add_entity(
    Entity(id="LEAD-99999", entity_type=LEAD, attributes={})
)

create_lead_workflow(
    "LEAD-99999"
)

advance_lead_workflow(
    "LEAD-99999",
    "CONTACTED"
)

print(
    "Check storage/graph.json"
)

print(
    "LEAD-99999 should already be saved with PipelineState=CONTACTED."
)
