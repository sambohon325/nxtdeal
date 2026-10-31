from core.workflows import (
    transition_with_history
)

history = [
    "NEW"
]

history = transition_with_history(
    history,
    "CONTACTED"
)

history = transition_with_history(
    history,
    "APPOINTMENT_SET"
)

print(
    "Workflow History"
)

print()

for state in history:

    print(state)