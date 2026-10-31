from dataclasses import dataclass
from typing import Optional


@dataclass
class Relationship:
    source_id: str
    target_id: str
    relationship_type: str
    # Provenance (session 76 fourth follow-up -- Sam: "there needs to be a way to
    # audit the connections between all of it"). Optional/defaulted so every existing
    # `Relationship(source_id=..., target_id=..., relationship_type=...)` call site
    # across this codebase (25+ files, all keyword-based -- imports/*, core/deals.py,
    # core/lead_assignment.py, etc.) keeps working unmodified. created_by is an
    # employee_id when known (None for relationships created by import scripts/seed
    # data, which have no acting employee), created_at is an ISO timestamp. Not a full
    # change-log (Sam's own scoping answer: an explorable live connections browser, not
    # a history feature) -- just enough provenance to show "linked via a message Sam
    # sent on July 15" inline when exploring, without a separate audit-log store.
    created_by: Optional[str] = None
    created_at: Optional[str] = None
