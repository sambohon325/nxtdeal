from core.workflows import (
    transition_state
)

state = "NEW"

print(
    "Current State:",
    state
)

state = transition_state(
    state,
    "CONTACTED"
)

print(
    "New State:",
    state
)