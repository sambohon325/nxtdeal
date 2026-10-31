from core.security import can_access_entity

from core.permissions import (
    SALES,
    FINANCE,
    OPERATIONS
)

print("Sales")

print(
    can_access_entity(
        SALES,
        "FinanceContract"
    )
)

print("Finance")

print(
    can_access_entity(
        FINANCE,
        "FinanceContract"
    )
)

print("Operations")

print(
    can_access_entity(
        OPERATIONS,
        "FinanceContract"
    )
)