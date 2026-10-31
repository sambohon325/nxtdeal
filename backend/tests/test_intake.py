"""
Tests for the five per-department quick-entry intake modules added in session 47
(core/field_notes, core/lead_intake, core/vehicle_intake, core/service_intake,
core/documents, plus their `*_api.py` wrappers) — see CLAUDE.md's session-47 note and
BUILD_QUEUE.md's "convert the loose test_*.py scripts to a real backend/tests/ pytest
suite as each module gets touched" rule. This is the first committed regression coverage
for those modules. Run from backend/ with `pytest`.

Every intake function calls `save_graph("storage/graph.json")` and `core/documents.py`
additionally writes raw bytes under `storage/uploads/`. The autouse fixtures below stub
both so the suite never touches the real graph or the real uploads dir — same precaution
tests/test_assets.py documents for its save_audit_log calls, and tests/test_auth.py for
save_credentials.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger, registry, id_generator
from core.relationship_types import (
    ASSIGNED_TO,
    INTERESTED_IN,
    AUTHORIZED,
    HAS_SERVICE_RECORD,
)

from core import field_notes, field_notes_api
from core import lead_intake, lead_intake_api
from core import vehicle_intake, vehicle_intake_api
from core import service_intake, service_intake_api
from core import documents, documents_api


@pytest.fixture(autouse=True)
def fresh_singletons():
    """Reset the three module-level singletons in place before/after every test.

    ledger.reset() clears entities+relationships (it exists for exactly this), but the
    registry (VIN/customer/lead lookup dicts) and id_generator (per-prefix counters) do
    NOT get reset by it, so clear them here too — otherwise ids and VIN registrations
    leak across tests. Same "mutate in place, never swap object identity" rule the other
    singletons follow (other modules hold direct `from core.dealeros import ...`
    references)."""

    def _reset():
        ledger.reset()

        registry.vehicle_vins.clear()
        registry.customer_ids.clear()
        registry.lead_ids.clear()
        registry.finance_ids.clear()
        registry.lenders.clear()
        registry.employee_ids.clear()
        registry.part_numbers.clear()

        for prefix in id_generator.counters:
            id_generator.counters[prefix] = 0

    _reset()

    yield

    _reset()


@pytest.fixture(autouse=True)
def no_real_disk_writes(monkeypatch, tmp_path):
    """Stub save_graph in every intake module's namespace (each did
    `from core.storage import save_graph`, so patch the imported reference) and point
    documents' UPLOAD_DIR at a per-test tmp dir so real uploads/ is never written."""

    for module in (field_notes, lead_intake, vehicle_intake, service_intake, documents):
        monkeypatch.setattr(module, "save_graph", lambda filepath: None)

    monkeypatch.setattr(documents, "UPLOAD_DIR", str(tmp_path / "uploads"))


# --------------------------------------------------------------------------
# field_notes
# --------------------------------------------------------------------------


def test_create_field_note_success():

    result = field_notes_api.create_field_note_api(
        "EMP-00001", "sales", "general", "Customer wants a follow-up call Monday"
    )

    assert "error" not in result
    assert result["department"] == "sales"
    assert result["category"] == "general"
    assert result["body"] == "Customer wants a follow-up call Monday"
    assert result["created_by"] == "EMP-00001"
    assert result["id"].startswith("NOTE-")


def test_field_note_requires_department():

    result = field_notes_api.create_field_note_api(
        "EMP-00001", "", "general", "body text"
    )

    assert "error" in result


def test_field_note_requires_nonblank_body():

    result = field_notes_api.create_field_note_api(
        "EMP-00001", "sales", "general", "   "
    )

    assert "error" in result


def test_field_note_rejects_unknown_category():

    result = field_notes_api.create_field_note_api(
        "EMP-00001", "sales", "not-a-category", "body text"
    )

    assert "error" in result


def test_field_note_body_is_trimmed():

    result = field_notes_api.create_field_note_api(
        "EMP-00001", "service", "recon", "  needs new tires  "
    )

    assert result["body"] == "needs new tires"


def test_field_note_resolves_vin_link_via_registry():

    registry.register_vehicle("1HGCV1F30LA000001", "VEH-00042")

    result = field_notes_api.create_field_note_api(
        "EMP-00001", "service", "maintenance", "oil change due",
        linked_entity_id="1HGCV1F30LA000001",
    )

    # A VIN (not a graph id) should be resolved to the real entity id.
    assert result["linked_entity_id"] == "VEH-00042"


