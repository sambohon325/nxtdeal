"""
Thin API-layer function for chat file attachments (session 47). Any authenticated role
can upload -- matches the "any role creates" precedent used everywhere else.
"""

from core.documents import create_document


def _serialize(entity):
    return {
        "id": entity.id,
        "filename": entity.attributes.get("FileName"),
        "content_type": entity.attributes.get("ContentType"),
        "size_bytes": entity.attributes.get("SizeBytes"),
        "created_at": entity.attributes.get("CreatedAt"),
    }


def upload_document_api(uploaded_by, filename, content_type, file_bytes, linked_entity_id=None, linked_entity_type=None):

    if not file_bytes:
        return {"error": "File is empty"}

    entity, error = create_document(uploaded_by, filename, content_type, file_bytes, linked_entity_id, linked_entity_type)

    if error:
        return {"error": error}

    return _serialize(entity)
