"""Native conversion must retain imported contact information without auto-converting."""
from copy import deepcopy
from core import dealer_bridge as b, lead_conversion
from core.dealeros import ledger, registry
from core.entities import Entity
from tests.test_dealer_bridge import A, B, setup, imported, isolated  # noqa: F401


def test_imported_lead_phone_survives_explicit_native_customer_conversion(monkeypatch):
    monkeypatch.setattr(lead_conversion, "save_graph", lambda _: None)
    monkeypatch.setattr(registry, "customer_ids", {})
    system, _ = setup()
    mapping = b.propose_mapping(A, system, "Lead", "leads", {
        field: {"source": field, "transform": "text"} for field in ("first_name", "email", "phone")})["id"]
    b.approve_mapping(B, mapping)
    imported("external_id,modified_at,first_name,email,phone\nl1,2026-10-01T00:00:00Z,Pilot,pilot@example.invalid,+15555550100\n", mapping)
    lead = next(entity for entity in ledger.entities.values() if entity.entity_type == "Lead")
    assert lead.attributes["phone"] == lead.attributes["Phone"] == "+15555550100"
    assert not any(entity.entity_type == "Customer" for entity in ledger.entities.values())
    observations = deepcopy(b.chrono_observations(A))
    customer = lead_conversion.convert_lead_to_customer(lead.id, B["employee_id"])
    assert customer.attributes["Phone"] == "+15555550100"
    assert customer.attributes["Email"] == "pilot@example.invalid"
    assert b.chrono_observations(A) == observations


def test_older_canonical_only_phone_is_preserved_but_native_clear_takes_precedence(monkeypatch):
    monkeypatch.setattr(lead_conversion, "save_graph", lambda _: None)
    monkeypatch.setattr(registry, "customer_ids", {})
    for record_id, attributes, expected in [
        ("old-bridge-lead", {"phone": "+15555550100"}, "+15555550100"),
        ("native-cleared-lead", {"phone": "+15555550100", "Phone": ""}, ""),
    ]:
        ledger.add_entity(Entity(record_id, "Lead", attributes))
        customer = lead_conversion.convert_lead_to_customer(record_id, B["employee_id"])
        assert customer.attributes["Phone"] == expected


def test_event_lead_conversion_preserves_source_identity_and_replay(monkeypatch):
    from core import bridge_event_imports as imports, bridge_event_profiles as profiles
    from tests.test_bridge_event_imports import staged
    from tests.test_bridge_adf_discovery import ADF
    monkeypatch.setattr(lead_conversion, "save_graph", lambda _: None)
    monkeypatch.setattr(registry, "customer_ids", {})
    system, profile, job = staged()
    profiles.approve(B, profile)
    imports.validate(A, job); imports.activate(B, job)
    history = imports.lineage(A, system, "Provider", "private-id")
    lead_id = history["canonical_id"]
    before = deepcopy(b.chrono_observations(A))
    assert not any(e.entity_type == "Customer" for e in ledger.entities.values())
    customer = lead_conversion.convert_lead_to_customer(lead_id, B["employee_id"])
    assert customer.attributes["Email"] == "private@example.com"
    assert ledger.get_entity(lead_id).attributes["ConvertedCustomerID"] == customer.id
    assert b.chrono_observations(A) == before
    assert imports.lineage(A, system, "Provider", "private-id")["canonical_id"] == lead_id
    replay = imports.stage(A, profile, ADF)["id"]
    assert imports.validate(A, replay)["rows"][0]["status"] == "duplicate"
    assert imports.activate(B, replay)["created"] == 0
    assert len([e for e in ledger.entities.values() if e.entity_type == "Customer"]) == 1
    assert len([e for e in ledger.entities.values() if e.entity_type == "Lead"]) == 1
