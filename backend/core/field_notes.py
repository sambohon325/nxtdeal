"""
Generic field-note quick-log (2026-07-13, session 47) -- see core/entity_types.py's
FIELD_NOTE docstring for the full "why". A FieldNote is deliberately unstructured
compared to a Lead/Vehicle/ServiceRecord: department + category + free-text body,
optionally pointed at an existing entity, created by whoever logged it. No approval
workflow (unlike Asset/Campaign/Website) -- these are additive field notes, not
publish-gated content.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator, registry
from core.entities import Entity
from core.entity_types import FIELD_NOTE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

CATEGORIES = [
    "incident", "recon", "maintenance", "payment", "general",
    # CRM/Prospects additions (Sales sub-menu spec, session 92 follow-up) -- the
    # Communication Hub's "Call/Text/Email/Video message" log and the Lead Record's
    # "Customer Notes" (objections/family info/competitors/payment goals) both reuse
    # this same FieldNote mechanism rather than a parallel note store, distinguished
    # purely by category so the Lead Record's Activity Timeline can merge them with
    # real pipeline-transition audit events in one feed.
    "call", "text", "email", "video",
    "objection", "family", "competitor", "payment_goal",
    # Lost Sale Recovery (session 105 follow-up) -- a logged outreach attempt against
    # a lost lead or a cancelled deal, merged into the same Activity Timeline as every
    # other FieldNote category rather than a parallel recovery-log store.
    "recovery_attempt",
    # Vehicle Lifecycle Management (session 106 follow-up) -- internal cross-department
    # messaging about a specific vehicle (Sales Manager <-> Recon Manager, etc.),
    # linked_entity_id=the Vehicle's id. Same reuse discipline as every category above.
    "vehicle_message",
    # Service's RO Workflow Engine (Service rebuild kickoff) -- the RO Workspace's
    # integrated Communication Center (Call/Text/Email, "attached to RO, no separate
    # systems"), linked_entity_id=the ServiceRecord's id. Same reuse discipline as
    # vehicle_message above.
    "ro_communication",
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_field_note(department, category, body, created_by, linked_entity_id=None):

    note_id = id_generator.generate("NOTE")

    # Accept a linked_entity_id that's either already a real graph entity id (starts
    # with a known prefix) or a VIN (looked up via the registry) -- quick-entry forms
    # are filled out by field staff who think in VINs/plate-adjacent numbers, not
    # internal ids like "VEH-00234".
    resolved_link = linked_entity_id or None

    if resolved_link and not ledger.get_entity(resolved_link):
        resolved_link = registry.find_vehicle(linked_entity_id) or resolved_link

    entity = Entity(
        id=note_id,
        entity_type=FIELD_NOTE,
        attributes={
            "department": department,
            "category": category,
            "body": body,
            "linked_entity_id": resolved_link,
            "created_by": created_by,
            "created_at": _now(),
        },
    )

    ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return entity


def list_field_notes(department=None, limit=50, linked_entity_id=None):

    notes = [
        e for e in ledger.get_all().values()
        if e.entity_type == FIELD_NOTE
        and (department is None or e.attributes.get("department") == department)
        and (linked_entity_id is None or e.attributes.get("linked_entity_id") == linked_entity_id)
    ]

    notes.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)

    return notes[:limit]
