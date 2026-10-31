from core.lead_routing import (
    auto_assign_lead
)

from core.audit import audit_log

from core.audit_storage import (
    save_audit_log
)

from core.storage_paths import AUDIT_PATH


def assign_new_lead(
    lead_id
):

    assigned_to = auto_assign_lead(
        lead_id
    )

    audit_log.record(
        event_type="lead_assigned",
        summary=f"Lead {lead_id} assigned to {assigned_to}",
        entity_id=lead_id,
        actor="routing_engine",
        details={"assigned_to": assigned_to}
    )

    save_audit_log(
        AUDIT_PATH
    )

    return {
        "lead_id": lead_id,
        "assigned_to": assigned_to
    }