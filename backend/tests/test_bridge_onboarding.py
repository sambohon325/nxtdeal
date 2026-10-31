from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.dealer_bridge import admin, router
from core import dealer_bridge as bridge, bridge_onboarding as onboarding, bridge_runtime
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, API, isolated  # noqa: F401


def system():
    return bridge.connect(A, "Nortridge Loan System", "Synthetic servicing")["id"]


def test_legacy_system_gets_detached_defaults_without_writes():
    sid = system()
    before = deepcopy(ledger.entities)
    result = onboarding.read(A, sid)
    assert result["revision"] == 0 and len(result["unresolved_evidence"]) == 7
    result["details"]["record_types"].append("Payment")
    assert onboarding.read(A, sid)["details"]["record_types"] == []
    assert "onboarding" not in ledger.get_entity(sid).attributes
    assert len(ledger.entities) == len(before)


def test_evidence_never_grants_access_or_changes_import_state():
    sid = system()
    details = onboarding.defaults()
    details.update(product_version="Synthetic v1", deployment="hosted", record_types=["LoanAccount", "Payment"])
    details["evidence"] = {key: "available" for key in onboarding.EVIDENCE}
    before = deepcopy(bridge.get(sid, "BridgeSystem"))
    result = onboarding.update(A, sid, 0, details)
    assert result["revision"] == 1 and result["updated_by"] == A["employee_id"]
    assert result["unresolved_evidence"] == []
    after = deepcopy(bridge.get(sid, "BridgeSystem"))
    after.pop("onboarding")
    assert before == after
    assert bridge_runtime.describe(sid)["status"] == "unavailable"
    assert not bridge.system_map(A)["mappings"] and not bridge.system_map(A)["jobs"]
    details["record_types"].clear()
    assert onboarding.read(A, sid)["details"]["record_types"] == ["LoanAccount", "Payment"]


def test_stale_revision_and_agent_updates_cannot_replace_human_details():
    sid = system()
    onboarding.update(A, sid, 0, onboarding.defaults())
    with pytest.raises(ValueError, match="changed"):
        onboarding.update(B, sid, 0, onboarding.defaults())
    with pytest.raises(PermissionError):
        onboarding.update(API, sid, 1, onboarding.defaults())
    with pytest.raises(PermissionError):
        onboarding.read({**A, "workspace_id": "other"}, sid)
    assert onboarding.read(A, sid)["revision"] == 1


def test_save_failure_rolls_back_details_and_audit(monkeypatch):
    sid = system()
    count = len(ledger.entities)
    def fail(path):
        raise OSError("synthetic storage failure")
    monkeypatch.setattr(bridge, "save_graph", fail)
    with pytest.raises(OSError):
        onboarding.update(A, sid, 0, onboarding.defaults())
    assert onboarding.read(A, sid)["revision"] == 0
    assert len(ledger.entities) == count


@pytest.mark.parametrize("field,value", [("product_version", "x" * 121), ("product_version", "v1\nsecret"),
    ("deployment", "production_endpoint"), ("record_types", ["Payment", "Payment"]),
    ("record_types", ["DeviceCommand"]), ("record_types", "Payment"),
    ("evidence", {}), ("evidence", {"password": "secret"})])
def test_setup_rejects_unknown_or_unbounded_details(field, value):
    sid = system()
    details = onboarding.defaults()
    details[field] = value
    with pytest.raises(ValueError):
        onboarding.update(A, sid, 0, details)
    assert onboarding.read(A, sid)["revision"] == 0


def test_api_schema_forbids_credentials_and_requires_human_session():
    sid = system()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[admin] = lambda: A
    client = TestClient(app)
    path = f"/dealer-bridge/systems/{sid}/onboarding"
    assert client.get(path).json()["revision"] == 0
    payload = {"revision": 0, "details": onboarding.defaults()}
    assert client.post(path, json={**payload, "credentials": "never stored"}).status_code == 422
    assert client.post(path, json=payload).json()["revision"] == 1
    assert client.post(path, json=payload).status_code == 400
    app.dependency_overrides[admin] = lambda: API
    assert client.post(path, json={**payload, "revision": 1}).status_code == 403
