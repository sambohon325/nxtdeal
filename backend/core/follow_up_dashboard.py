from core.pipeline_state import (
    get_all_pipeline_entity_ids
)

from core.follow_up_queue import (
    get_follow_up_queue
)


def get_follow_up_dashboard():

    return get_follow_up_queue(
        get_all_pipeline_entity_ids(),
        threshold_days=0
    )