def test_field_note_keeps_existing_entity_id_link_as_is():

    from core.entities import Entity
    from core.entity_types import VEHICLE

    ledger.add_entity(Entity(id="VEH-00099", entity_type=VEHICLE, attributes={}))

    result = field_notes_api.create_field_note_api(
        "EMP-00001", "inventory", "general", "detailing done",
        linked_entity_id="VEH-00099",
    )

    assert result["linked_entity_id"] == "VEH-00099"


def test_list_field_notes_filters_by_department_recent_first():

    field_notes.create_field_note("sales", "general", "first", "EMP-1")
    field_notes.create_field_note("service", "general", "other dept", "EMP-1")
    field_notes.create_field_note("sales", "general", "second", "EMP-1")

    sales_notes = field_notes_api.list_field_notes_api(department="sales")

    assert [n["body"] for n in sales_notes] == ["second", "first"]


def test_list_field_notes_respects_limit():

    for i in range(5):
        field_notes.create_field_note("sales", "general", f"note {i}", "EMP-1")

    assert len(field_notes_api.list_field_notes_api(limit=3)) == 3


# --------------------------------------------------------------------------
# lead_intake
# --------------------------------------------------------------------------


def test_create_lead_success_has_import_shaped_attributes():

    result = lead_intake_api.create_lead_api(
        "EMP-00001", "Jane", "Doe", "Walk-In", phone="555-1234", email="j@x.com"
    )

    assert "error" not in result
    assert result["id"].startswith("LEAD-")
    assert result["FirstName"] == "Jane"
    assert result["LastName"] == "Doe"
    assert result["Source"] == "Walk-In"
    assert result["Status"] == "New"
    # Same pipeline-state shape imports/lead_import.py writes.
    assert result["PipelineState"] == "NEW"
    assert result["AssignedSalesperson"] == "EMP-00001"


def test_create_lead_requires_names():

    assert "error" in lead_intake_api.create_lead_api("EMP-1", "", "Doe", "Walk-In")
    assert "error" in lead_intake_api.create_lead_api("EMP-1", "Jane", "", "Walk-In")


def test_create_lead_rejects_unknown_source():

    result = lead_intake_api.create_lead_api("EMP-1", "Jane", "Doe", "Skywriting")

    assert "error" in result


def test_create_lead_auto_assigns_to_creator():

    result = lead_intake_api.create_lead_api("EMP-00007", "Jane", "Doe", "Phone-Up")

    rels = ledger.get_entity_relationships(result["id"])

    assert any(
        r.source_id == "EMP-00007"
        and r.target_id == result["id"]
        and r.relationship_type == ASSIGNED_TO
        for r in rels
    )


def test_create_lead_registers_in_registry():

    result = lead_intake_api.create_lead_api("EMP-1", "Jane", "Doe", "Event")

    assert registry.find_lead(result["id"]) == result["id"]


def test_create_lead_with_resolvable_vin_links_interest():

    registry.register_vehicle("1FTFW1E50NKD00001", "VEH-00500")

    result = lead_intake_api.create_lead_api(
        "EMP-1", "Jane", "Doe", "Website", vin="1FTFW1E50NKD00001"
    )

    rels = ledger.get_entity_relationships(result["id"])

    assert any(
        r.target_id == "VEH-00500" and r.relationship_type == INTERESTED_IN
        for r in rels
    )


def test_create_lead_with_unresolvable_vin_creates_no_interest_rel():

    result = lead_intake_api.create_lead_api(
        "EMP-1", "Jane", "Doe", "Website", vin="NOTAREALVIN000000"
    )

    rels = ledger.get_entity_relationships(result["id"])

    assert not any(r.relationship_type == INTERESTED_IN for r in rels)


# --------------------------------------------------------------------------
# vehicle_intake
# --------------------------------------------------------------------------


def _valid_vehicle_kwargs(vin="1HGCV1F30LA111111"):
    return dict(
        vin=vin,
        year=2022,
        make="Honda",
        model="Accord",
        trim="EX",
        color="Blue",
        mileage=15000,
        condition="Used",
        price=24000,
        cost=20000,
        stock_number="STK-1",
        lot="Franchise New/Used",
    )


def test_create_vehicle_success_and_registers():

    result = vehicle_intake_api.create_vehicle_api(**_valid_vehicle_kwargs())

    assert "error" not in result
    assert result["id"].startswith("VEH-")
    assert result["VIN"] == "1HGCV1F30LA111111"
    assert result["DateSold"] == ""  # unsold on arrival
    assert registry.find_vehicle("1HGCV1F30LA111111") == result["id"]


def test_create_vehicle_requires_core_fields():

    kwargs = _valid_vehicle_kwargs()
    kwargs["make"] = ""

    assert "error" in vehicle_intake_api.create_vehicle_api(**kwargs)


