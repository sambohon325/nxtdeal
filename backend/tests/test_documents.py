"""
Tests for core/documents.py / core/documents_api.py -- the generic categorized
Document vault + chat-attachment upload mechanism (content-type/size validation,
real file write, real Document entity creation).

tests/test_intake.py already has 5 real tests calling documents_api.upload_document_api()
directly (success, empty-file rejection, disallowed-content-type rejection, oversize
rejection, linked-entity capture) -- this file gives core.documents.create_document()
its own direct, bypass-the-API-layer coverage (TestCreateDocument), including the one
real, honest gap create_document() itself has: it has no empty-file guard of its own --
that check only exists in documents_api.upload_document_api(), one layer up -- so calling
create_document() directly with b"" is real, valid, uncovered behavior worth documenting.
TestUploadDocumentApi re-confirms the API wrapper's own behavior directly against this
module too, same "re-confirm, not just rely on a transitive cluster test" precedent
test_escalation_routing.py already established.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entity_types import DOCUMENT
from core import documents
from core import documents_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch, tmp_path):
    monkeypatch.setattr(documents, "save_graph", lambda filepath: None)
    monkeypatch.setattr(documents, "UPLOAD_DIR", str(tmp_path / "uploads"))


class TestCreateDocument:

    def test_creates_a_real_entity_and_writes_the_real_file(self):
        entity, error = documents.create_document(
            "EMP-1", "photo.png", "image/png", b"\x89PNG fake bytes"
        )

        assert error is None
        assert entity.entity_type == DOCUMENT
        assert entity.id.startswith("DOC-")
        assert entity.attributes["FileName"] == "photo.png"
        assert entity.attributes["ContentType"] == "image/png"
        assert entity.attributes["SizeBytes"] == len(b"\x89PNG fake bytes")
        assert entity.attributes["UploadedBy"] == "EMP-1"
        assert os.path.exists(entity.attributes["StoragePath"])
        with open(entity.attributes["StoragePath"], "rb") as f:
            assert f.read() == b"\x89PNG fake bytes"

        # The entity actually landed in the real ledger too, not just returned.
        assert ledger.get_entity(entity.id) is entity

    def test_rejects_a_disallowed_content_type(self):
        entity, error = documents.create_document(
            "EMP-1", "evil.exe", "application/x-msdownload", b"MZ..."
        )

        assert entity is None
        assert error is not None
        assert "application/x-msdownload" in error

    def test_rejects_an_oversize_file(self):
        big = b"x" * (documents.MAX_SIZE_BYTES + 1)

        entity, error = documents.create_document(
            "EMP-1", "huge.pdf", "application/pdf", big
        )

        assert entity is None
        assert error is not None
        assert "15MB" in error

    def test_accepts_a_file_exactly_at_the_size_limit(self):
        exactly_max = b"x" * documents.MAX_SIZE_BYTES

        entity, error = documents.create_document(
            "EMP-1", "max.pdf", "application/pdf", exactly_max
        )

        assert error is None
        assert entity.attributes["SizeBytes"] == documents.MAX_SIZE_BYTES

    def test_generates_a_unique_doc_prefixed_id_per_call(self):
        first, _ = documents.create_document("EMP-1", "a.pdf", "application/pdf", b"a")
        second, _ = documents.create_document("EMP-1", "b.pdf", "application/pdf", b"b")

        assert first.id != second.id
        assert first.id.startswith("DOC-")
        assert second.id.startswith("DOC-")

    def test_captures_a_real_linked_entity_type_and_id_when_given(self):
        entity, _ = documents.create_document(
            "EMP-1", "form.pdf", "application/pdf", b"%PDF-1.4",
            linked_entity_id="LEAD-00001", linked_entity_type="LEAD",
        )

        assert entity.attributes["EntityID"] == "LEAD-00001"
        assert entity.attributes["EntityType"] == "LEAD"

    def test_defaults_linked_entity_fields_to_empty_string_when_not_given(self):
        entity, _ = documents.create_document(
            "EMP-1", "form.pdf", "application/pdf", b"%PDF-1.4"
        )

        assert entity.attributes["EntityID"] == ""
        assert entity.attributes["EntityType"] == ""

    def test_sanitizes_path_separators_in_the_filename_for_the_storage_path(self):
        entity, error = documents.create_document(
            "EMP-1", "../../etc/passwd", "text/plain", b"not really passwd"
        )

        assert error is None
        # The original, unsafe filename is preserved as metadata...
        assert entity.attributes["FileName"] == "../../etc/passwd"
        # ...but the real on-disk path has every "/" (and "\\") stripped out of the
        # sanitized name, so this never actually writes outside the real upload
        # directory -- the file lands directly inside UPLOAD_DIR, not a subdirectory.
        storage_path = entity.attributes["StoragePath"]
        assert os.path.dirname(storage_path) == documents.UPLOAD_DIR
        assert os.path.exists(storage_path)

    def test_real_honest_gap_create_document_itself_has_no_empty_file_guard(self):
        # documents.create_document() has no empty-bytes check of its own -- that
        # guard lives one layer up, in documents_api.upload_document_api(). Calling
        # this function directly with b"" is real, valid behavior: it writes a real
        # 0-byte file and creates a real entity rather than rejecting it.
        entity, error = documents.create_document(
            "EMP-1", "empty.png", "image/png", b""
        )

        assert error is None
        assert entity.attributes["SizeBytes"] == 0
        assert os.path.exists(entity.attributes["StoragePath"])
        assert os.path.getsize(entity.attributes["StoragePath"]) == 0

    def test_records_a_real_created_at_timestamp(self):
        entity, _ = documents.create_document(
            "EMP-1", "a.pdf", "application/pdf", b"a"
        )

        assert entity.attributes["CreatedAt"]
        assert "T" in entity.attributes["CreatedAt"]


class TestDocumentsApiSerialize:

    def test_serializes_only_the_expected_public_fields(self):
        entity, _ = documents.create_document(
            "EMP-1", "photo.png", "image/png", b"\x89PNG fake bytes",
            linked_entity_id="LEAD-1", linked_entity_type="LEAD",
        )

        result = documents_api._serialize(entity)

        assert result == {
            "id": entity.id,
            "filename": "photo.png",
            "content_type": "image/png",
            "size_bytes": len(b"\x89PNG fake bytes"),
            "created_at": entity.attributes["CreatedAt"],
        }
        # Deliberately does not leak the raw on-disk StoragePath or UploadedBy.
        assert "storage_path" not in result
        assert "uploaded_by" not in result


class TestUploadDocumentApi:

    def test_rejects_an_empty_file_before_ever_calling_create_document(self, monkeypatch):
        def _should_not_be_called(*args, **kwargs):
            raise AssertionError("create_document should not be called for an empty file")

        monkeypatch.setattr(documents_api, "create_document", _should_not_be_called)

        result = documents_api.upload_document_api("EMP-1", "empty.png", "image/png", b"")

        assert result == {"error": "File is empty"}

    def test_success_returns_the_real_serialized_shape(self):
        result = documents_api.upload_document_api(
            "EMP-1", "photo.png", "image/png", b"\x89PNG fake bytes"
        )

        assert "error" not in result
        assert result["id"].startswith("DOC-")
        assert result["filename"] == "photo.png"
        assert result["content_type"] == "image/png"
        assert result["size_bytes"] == len(b"\x89PNG fake bytes")

        # A real entity actually landed on the ledger, not just a dict shape.
        entity = ledger.get_entity(result["id"])
        assert entity is not None
        assert entity.entity_type == DOCUMENT

    def test_propagates_the_real_disallowed_content_type_error(self):
        result = documents_api.upload_document_api(
            "EMP-1", "evil.exe", "application/x-msdownload", b"MZ..."
        )

        assert "error" in result
        assert "application/x-msdownload" in result["error"]

    def test_propagates_the_real_oversize_error(self):
        big = b"x" * (documents.MAX_SIZE_BYTES + 1)

        result = documents_api.upload_document_api(
            "EMP-1", "huge.pdf", "application/pdf", big
        )

        assert "error" in result
        assert "15MB" in result["error"]

    def test_captures_a_real_linked_entity_through_the_api_layer(self):
        result = documents_api.upload_document_api(
            "EMP-1", "form.pdf", "application/pdf", b"%PDF-1.4",
            linked_entity_id="LEAD-00001", linked_entity_type="LEAD",
        )

        entity = ledger.get_entity(result["id"])
        assert entity.attributes["EntityID"] == "LEAD-00001"
        assert entity.attributes["EntityType"] == "LEAD"
