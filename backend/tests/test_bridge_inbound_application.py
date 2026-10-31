"""Signed intake through the real app router and middleware stack, isolated by conftest."""
from fastapi.testclient import TestClient

from api.app import app
from core.dealeros import ledger
from tests.test_bridge_inbound import configured, delivery, ENDPOINT, bindings  # noqa: F401
from tests.test_bridge_inbound_http import headers
from tests.test_bridge_sync import isolated  # noqa: F401


def test_real_application_accepts_signed_intake_without_session_and_keeps_job_staged():
    configured()
    api = TestClient(app)
    values = delivery()
    response = api.post(f"/dealer-bridge/inbound/adf/{ENDPOINT}", headers=headers(values), content=values[4])
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "received_for_review"
    again = api.post(f"/dealer-bridge/inbound/adf/{ENDPOINT}", headers=headers(values), content=values[4])
    assert again.status_code == 202 and again.json()["status"] == "already_received"
    jobs = [e for e in ledger.get_all().values() if e.entity_type == "BridgeEventJob"]
    assert len(jobs) == 1 and jobs[0].attributes["status"] == "staged"
    assert not any(e.entity_type in {"Lead", "SourceObservation"} for e in ledger.get_all().values())


def test_gateway_signature_does_not_authorize_administrative_routes():
    system, _, _, _, _ = configured(enabled=False)
    api = TestClient(app)
    signed_headers = headers(delivery())
    assert api.get(f"/dealer-bridge/systems/{system}/inbound", headers=signed_headers).status_code == 401
    signed_headers["Content-Type"] = "application/json"
    result = api.post(f"/dealer-bridge/inbound/{ENDPOINT}/policy", headers=signed_headers,
                      json={"enabled":True, "revision":"gateway-v1"})
    assert result.status_code == 401


def test_real_application_rejects_unsigned_public_delivery_without_persisting():
    configured()
    api = TestClient(app)
    values = delivery()
    envelope = headers(values)
    envelope["X-Nxtdeal-Signature"] = "0" * 64
    response = api.post(f"/dealer-bridge/inbound/adf/{ENDPOINT}", headers=envelope, content=values[4])
    assert response.status_code == 403
    assert set(response.json()) == {"detail"}
    assert not any(e.entity_type == "BridgeEventJob" for e in ledger.get_all().values())
