"""Updated 2026-07-13 for the graph-backed pipeline (core/pipeline_state.py) — see
CLAUDE.md's "one graph" note."""

from core.entities import Entity
from core.dealeros import ledger
from core.entity_types import LEAD

from core.lead_workflows import (
    create_lead_workflow
)

from core.pipeline_state import (
    get_pipeline_state
)

ledger.add_entity(
    Entity(id="LEAD-00001", entity_type=LEAD, attributes={})
)

create_lead_workflow(
    "LEAD-00001"
)

print(
    "Lead:",
    "LEAD-00001"
)

print(
    "State:",
    get_pipeline_state("LEAD-00001")
)
