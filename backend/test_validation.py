from core.validation import (
    validate_entity
)

customer = {
    "FirstName": "John"
}

validate_entity(
    "Customer",
    customer
)

print(
    "Customer validation passed."
)