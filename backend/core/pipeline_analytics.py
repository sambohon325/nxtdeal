from core.pipeline_metrics import (
    get_conversion_rate,
    get_loss_rate,
    get_active_leads,
    get_closed_leads
)

from core.time_to_close import (
    get_average_time_to_close
)

from core.pipeline_state import (
    get_pipeline_summary,
    get_all_pipeline_entity_ids
)


def get_pipeline_metrics():

    pipeline = get_pipeline_summary()

    entity_ids = get_all_pipeline_entity_ids()

    return {

        "pipeline": pipeline,

        "conversion_rate":
            get_conversion_rate(
                pipeline
            ),

        "loss_rate":
            get_loss_rate(
                pipeline
            ),

        "active_leads":
            get_active_leads(
                pipeline
            ),

        "closed_leads":
            get_closed_leads(
                pipeline
            ),

        "average_time_to_close_days":
            get_average_time_to_close(
                entity_ids
            )
    }
