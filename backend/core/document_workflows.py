"""
core/document_workflows.py -- Operations' "Documents" item (session 106
follow-up #6, "keep going" autonomous continuation, sixth slice of the
Operations rebuild). Sam's spec: "Deal Jacket Workflow, Title Processing
workflow, Compliance Packets, Digital Approvals."

Builds real actions on top of the categorized Document vault
(`imports/seed_demo_extras.py`'s `seed_documents()`, session 60) rather than
a second document model. `DOCUMENT_TYPES_BY_ENTITY` (Deal -> Deal Jacket/
Buyer Order, Vehicle -> Title/Recon Form/Inspection Report, Customer ->
Compliance File) is the same real catalog `operations_menu.py`'s existing
`documents()` view already reads -- this module adds completeness checks and
two new mutation capabilities on top of it:

  - Deal Jacket Workflow / Title Processing workflow: `get_deal_jacket_status()`/
    `get_title_status()` compute a real completeness check (which required doc
    types are actually on file for a given Deal/Vehicle) -- the same
    missing-title check `core/inventory_menu.py`'s `wholesale()` and
    `core/vehicle_lifecycle.py` already established, generalized to Deal
    Jackets too. `request_document()` reuses `core/operations_tasks.py`'s
    engine (task_type "title_processing" for a missing Title, matching the
    existing catalog entry; "document_request" for everything else, a new
    entry added this session) rather than a parallel request queue.

  - Compliance Packets: `get_document_packet()` is a real bundling view -- every
    real Document actually on file for one entity (Deal/Vehicle/Customer), not
    a fabricated new document type. Nothing in this codebase could previously
    assemble "everything on file about this Deal" into one view.

  - Digital Approvals: the one genuinely new capability this slice adds.
    Document entities had no `approval_status` field at all before this
    module -- `approve_document()`/`reject_document()` are real actions, a
    computed "pending" default on read (same computed-default convention as
    `vehicle_lifecycle.py`'s `lifecycle_status`) for the ~89 seeded documents
    that predate this concept.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import DOCUMENT, DEAL, VEHICLE, CUSTOMER
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

from core.operations_tasks import create_task

REQUIRED_DOC_TYPES = {
    DEAL: ["Deal Jacket", "Buyer Order"],
    VEHICLE: ["Title"],
    CUSTOMER: ["Compliance File"],
}

APPROVAL_STATUSES = ("pending", "approved", "rejected")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _documents_for(entity_id):
    return [
        d for d in ledger.get_all().values()
        if d.entity_type == DOCUMENT and d.attributes.get("EntityID") == entity_id
    ]


def _approval_status(doc):
    return doc.attributes.get("approval_status") or "pending"


def _doc_brief(d):
    return {
        "id": d.id,
        "document_type": d.attributes.get("DocumentType"),
        "file_name": d.attributes.get("FileName"),
        "uploaded_by": d.attributes.get("UploadedBy"),
        "created_at": d.attributes.get("CreatedAt"),
        "approval_status": _approval_status(d),
    }


def _get_entity(entity_type, entity_id):
    e = ledger.get_entity(entity_id)
    if not e or e.entity_type != entity_type:
        return None
    return e


def _completeness_check(entity_type, entity_id):

    entity = _get_entity(entity_type, entity_id)
    if not entity:
        return {"error": f"{entity_type} '{entity_id}' not found"}

    required = REQUIRED_DOC_TYPES.get(entity_type, [])
    docs = _documents_for(entity_id)
    present_types = {d.attributes.get("DocumentType") for d in docs}
    missing = [t for t in required if t not in present_types]

    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "required_types": required,
        "documents": [_doc_brief(d) for d in docs],
        "missing_types": missing,
        "is_complete": len(missing) == 0,
    }


def get_deal_jacket_status(deal_id):
    return _completeness_check(DEAL, deal_id)


def get_title_status(vehicle_id):
    return _completeness_check(VEHICLE, vehicle_id)


def request_document(entity_type, entity_id, document_type, requested_by, notes="", _skip_save=False):

    entity = _get_entity(entity_type, entity_id)
    if not entity:
        return {"error": f"{entity_type} '{entity_id}' not found"}

    required = REQUIRED_DOC_TYPES.get(entity_type, [])
    if document_type not in required:
        return {"error": f"document_type must be one of {required} for a {entity_type}"}

    task_type = "title_processing" if document_type == "Title" else "document_request"
    owner_bucket = "Title Clerk" if document_type == "Title" else "Accounting"

    label = entity.attributes.get("VIN") or entity.attributes.get("CustomerName") or entity_id

    return create_task(
        task_type=task_type,
        detail=f"{document_type} requested for {entity_type} {label}. {notes}".strip(),
        created_by=requested_by,
        priority="normal",
        owner_bucket=owner_bucket,
        linked_entity_id=entity_id,
        # _skip_save (added 2026-07-19 for core/screen_guidance.py's own "Do It"
        # bulk action, create_document_requests_from_guidance() -- same batching
        # precedent as core/operations_tasks.py's own create_task() comment
        # describes) -- every other existing caller is unaffected, default False,
        # saves immediately as it always has.
        _skip_save=_skip_save,
    )


def get_document_packet(entity_type, entity_id):
    """A real bundling view -- every document actually on file for one
    entity, plus the same completeness check (missing required types) so a
    'Compliance Packet' request surfaces what's there AND what's still
    missing in one place."""

    if entity_type not in REQUIRED_DOC_TYPES:
        return {"error": f"entity_type must be one of {list(REQUIRED_DOC_TYPES.keys())}"}

    return _completeness_check(entity_type, entity_id)


def approve_document(document_id, approved_by, notes=""):

    doc = ledger.get_entity(document_id)
    if not doc or doc.entity_type != DOCUMENT:
        return {"error": f"Document '{document_id}' not found"}

    doc.attributes["approval_status"] = "approved"
    doc.attributes["approval_notes"] = notes or ""
    doc.attributes["approved_by"] = approved_by
    doc.attributes["approval_updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)

    return _doc_brief(doc)


def reject_document(document_id, rejected_by, reason=""):

    doc = ledger.get_entity(document_id)
    if not doc or doc.entity_type != DOCUMENT:
        return {"error": f"Document '{document_id}' not found"}

    if not reason:
        return {"error": "A reason is required to reject a document"}

    doc.attributes["approval_status"] = "rejected"
    doc.attributes["approval_notes"] = reason
    doc.attributes["approved_by"] = rejected_by
    doc.attributes["approval_updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)

    return _doc_brief(doc)


def list_pending_approvals(limit=50):

    pending = [
        d for d in ledger.get_all().values()
        if d.entity_type == DOCUMENT and _approval_status(d) == "pending"
    ]

    pending.sort(key=lambda d: d.attributes.get("CreatedAt") or "", reverse=True)

    return {
        "count": len(pending),
        "documents": [_doc_brief(d) for d in pending[:limit]],
    }
