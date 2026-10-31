from datetime import datetime


class WorkflowInstance:

    def __init__(
        self,
        entity_id,
        workflow_name,
        initial_state
    ):

        self.entity_id = entity_id

        self.workflow_name = (
            workflow_name
        )

        self.history = [
            {
                "state": initial_state,
                "timestamp":
                    datetime.now().isoformat()
            }
        ]

    @property
    def current_state(
        self
    ):

        return (
            self.history[-1]["state"]
        )

    def add_state(
        self,
        state
    ):

        self.history.append(
            {
                "state": state,
                "timestamp":
                    datetime.now().isoformat()
            }
        )