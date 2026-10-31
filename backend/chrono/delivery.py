"""Generic temporal ingest contract. No dealer/vendor algorithms or AI dependency."""
from dataclasses import dataclass, field
from typing import Protocol
from chrono.contracts import Observation


@dataclass(frozen=True)
class TemporalEnvelope:
    event_id: str
    observation: Observation
    attributes: dict
    provenance: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryReceipt:
    accepted_event_ids: tuple[str, ...]
    retryable: bool = True


class ObservationSink(Protocol):
    # Retried requests reuse event IDs; sinks MUST deduplicate them durably.
    supports_idempotency: bool
    def deliver(self, *, workspace_id: str, events: tuple[TemporalEnvelope, ...]) -> DeliveryReceipt: ...
