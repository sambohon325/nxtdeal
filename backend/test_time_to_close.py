"""Updated 2026-07-13 for the graph-backed pipeline — see CLAUDE.md's "one graph" note.
get_average_time_to_close() now takes entity_ids and reads PipelineCreatedAt/
PipelineStateSince straight off the graph instead of a WorkflowInstance's .history."""

from core.entities import Entity
from core.dealeros import ledger
from core.entity_types import LEAD

from core.pipeline_state import start_pipeline, set_pipeline_state

from core.time_to_close import get_average_time_to_close

ledger.add_entity(Entity(id="LEAD-CLOSED-1", entity_type=LEAD, attributes={}))

start_pipeline(
    "LEAD-CLOSED-1",
    initial_state="NEW",
    timestamp="2026-07-01T00:00:00"
)

set_pipeline_state(
    "LEAD-CLOSED-1",
    "CONTACTED",
    timestamp="2026-07-02T00:00:00"
)

set_pipeline_state(
    "LEAD-CLOSED-1",
    "SOLD",
    timestamp="2026-07-06T00:00:00"
)

print(
    "Average Time To Close:"
)

print(
    get_average_time_to_close(["LEAD-CLOSED-1"])
)
