from core.entity_filter import get_visible_entities

from core.permissions import (
    SALES,
    FINANCE
)

print("Sales")

print(
    get_visible_entities(
        SALES
    )
)

print()

print("Finance")

print(
    get_visible_entities(
        FINANCE
    )
)