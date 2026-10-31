import json

from core.workflow_instances import (
    WorkflowInstance
)

from core.workflow_repository import (
    workflow_repository
)


def save_workflows(
    filepath
):

    data = []

    for workflow in (
        workflow_repository
        .get_all_workflows()
    ):

        data.append(
            {
                "entity_id":
                    workflow.entity_id,

                "workflow_name":
                    workflow.workflow_name,

                "history":
                    workflow.history
            }
        )

    with open(
        filepath,
        "w"
    ) as file:

        json.dump(
            data,
            file,
            indent=4
        )


def load_workflows(
    filepath
):

    try:

        with open(
            filepath,
            "r"
        ) as file:

            data = json.load(
                file
            )

    except FileNotFoundError:

        return

    workflow_repository.workflows = {}

    for item in data:

        workflow = (
            WorkflowInstance(
                entity_id=item[
                    "entity_id"
                ],
                workflow_name=item[
                    "workflow_name"
                ],
                initial_state=item[
                    "history"
                ][0]["state"]
            )
        )

        workflow.history = (
            item["history"]
        )

        workflow_repository.add_workflow(
            workflow
        )