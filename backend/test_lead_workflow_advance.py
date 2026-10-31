"""Updated 2026-07-13 for the graph-backed pipeline (core/pipeline_state.py) — see
CLAUDE.md's "one graph" note. Full transition history now lives in the audit log
(core/audit.py), not on the returned value, since state is just an attribute on the Lead
entity now."""

from core.entities import Entity
from core.dealeros import ledger
from core.entity_types import LEAD

from core.lead_workflows import (
    create_lead_workflow,
    advance_lead_workflow
)

from core.audit import audit_log

ledger.add_entity(
    Entity(id="LEAD-00001", entity_type=LEAD, attributes={})
)

create_lead_workflow(
    "LEAD-00001"
)

state = advance_lead_workflow(
    "LEAD-00001",
    "CONTACTED"
)

state = advance_lead_workflow(
    "LEAD-00001",
    "APPOINTMENT_SET"
)

print(
    "Current State:"
)

print(
    state
)

print()

print(
    "History (from the audit log):"
)

for event in audit_log.get_for_entity("LEAD-00001"):

    print(event.event_type, event.details)
