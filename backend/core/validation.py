from core.schema import SCHEMAS


def validate_entity(
    entity_type,
    attributes
):

    if entity_type not in SCHEMAS:

        raise ValueError(
            f"Unknown entity type: {entity_type}"
        )

    required_fields = (
        SCHEMAS[entity_type]
    )

    missing = []

    for field in required_fields:

        if field not in attributes:

            missing.append(
                field
            )

    if missing:

        raise ValueError(
            f"Missing required fields: {missing}"
        )

    return True