class WorkflowRepository:

    def __init__(self):

        self.workflows = {}

    def add_workflow(
        self,
        workflow
    ):

        self.workflows[
            workflow.entity_id
        ] = workflow

    def get_workflow(
        self,
        entity_id
    ):

        return self.workflows.get(
            entity_id
        )

    def get_all_workflows(
        self
    ):

        return list(
            self.workflows.values()
        )

    def get_pipeline_summary(
        self
    ):

        summary = {}

        for workflow in (
            self.workflows.values()
        ):

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


workflow_repository = (
    WorkflowRepository()
)