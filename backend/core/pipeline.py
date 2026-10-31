def get_pipeline_summary(
    workflows
):

    summary = {}

    for workflow in workflows:

        state = (
            workflow.current_state
        )

        summary[state] = (
            summary.get(
                state,
                0
            ) + 1
        )

    return summary