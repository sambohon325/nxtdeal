from core.workflows import (
    get_next_states,
    can_transition
)

print(
    "Next States From NEW"
)

print(
    get_next_states(
        "NEW"
    )
)

print()

print(
    "NEW -> CONTACTED"
)

print(
    can_transition(
        "NEW",
        "CONTACTED"
    )
)

print()

print(
    "NEW -> SOLD"
)

print(
    can_transition(
        "NEW",
        "SOLD"
    )
)