"""Source consent is retained evidence, not automatic outbound permission."""
import pytest

from core import dealer_bridge as bridge, agent_actions
from core.bridge_lineage import lookup
from core.dealeros import ledger
from core.entities import Entity
from tests.test_dealer_bridge import A, B, setup, imported, isolated  # noqa: F401


def import_consent(status, channel="sms"):
    system, customers = setup()
    imported(mapping=customers)
    customer = next(e for e in ledger.entities.values() if e.entity_type == "Customer")
    customer.attributes.update(phone="+15555550100", consent={"sms": True, "email": True})
    mapping = bridge.propose_mapping(A, system, "Consent", "consents", {
        "customer_id": {"source": "customer", "transform": "external_id", "object_type": "customers"},
        **{field: {"source": field, "transform": "text"} for field in ("channel", "status", "occurred_at")}})["id"]
    bridge.approve_mapping(B, mapping)
    imported(f"external_id,modified_at,customer,channel,status,occurred_at\nc1,2026-10-01T00:00:00Z,1,{channel},{status},2026-10-01T00:00:00Z\n", mapping)
    return system, customer


@pytest.mark.parametrize("status", ["granted", "opted_in", "subscribed", "revoked", "unknown"])
def test_source_consent_does_not_grant_send_permission_even_with_legacy_flag(status, monkeypatch):
    system, customer = import_consent(status)
    monkeypatch.setattr(agent_actions, "connected", lambda capability: True)
    record = next(e for e in ledger.entities.values() if e.entity_type == "ImportedConsent")
    assert record.attributes["canonical_kind"] == "Consent"
    assert record.attributes["import_semantics"] == "observation_only"
    assert not agent_actions.channel_consent(customer, "sms")
    with pytest.raises(PermissionError, match="consent"):
        agent_actions.validate(A, "sms.send", {"customer_id": customer.id, "body": "Must stay blocked"})
    assert lookup(A, system, "consents", "c1")["current_values"]["status"] == status
    # Another channel retains its independent native permission.
    assert agent_actions.channel_consent(customer, "email")


@pytest.mark.parametrize("native_time,expected", [
    ("2026-09-30T00:00:00Z", False), ("2026-10-01T00:00:00Z", False), ("2026-10-02T00:00:00Z", True)])
def test_only_a_later_native_consent_decision_can_supersede_source_evidence(native_time, expected):
    _, customer = import_consent("revoked")
    ledger.add_entity(Entity("native-consent", "Consent", {
        "customer_id": customer.id, "channel": "sms", "status": "granted", "occurred_at": native_time}))
    assert agent_actions.channel_consent(customer, "sms") is expected
    customer.attributes["do_not_contact"] = True
    assert not agent_actions.channel_consent(customer, "sms")


def test_foreign_workspace_consent_cannot_override_native_permission():
    _, customer = import_consent("revoked")
    record = next(e for e in ledger.entities.values() if e.entity_type == "ImportedConsent")
    record.attributes["workspace_id"] = "foreign-workspace"
    assert agent_actions.channel_consent(customer, "sms")


@pytest.mark.parametrize("source_channel", ["SMS", " Sms ", "EMAIL", " Email "])
def test_channel_casing_cannot_hide_an_imported_opt_out(source_channel):
    _, customer = import_consent("revoked", source_channel)
    assert not agent_actions.channel_consent(customer, source_channel.strip().lower())
