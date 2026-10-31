"""
Chat file attachments (2026-07-13, session 47) -- Sam: "we need to add a +file
attachment to the main chat, so they can add images, files, etc." Reuses the existing
DOCUMENT entity type (imports/document_import.py already establishes the shape:
DocumentNumber/EntityType/EntityID/FileName) rather than inventing a parallel concept --
an uploaded chat attachment is an ordinary Document entity, just one created live
instead of via CSV, optionally pointed at whatever entity the conversation was about.

Raw bytes are written to the active tenant's uploads directory (created on first use,
resolved via core.storage_paths.uploads_dir() -- "storage/uploads" for today's one real
dealer, "storage/tenants/{id}/uploads" for a provisioned tenant) under the Document's own
id so two uploads can never collide on filename; the entity's attributes carry the
original filename back for display.
"""

import os
from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import DOCUMENT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH, uploads_dir

# Tenant-aware (session 55): resolved through core.storage_paths so a provisioned tenant's
# attachment bytes land in its own DEALEROS_STORAGE_DIR, not the default "storage/". Kept
# as a module-level attribute (computed once at import, matching GRAPH_PATH's precedent)
# so tests/test_intake.py's monkeypatch of documents.UPLOAD_DIR still redirects real
# uploads to a tmp dir. A real tenant process fixes DEALEROS_STORAGE_DIR at boot, so the
# import-time evaluation is fine.
UPLOAD_DIR = uploads_dir()

# Deliberately conservative -- images and common office/PDF documents only, matching
# what a dealership employee would actually attach (a photo of damage, a scanned form),
# not an arbitrary-file-upload surface.
ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

MAX_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB


def create_document(uploaded_by, filename, content_type, file_bytes, linked_entity_id=None, linked_entity_type=None):

    if content_type not in ALLOWED_CONTENT_TYPES:
        return None, f"File type '{content_type}' isn't supported"

    if len(file_bytes) > MAX_SIZE_BYTES:
        return None, "File is larger than the 15MB limit"

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    document_id = id_generator.generate("DOC")

    safe_name = filename.replace("/", "_").replace("\\", "_")

    storage_path = os.path.join(UPLOAD_DIR, f"{document_id}_{safe_name}")

    with open(storage_path, "wb") as f:
        f.write(file_bytes)

    entity = Entity(
        id=document_id,
        entity_type=DOCUMENT,
        attributes={
            "DocumentNumber": document_id,
            "EntityType": linked_entity_type or "",
            "EntityID": linked_entity_id or "",
            "FileName": filename,
            "ContentType": content_type,
            "SizeBytes": len(file_bytes),
            "StoragePath": storage_path,
            "UploadedBy": uploaded_by,
            "CreatedAt": datetime.now(timezone.utc).isoformat(),
        },
    )

    ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return entity, None
