"""Updated 2026-07-13 for the graph-backed pipeline — see CLAUDE.md's "one graph" note.
get_pipeline_metrics() now reads PipelineState straight off Lead entities on the graph
instead of a separate workflow_repository."""

from core.entities import Entity
from core.dealeros import ledger
from core.entity_types import LEAD

from core.pipeline_state import start_pipeline

from core.pipeline_analytics import (
    get_pipeline_metrics
)

for lead_id, state in [
    ("LEAD-1", "NEW"),
    ("LEAD-2", "CONTACTED"),
    ("LEAD-3", "SOLD"),
    ("LEAD-4", "LOST"),
]:

    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes={}))
    start_pipeline(lead_id, initial_state=state)

print(
    get_pipeline_metrics()
)
