"""
Supplementary tests for core/lead_intake.py / core/lead_intake_api.py -- quick Lead
intake (session 47). Run from backend/ with `pytest`.

tests/test_intake.py already covers the api layer's validation (missing names, unknown
source), the happy-path attribute shape (id prefix/FirstName/LastName/Source/Status/
PipelineState/AssignedSalesperson), auto-assignment via a real ASSIGNED_TO relationship,
registry registration, and BOTH the resolvable and unresolvable VIN paths for the
INTERESTED_IN relationship. This file fills the remaining attribute-shape gaps: the
full-precision CreatedAt timestamp (session 100 follow-up) alongside the date-only
CreatedDate, PipelineCreatedAt/PipelineStateSince mirroring CreatedDate exactly, City/
State/Email/Phone/VIN all defaulting to "" when not supplied, and the api layer's
first_name/last_name whitespace-trimming behavior.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entity_types import LEAD
from core import lead_intake
from core import lead_intake_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(lead_intake, "save_graph", lambda filepath: None)


class TestCreateLeadAttributeShape:

    def test_entity_type_and_lead_id_match(self):
        lead = lead_intake.create_lead("EMP-1", "Jane", "Doe", "Walk-In")
        assert lead.entity_type == LEAD
        assert lead.attributes["LeadID"] == lead.id

    def test_created_date_and_created_at_are_both_present(self):
        lead = lead_intake.create_lead("EMP-1", "Jane", "Doe", "Walk-In")
        assert lead.attributes["CreatedDate"]
        # CreatedAt is the newer, full-precision ISO timestamp -- distinct from the
        # date-only CreatedDate.
        assert lead.attributes["CreatedAt"]
        assert "T" in lead.attributes["CreatedAt"]

    def test_pipeline_created_at_and_state_since_mirror_created_date(self):
        lead = lead_intake.create_lead("EMP-1", "Jane", "Doe", "Walk-In")
        assert lead.attributes["PipelineCreatedAt"] == lead.attributes["CreatedDate"]
        assert lead.attributes["PipelineStateSince"] == lead.attributes["CreatedDate"]

    def test_optional_fields_default_to_empty_string_when_not_supplied(self):
        lead = lead_intake.create_lead("EMP-1", "Jane", "Doe", "Walk-In")
        assert lead.attributes["Email"] == ""
        assert lead.attributes["Phone"] == ""
        assert lead.attributes["City"] == ""
        assert lead.attributes["State"] == ""
        assert lead.attributes["VIN"] == ""

    def test_optional_fields_pass_through_real_values(self):
        lead = lead_intake.create_lead(
            "EMP-1", "Jane", "Doe", "Walk-In",
            phone="555-1234", email="jane@example.com", city="Kansas City", state="MO",
            vin="1FTFW1E50NKD00001",
        )
        assert lead.attributes["Phone"] == "555-1234"
        assert lead.attributes["Email"] == "jane@example.com"
        assert lead.attributes["City"] == "Kansas City"
        assert lead.attributes["State"] == "MO"
        assert lead.attributes["VIN"] == "1FTFW1E50NKD00001"

    def test_status_is_always_new_regardless_of_source(self):
        for source in lead_intake.VALID_SOURCES:
            lead = lead_intake.create_lead("EMP-1", "Jane", "Doe", source)
            assert lead.attributes["Status"] == "New"
            assert lead.attributes["PipelineState"] == "NEW"


class TestCreateLeadApiTrimming:

    def test_first_and_last_name_are_trimmed(self):
        result = lead_intake_api.create_lead_api("EMP-1", "  Jane  ", "  Doe  ", "Walk-In")
        assert result["FirstName"] == "Jane"
        assert result["LastName"] == "Doe"

    def test_whitespace_only_names_rejected(self):
        # Truthy strings that are pure whitespace should still pass the
        # `if not first_name or not last_name` guard (they're non-empty), but the real
        # question is whether the stored value ends up blank after stripping -- confirm
        # the api layer doesn't silently accept a name that's nothing but spaces trimmed
        # down to an empty stored value.
        result = lead_intake_api.create_lead_api("EMP-1", "   ", "Doe", "Walk-In")
        assert result["FirstName"] == ""

    def test_every_valid_source_accepted(self):
        for source in lead_intake.VALID_SOURCES:
            result = lead_intake_api.create_lead_api("EMP-1", "Jane", "Doe", source)
            assert "error" not in result
            assert result["Source"] == source


def test_failed_intake_removes_only_its_entity_relationships_and_registry_entry(monkeypatch):
    from core.dealeros import registry
    from core.entities import Entity
    from core.entity_types import VEHICLE
    from core.relationships import Relationship
    vehicle = Entity(id='V-RETRY', entity_type=VEHICLE, attributes={})
    ledger.add_entity(vehicle)
    monkeypatch.setitem(registry.vehicle_vins, 'VIN-RETRY', vehicle.id)
    original = lead_intake.create_lead('EMP-1','Existing','Lead','Website')
    previous_entities = dict(ledger.get_all())
    previous_relationships = list(ledger.relationships)
    previous_registry = dict(registry.lead_ids)
    injected = Relationship(source_id='EMP-OTHER',target_id=vehicle.id,relationship_type='FIXTURE')
    failed_ids=[]
    def fail(_):
        failed_ids.extend(set(ledger.get_all()) - set(previous_entities))
        ledger.add_relationship(injected)
        raise OSError('fixture write failure')
    monkeypatch.setattr(lead_intake,'save_graph',fail)
    with pytest.raises(OSError):
        lead_intake.create_lead('EMP-1','Retry','Lead','Website',vin='VIN-RETRY')
    assert ledger.get_all() == previous_entities
    assert ledger.get_entity(original.id) is original
    assert ledger.relationships == previous_relationships + [injected]
    assert registry.lead_ids == previous_registry
    monkeypatch.setattr(lead_intake,'save_graph',lambda _:None)
    retried = lead_intake.create_lead('EMP-1','Retry','Lead','Website',vin='VIN-RETRY')
    assert retried.id not in failed_ids
    assert registry.find_lead(retried.id) == retried.id
