def get_conversion_rate(
    pipeline
):

    total = sum(
        pipeline.values()
    )

    sold = pipeline.get(
        "SOLD",
        0
    )

    if total == 0:

        return 0

    return round(
        (sold / total) * 100,
        2
    )


def get_loss_rate(
    pipeline
):

    total = sum(
        pipeline.values()
    )

    lost = pipeline.get(
        "LOST",
        0
    )

    if total == 0:

        return 0

    return round(
        (lost / total) * 100,
        2
    )


def get_active_leads(
    pipeline
):

    active_states = [

        "NEW",

        "CONTACTED",

        "APPOINTMENT_SET",

        "VISITED",

        "PROPOSAL",

        "NEGOTIATION"
    ]

    return sum(
        pipeline.get(
            state,
            0
        )
        for state in active_states
    )


def get_closed_leads(
    pipeline
):

    return (

        pipeline.get(
            "SOLD",
            0
        )

        +

        pipeline.get(
            "LOST",
            0
        )
    )