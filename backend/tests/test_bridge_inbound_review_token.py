from copy import deepcopy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import router, admin
from core import bridge_inbound as inbound, bridge_event_profiles as profiles, dealer_bridge as b
from core.bridge_adapters.adf_gateway import ADFGatewayVerifier
from core.dealeros import ledger
from tests.test_bridge_inbound import configured, ENDPOINT, KEY, bindings  # noqa: F401
from tests.test_bridge_sync import A, B, API, isolated  # noqa: F401


def token(system):return inbound.status(A,system)["gateways"][0]["review_token"]


def test_review_token_is_read_only_and_never_resolves_signing_material():
    system,_,_,provider,_=configured()
    provider.during_read=lambda:pytest.fail("Review must not resolve secrets")
    before=deepcopy(ledger.entities)
    first=token(system)
    assert isinstance(first,str) and len(first)==64 and token(system)==first
    assert ledger.entities==before and KEY not in str(inbound.status(A,system))


@pytest.mark.parametrize("change",["queue_limit","profile","environment","source_name","policy"])
def test_stale_gateway_review_cannot_enable_changed_configuration(change):
    system,profile,broker,provider,verifier=configured()
    reviewed=token(system)
    if change=="policy":inbound.configure(B,ENDPOINT,False)
    elif change=="source_name":b.get(system,"BridgeSystem")["name"]="Renamed synthetic source"
    else:
        inbound.unbind(ENDPOINT)
        environment="synthetic"
        if change=="profile":
            profile=profiles.propose(A,system,"Other provider",{"first_name":{"source":"name_full","transform":"text"}})["id"]
            profiles.approve(B,profile)
        if change=="environment":
            environment="sandbox"
            verifier=ADFGatewayVerifier(broker=broker,system_id=system,secret_reference="vault/gateway",account_ref="qa-gateway",environment=environment)
        inbound.bind(ENDPOINT,profile_id=profile,revision="gateway-v1",environment=environment,verifier=verifier,max_pending_batches=200 if change=="queue_limit" else 100)
    before=deepcopy(ledger.entities)
    with pytest.raises(ValueError,match="configuration or policy changed"):
        inbound.configure(A,ENDPOINT,True,"gateway-v1",reviewed)
    assert ledger.entities==before
    fresh=token(system)
    assert fresh!=reviewed
    inbound.configure(A,ENDPOINT,True,"gateway-v1",fresh)
    assert inbound.status(A,system)["gateways"][0]["effective_status"]=="ready"


def test_disable_does_not_require_a_current_review_token():
    system,_,_,_,_=configured()
    inbound.configure(A,ENDPOINT,False,"old", "0"*64)
    assert not inbound.status(A,system)["gateways"][0]["enabled"]


def test_http_token_fences_enable_and_does_not_authorize_api_principals():
    system,_,_,_,_=configured()
    app=FastAPI();app.include_router(router);app.dependency_overrides[admin]=lambda:A
    api=TestClient(app)
    reviewed=api.get(f"/dealer-bridge/systems/{system}/inbound").json()["gateways"][0]["review_token"]
    body={"enabled":True,"revision":"gateway-v1","review_token":reviewed}
    route=f"/dealer-bridge/inbound/{ENDPOINT}/policy"
    assert api.post(route,json={**body,"review_token":"short"}).status_code==422
    app.dependency_overrides[admin]=lambda:API
    assert api.post(route,json=body).status_code==403
    app.dependency_overrides[admin]=lambda:A
    inbound.configure(B,ENDPOINT,False)
    assert api.post(route,json=body).status_code==400
    assert not inbound.status(A,system)["gateways"][0]["enabled"]
