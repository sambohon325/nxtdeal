import asyncio
from copy import deepcopy

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from api.routers.dealer_bridge import router, admin
from api.routers.bridge_inbound import receive_adf
from core import bridge_inbound as inbound, dealer_bridge as b, bridge_activity
from core.dealeros import ledger
from tests.test_bridge_inbound import configured, delivery, ENDPOINT, bindings  # noqa: F401
from tests.test_bridge_sync import A, B, API, isolated  # noqa: F401


def client():
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: B
    return TestClient(app), app


def headers(values):
    return {"Content-Type":"application/xml; charset=utf-8", "X-Nxtdeal-Delivery-ID":values[1],
            "X-Nxtdeal-Signed-At":values[2], "X-Nxtdeal-Signature":values[3]}


def test_public_signature_route_stages_and_idempotently_acknowledges_without_session():
    system, _, _, _, _ = configured()
    api, app = client()
    app.dependency_overrides[admin] = lambda: pytest.fail("Inbound signature route must not accept or require session authority")
    values = delivery()
    first = api.post(f"/dealer-bridge/inbound/adf/{ENDPOINT}", headers=headers(values), content=values[4])
    assert first.status_code == 202 and first.json()["status"] == "received_for_review"
    assert set(first.json()) == {"status", "receipt_id"}
    again = api.post(f"/dealer-bridge/inbound/adf/{ENDPOINT}", headers=headers(values), content=values[4])
    assert again.status_code == 202 and again.json()["status"] == "already_received"
    assert not any(e.entity_type in {"Lead","SourceObservation"} for e in ledger.get_all().values())
    actions = bridge_activity.read(A,system)["activities"]
    assert {"inbound.enable","inbound.received"} <= {record["action"] for record in actions}
    assert "private@example.com" not in first.text


def test_administrator_policy_controls_are_human_only_strict_and_workspace_scoped():
    system, _, _, _, _ = configured(enabled=False)
    api, app = client()
    result = api.get(f"/dealer-bridge/systems/{system}/inbound").json()["gateways"][0]
    assert result["effective_status"] == "disabled" and result["binding_available"]
    body = {"enabled":True,"revision":"gateway-v1"}
    app.dependency_overrides[admin] = lambda: API
    assert api.post(f"/dealer-bridge/inbound/{ENDPOINT}/policy",json=body).status_code == 403
    app.dependency_overrides[admin] = lambda: B
    assert api.post(f"/dealer-bridge/inbound/{ENDPOINT}/policy",json={**body,"enabled":"true"}).status_code == 422
    assert api.post(f"/dealer-bridge/inbound/{ENDPOINT}/policy",json=body).status_code == 200
    assert api.get(f"/dealer-bridge/systems/{system}/inbound").json()["gateways"][0]["effective_status"] == "ready"
    app.dependency_overrides[admin] = lambda: {**B,"workspace_id":"foreign"}
    assert api.get(f"/dealer-bridge/systems/{system}/inbound").status_code == 403


@pytest.mark.parametrize("change,expected", [("missing",400),("duplicate",400),("signature",403),("mime",415),
    ("compressed",415),("length",413),("ambiguous",400),("mismatch",400),("malformed",400)])
def test_http_envelope_rejection_never_echoes_body_or_creates_job(change, expected):
    configured()
    api, _ = client()
    values = delivery(body=b"private-invalid-xml") if change == "malformed" else delivery()
    raw_headers = list(headers(values).items())
    if change == "missing": raw_headers = [(key,value) for key,value in raw_headers if key != "X-Nxtdeal-Signature"]
    elif change == "duplicate": raw_headers.append(("X-Nxtdeal-Signature",values[3]))
    elif change == "signature": raw_headers = [(key,"0"*64 if key == "X-Nxtdeal-Signature" else value) for key,value in raw_headers]
    elif change == "mime": raw_headers = [(key,"application/json" if key == "Content-Type" else value) for key,value in raw_headers]
    elif change == "compressed": raw_headers.append(("Content-Encoding","gzip"))
    elif change == "length": raw_headers.append(("Content-Length","1000001"))
    elif change == "ambiguous": raw_headers.extend([("Content-Length",str(len(values[4]))),("Transfer-Encoding","chunked")])
    elif change == "mismatch": raw_headers.append(("Content-Length","1"))
    response = api.post(f"/dealer-bridge/inbound/adf/{ENDPOINT}",headers=raw_headers,content=values[4])
    assert response.status_code == expected, response.text
    assert "private" not in response.text
    assert not any(e.entity_type == "BridgeEventJob" for e in ledger.get_all().values())


def test_backpressure_and_save_failure_return_retryable_redacted_http_response(monkeypatch):
    system, _, _, _, _ = configured(limit=1)
    api, _ = client()
    one = delivery()
    assert api.post(f"/dealer-bridge/inbound/adf/{ENDPOINT}",headers=headers(one),content=one[4]).status_code == 202
    two = delivery(identity="delivery-2")
    response = api.post(f"/dealer-bridge/inbound/adf/{ENDPOINT}",headers=headers(two),content=two[4])
    assert response.status_code == 503 and response.headers["retry-after"] == "60"
    assert inbound.status(B,system)["gateways"][0]["effective_status"] == "queue_full"
    job = next(e.id for e in ledger.get_all().values() if e.entity_type == "BridgeEventJob")
    from core import bridge_event_imports as imports
    imports.cancel(B,job,"Synthetic batch reviewed and cancelled")
    before = {key:deepcopy(value.attributes) for key,value in ledger.entities.items()}
    def fail(path): raise OSError("PRIVATE persistence path")
    monkeypatch.setattr(b,"save_graph",fail)
    response = api.post(f"/dealer-bridge/inbound/adf/{ENDPOINT}",headers=headers(two),content=two[4])
    assert response.status_code == 503 and "PRIVATE" not in response.text
    assert before == {key:value.attributes for key,value in ledger.entities.items()}


def test_disable_unbound_policy_stays_available_to_administrator():
    system, _, _, _, _ = configured()
    inbound.unbind(ENDPOINT)
    assert inbound.status(B,system)["gateways"][0]["effective_status"] == "review_required"
    inbound.configure(B,ENDPOINT,False)
    result = inbound.status(B,system)["gateways"][0]
    assert result["effective_status"] == "disabled" and not result["binding_available"]


def test_stream_size_cap_without_content_length_and_disconnected_body():
    configured()
    values = delivery()
    raw_headers = [(key.lower().encode(),value.encode()) for key,value in headers(values).items()]
    async def run(messages):
        async def receive(): return messages.pop(0)
        request = Request({"type":"http","method":"POST","path":"/","headers":raw_headers},receive)
        with pytest.raises(HTTPException) as error: await receive_adf(ENDPOINT,request)
        return error.value.status_code
    assert asyncio.run(run([{"type":"http.request","body":b"x"*600000,"more_body":True},
                            {"type":"http.request","body":b"x"*400001,"more_body":False}])) == 413
    assert asyncio.run(run([{"type":"http.disconnect"}])) == 408
