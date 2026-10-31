"""Generic temporal boundary: intentionally contains no dealership algorithms."""
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class Observation:
    entity_id: str
    timestamp: str
    evidence_kind: Literal["observed", "derived", "ai_inferred", "predicted"]
    source_system: str
    source_id: str
    source_timestamp: str | None
    import_timestamp: str
    confidence: float | None = None
    identity_resolution: str | None = None
    raw_reference: str | None = None


@dataclass(frozen=True)
class Analysis:
    status: Literal["available", "unavailable"]
    engine_version: str | None
    adapter_version: str
    predictions: tuple
    reason: str | None = None


class TemporalEngine(Protocol):
    def analyze(self, *, workspace_id: str, observations: tuple[Observation, ...]) -> Analysis: ...