def test_create_vehicle_rejects_bad_condition():

    kwargs = _valid_vehicle_kwargs()
    kwargs["condition"] = "Slightly Used"

    assert "error" in vehicle_intake_api.create_vehicle_api(**kwargs)


def test_create_vehicle_rejects_bad_lot():

    kwargs = _valid_vehicle_kwargs()
    kwargs["lot"] = "Back Alley"

    assert "error" in vehicle_intake_api.create_vehicle_api(**kwargs)


def test_create_vehicle_rejects_duplicate_vin():

    vehicle_intake_api.create_vehicle_api(**_valid_vehicle_kwargs())

    dup = vehicle_intake_api.create_vehicle_api(**_valid_vehicle_kwargs())

    assert "error" in dup


# --------------------------------------------------------------------------
# service_intake
# --------------------------------------------------------------------------


def test_create_service_record_success_technician_is_creator():

    result = service_intake_api.create_service_record_api(
        "EMP-00030", "1HGCV1F30LA222222", "Brake job", "Customer Pay"
    )

    assert "error" not in result
    assert result["id"].startswith("SRV-")
    # employee_value.py's real per-tech attribution keys off this being the graph id.
    assert result["Technician"] == "EMP-00030"
    assert result["Status"] == "Completed"


def test_create_service_record_requires_description():

    result = service_intake_api.create_service_record_api(
        "EMP-1", "VIN", "   ", "Customer Pay"
    )

    assert "error" in result


def test_create_service_record_rejects_bad_pay_type():

    result = service_intake_api.create_service_record_api(
        "EMP-1", "VIN", "desc", "Gift Card"
    )

    assert "error" in result


def test_create_service_record_rejects_bad_status():

    result = service_intake_api.create_service_record_api(
        "EMP-1", "VIN", "desc", "Warranty", status="Pending"
    )

    assert "error" in result


def test_create_service_record_links_customer_when_resolvable():

    registry.register_customer("CUST-EXT-1", "CUST-00010")

    result = service_intake_api.create_service_record_api(
        "EMP-1", "VIN", "desc", "Internal", customer_id="CUST-EXT-1"
    )

    rels = ledger.get_entity_relationships(result["id"])

    assert any(
        r.source_id == "CUST-00010"
        and r.relationship_type == AUTHORIZED
        for r in rels
    )


def test_create_service_record_links_vehicle_when_resolvable():

    registry.register_vehicle("1HGCV1F30LA333333", "VEH-00700")

    result = service_intake_api.create_service_record_api(
        "EMP-1", "1HGCV1F30LA333333", "desc", "Warranty"
    )

    rels = ledger.get_entity_relationships(result["id"])

    assert any(
        r.source_id == "VEH-00700"
        and r.relationship_type == HAS_SERVICE_RECORD
        for r in rels
    )


# --------------------------------------------------------------------------
# documents
# --------------------------------------------------------------------------


def test_upload_document_success_writes_file_and_entity():

    result = documents_api.upload_document_api(
        "EMP-00001", "damage.png", "image/png", b"\x89PNG fake bytes"
    )

    assert "error" not in result
    assert result["id"].startswith("DOC-")
    assert result["filename"] == "damage.png"
    assert result["content_type"] == "image/png"
    assert result["size_bytes"] == len(b"\x89PNG fake bytes")

    entity = ledger.get_entity(result["id"])
    assert entity is not None
    # The raw bytes were written to the (tmp) upload dir.
    assert os.path.exists(entity.attributes["StoragePath"])


def test_upload_document_rejects_empty_file():

    result = documents_api.upload_document_api(
        "EMP-1", "empty.png", "image/png", b""
    )

    assert "error" in result


def test_upload_document_rejects_disallowed_content_type():

    result = documents_api.upload_document_api(
        "EMP-1", "evil.exe", "application/x-msdownload", b"MZ..."
    )

    assert "error" in result


def test_upload_document_rejects_oversize_file():

    big = b"x" * (documents.MAX_SIZE_BYTES + 1)

    result = documents_api.upload_document_api(
        "EMP-1", "huge.pdf", "application/pdf", big
    )

    assert "error" in result


def test_upload_document_captures_linked_entity():

    result = documents_api.upload_document_api(
        "EMP-1", "form.pdf", "application/pdf", b"%PDF-1.4",
        linked_entity_id="LEAD-00001", linked_entity_type="LEAD",
    )

    entity = ledger.get_entity(result["id"])

    assert entity.attributes["EntityID"] == "LEAD-00001"
    assert entity.attributes["EntityType"] == "LEAD"
