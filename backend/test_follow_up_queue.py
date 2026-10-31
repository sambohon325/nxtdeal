"""Updated 2026-07-13 for the graph-backed pipeline — see CLAUDE.md's "one graph" note.
get_follow_up_queue() now takes a list of entity_ids straight off the graph."""

from core.entities import Entity
from core.dealeros import ledger
from core.entity_types import LEAD

from core.lead_workflows import create_lead_workflow

from core.pipeline_state import get_all_pipeline_entity_ids

from core.follow_up_queue import (
    get_follow_up_queue
)

ledger.add_entity(Entity(id="LEAD-FU-1", entity_type=LEAD, attributes={}))
create_lead_workflow("LEAD-FU-1")

queue = get_follow_up_queue(
    get_all_pipeline_entity_ids(),
    threshold_days=0
)

print(
    "Follow-Up Queue"
)

print()

for item in queue:

    print(item)
