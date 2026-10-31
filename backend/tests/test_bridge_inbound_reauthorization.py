import pytest
from core import bridge_inbound as inbound, dealer_bridge as b, bridge_event_profiles as profiles
from core.bridge_adapters.adf_gateway import InvalidDelivery
from tests.test_bridge_inbound import configured, delivery, ENDPOINT, bindings  # noqa: F401
from tests.test_bridge_sync import A, B, API, isolated  # noqa: F401


def test_current_human_can_reauthorize_same_revision_after_previous_admin_loses_access(monkeypatch):
    system, _, _, provider, _ = configured()
    monkeypatch.setattr(inbound.credential_store, "get_record",
        lambda employee: {"role":"SALES" if employee == B["employee_id"] else "ADMIN"})
    provider.during_read = lambda: pytest.fail("Policy diagnostics must not resolve secrets")
    gateway = inbound.status(A, system)["gateways"][0]
    assert gateway["effective_status"] == "review_required"
    assert gateway["review_reasons"] == ["authorizing_administrator_unavailable"]
    assert gateway["can_review_policy"]
    with pytest.raises(InvalidDelivery): inbound.receive(*delivery())
    with pytest.raises(PermissionError): inbound.configure(API, ENDPOINT, True, "gateway-v1")
    inbound.configure(A, ENDPOINT, True, "gateway-v1")
    gateway = inbound.status(A, system)["gateways"][0]
    assert gateway["effective_status"] == "ready" and not gateway["review_reasons"]
    provider.during_read = None
    assert inbound.receive(*delivery())["status"] == "received_for_review"


@pytest.mark.parametrize("condition,reason", [
    ("pause","source_paused"), ("revoke","profile_unavailable_or_changed"),
    ("unapproved","profile_approval_required"), ("unbind","binding_unavailable"),
])
def test_unmet_prerequisites_explain_why_reauthorization_is_unavailable(condition, reason):
    system, profile, _, _, _ = configured()
    if condition == "pause": b.get(system, "BridgeSystem")["paused"] = True
    elif condition == "revoke": profiles.revoke(A, profile, "Synthetic profile replaced")
    elif condition == "unapproved": b.get(profile, "BridgeEventProfile")["status"] = "proposed"
    else: inbound.unbind(ENDPOINT)
    gateway = inbound.status(A, system)["gateways"][0]
    assert gateway["effective_status"] == "review_required"
    assert reason in gateway["review_reasons"] and not gateway["can_review_policy"]
    with pytest.raises(ValueError): inbound.configure(A, ENDPOINT, True, "gateway-v1")


def test_binding_change_requires_new_explicit_revision_and_cannot_silently_resume():
    system, profile, _, _, verifier = configured()
    inbound.bind(ENDPOINT, profile_id=profile, revision="gateway-v2", environment="synthetic", verifier=verifier)
    gateway = inbound.status(A, system)["gateways"][0]
    assert gateway["review_reasons"] == ["binding_review_required"]
    assert gateway["can_review_policy"] and gateway["effective_status"] == "review_required"
    with pytest.raises(ValueError): inbound.configure(A, ENDPOINT, True, "gateway-v1")
    with pytest.raises(InvalidDelivery): inbound.receive(*delivery())
    inbound.configure(A, ENDPOINT, True, "gateway-v2")
    assert inbound.status(A, system)["gateways"][0]["effective_status"] == "ready"
