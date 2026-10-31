import pytest
from core import bridge_inbound as inbound, dealer_bridge as b, bridge_event_imports as imports
from core.bridge_readiness import summarize
from tests.test_bridge_inbound import configured, delivery, ENDPOINT, bindings  # noqa: F401
from tests.test_bridge_sync import A, B, isolated  # noqa: F401


def test_policy_readiness_is_separate_from_received_evidence_and_does_not_probe_secrets():
    system, _, _, provider, _ = configured()
    def fail(): pytest.fail("Readiness must not resolve secret material")
    provider.during_read = fail
    report = inbound.status(B,system)
    assert report["policy_only"] and report["gateways"][0]["effective_status"] == "ready"
    assert report["received_delivery_count"] == 0 and report["last_received_at"] is None
    item = next(item for item in b.system_map(A)["systems"] if item["id"] == system)
    assert item["readiness"]["next_step"] == "monitor_inbound_review"
    assert not item["readiness"]["live_access"]
    assert item["readiness"]["inbound_policy_counts"] == {"ready":1}


def test_received_counts_are_scoped_and_staged_review_takes_precedence():
    system, _, _, _, _ = configured()
    inbound.receive(*delivery())
    report = inbound.status(A,system)
    assert report["received_delivery_count"] == 1 and report["last_received_at"]
    assert "private-id" not in str(report) and "Private Name" not in str(report)
    item = next(item for item in b.system_map(A)["systems"] if item["id"] == system)
    assert item["readiness"]["next_step"] == "validate_event_import"
    other = b.connect(A,"CSV","Other source")["id"]
    assert inbound.status(A,other)["received_delivery_count"] == 0


def test_disabled_and_unbound_gateways_have_honest_next_steps():
    system, _, _, _, _ = configured()
    inbound.unbind(ENDPOINT)
    item = next(item for item in b.system_map(A)["systems"] if item["id"] == system)
    assert item["readiness"]["next_step"] == "review_inbound_policy"
    inbound.configure(B,ENDPOINT,False)
    item = next(item for item in b.system_map(A)["systems"] if item["id"] == system)
    assert item["readiness"]["next_step"] == "review_inbound_options"


def test_inconsistent_receipt_is_not_counted_as_received_evidence():
    system, _, _, _, _ = configured()
    first = inbound.receive(*delivery())
    receipt = b.get(first["receipt_id"],"BridgeInboundDelivery")
    imports.cancel(B,receipt["job_id"],"Synthetic batch cancelled before evidence review")
    receipt["body_hash"] = "changed"
    report = inbound.status(A,system)
    assert report["received_delivery_count"] == 0 and report["delivery_evidence_issues"] == 1
    item = next(item for item in b.system_map(A)["systems"] if item["id"] == system)
    assert item["readiness"]["next_step"] == "review_inbound_evidence"


def test_other_source_gateway_report_cannot_change_guidance():
    result = summarize({"id":"source"},{},[],[],inbound={"system_id":"other", "gateways":[{"effective_status":"ready"}],"received_delivery_count":15})
    assert result["next_step"] == "discover_mapping"
    assert result["inbound_policy_counts"] == {} and result["received_delivery_count"] == 0
