from datetime import datetime


LEAD_WORKFLOW = {

    "NEW": [
        "CONTACTED"
    ],

    "CONTACTED": [
        "APPOINTMENT_SET",
        "LOST"
    ],

    "APPOINTMENT_SET": [
        "VISITED",
        "LOST"
    ],

    "VISITED": [
        "PROPOSAL",
        "LOST"
    ],

    "PROPOSAL": [
        "NEGOTIATION",
        "LOST"
    ],

    "NEGOTIATION": [
        "SOLD",
        "LOST"
    ],

    "SOLD": [],

    "LOST": []
}


def get_next_states(
    current_state
):

    return LEAD_WORKFLOW.get(
        current_state,
        []
    )


def can_transition(
    current_state,
    next_state
):

    return (
        next_state in
        get_next_states(
            current_state
        )
    )


def transition_state(
    current_state,
    next_state
):

    if not can_transition(
        current_state,
        next_state
    ):

        raise ValueError(
            f"Invalid transition: "
            f"{current_state} -> {next_state}"
        )

    return next_state


def transition_with_history(
    history,
    next_state
):

    current_state = (
        history[-1]["state"]
    )

    if not can_transition(
        current_state,
        next_state
    ):

        raise ValueError(
            f"Invalid transition: "
            f"{current_state} -> {next_state}"
        )

    history.append(
        {
            "state": next_state,
            "timestamp":
                datetime.now().isoformat()
        }
    )

    return history