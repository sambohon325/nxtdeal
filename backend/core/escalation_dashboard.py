from core.pipeline_state import (
    get_all_pipeline_entity_ids
)

from core.escalation import (
    get_escalated_leads
)


def get_escalation_dashboard():

    return get_escalated_leads(
        get_all_pipeline_entity_ids(),
        threshold_days=14
    )
