import json

from core.lead_assignment import (
    assignments
)


def save_assignments(
    filepath
):

    with open(
        filepath,
        "w"
    ) as file:

        json.dump(
            assignments,
            file,
            indent=4
        )


def load_assignments(
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

    assignments.clear()

    assignments.update(
        data
    )