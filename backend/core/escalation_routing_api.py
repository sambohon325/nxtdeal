from core.escalation_routing import (
    reassign_escalated_lead
)

from core.audit import audit_log

from core.audit_storage import (
    save_audit_log
)

from core.storage_paths import AUDIT_PATH


def reassign(
    lead_id
):

    result = reassign_escalated_lead(
        lead_id
    )

    audit_log.record(
        event_type="lead_escalated",
        summary=f"Lead {lead_id} escalated and reassigned",
        entity_id=lead_id,
        actor="escalation_engine",
        details={"result": result}
        if not isinstance(result, dict)
        else result
    )

    save_audit_log(
        AUDIT_PATH
    )

    return result