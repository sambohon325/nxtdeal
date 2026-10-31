"""Bound numerical jobs in this process, including work in synchronous threads."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from threading import BoundedSemaphore
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

COMPUTE_BUSY_RESPONSES = {
    503: {
        "description": "Numerical capacity is occupied. No analysis was started; retry explicitly.",
        "headers": {"Retry-After": {"schema": {"type": "string"}}},
        "content": {"application/json": {"schema": {
            "type": "object",
            "required": ["detail", "executed"],
            "properties": {
                "detail": {"type": "string"},
                "executed": {"type": "boolean", "const": False},
            },
        }}},
    },
}


class ComputeBusy(ValueError):
    """No numerical work was admitted; callers may explicitly retry."""


class ComputeAdmission:
    def __init__(self, maximum: int = 1):
        if type(maximum) is not int or not 1 <= maximum <= 4:
            raise ValueError("Numerical concurrency must be an integer between 1 and 4")
        self.slots = BoundedSemaphore(maximum)

    @contextmanager
    def enter(self) -> Iterator[None]:
        if not self.slots.acquire(blocking=False):
            raise ComputeBusy("The forecast engine is busy. No analysis was started; retry shortly.")
        try:
            yield
        finally:
            self.slots.release()


# All tenant engines in the shipped one-process service share this budget.
# It belongs to the synchronous job, not an HTTP task that may be cancelled
# while its worker continues. Do not release it merely because a caller stops
# waiting. Lower-level prepare/sample primitives remain trusted internal APIs.
numerical_jobs = ComputeAdmission()


def admitted(function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def run(*args: P.args, **kwargs: P.kwargs) -> R:
        with numerical_jobs.enter():
            return function(*args, **kwargs)

    return run
