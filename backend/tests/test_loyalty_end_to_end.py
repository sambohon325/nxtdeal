from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core import loyalty_program as lp, loyalty_workflows as flow
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, APPOINTMENT, SERVICE_RECORD, PART_SALE, DELIVERY
from api.routers.loyalty_program import router as staff_router, staff
from api.routers.loyalty_customer import router
from core.customer_verification_boundary import CustomerVerificationBoundary

ORIGIN={"Origin":"https://app.nxtdeal.app"}


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv("DEALEROS_STORAGE_DIR",str(tmp_path))
    monkeypatch.setattr(ledger,"entities",{})
    for cid in ("C1","C2"):
        ledger.add_entity(Entity(id=cid,entity_type=CUSTOMER,attributes={"CustomerID":cid,"Name":cid}))
    ledger.add_entity(Entity(id="A1",entity_type=APPOINTMENT,attributes={"customer_id":"C1","status":"scheduled","department":"Service","scheduled_start":(datetime.now(timezone.utc)+timedelta(days=10)).isoformat()}))
    ledger.add_entity(Entity(id="A2",entity_type=APPOINTMENT,attributes={"customer_id":"C2","status":"scheduled","department":"Service"}))
    ledger.add_entity(Entity(id="RO1",entity_type=SERVICE_RECORD,attributes={"CustomerID":"C1","Cost":200,"Status":"Completed","PayType":"Customer Pay"}))
    lp.save_document("program",lp.DEFAULT_PROGRAM|{"status":"active","terms":"Earn one point per eligible dollar. Rewards are subject to listed conditions.","enrollment_enabled":True,"earning_enabled":True,"redemption_enabled":True},"admin")
    lp.save_document("rule",dict(name="Service",status="active",trigger="service",calculation="per_dollar",points=1),"marketing")
    reward=lp.save_document("reward",dict(name="$25 service",status="active",point_cost=2500,discount_cents=2500,department="Service"),"marketing")
    lp.enroll("C1","Customer One","staff","enroll","1",legacy_points=3000)
    app=FastAPI()
    app.add_middleware(CustomerVerificationBoundary)
    app.include_router(staff_router)
    app.include_router(router)
    app.dependency_overrides[staff]=lambda:{"role":"ADMIN","employee_id":"EMP1"}
    client=TestClient(app)
    return client,reward


def login(client,cid="C1"):
    invitation=client.post(f"/loyalty/program/members/{cid}/invitation",json={"reason":"Checked photo ID in person"}).json()["invitation"]
    response=client.post("/customer/loyalty/session",json={"invitation":invitation},headers=ORIGIN)
    assert response.status_code==200,response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    return ORIGIN|{"X-Loyalty-CSRF":response.json()["csrf"]}


def test_customer_to_staff_to_receipt_full_journey(setup):
    client,reward=setup
    headers=login(client)
    view=client.get("/customer/loyalty",headers=ORIGIN).json()
    assert [a["id"] for a in view["appointments"]]==["A1"]
    assert view["member"]["available"]==3000
    response=client.post("/customer/loyalty/reserve",headers=headers,json={"request_key":"reserve","reward_id":reward["id"],"appointment_id":"A1"})
    assert response.status_code==200,response.text
    hold=response.json()["reservation_id"]
    assert datetime.fromisoformat(response.json()["expires_at"])>datetime.now(timezone.utc)+timedelta(days=10)
    staff_member=client.get("/loyalty/program/members/C1").json()
    assert (staff_member["available"],staff_member["reserved"])==(500,2500)
    result=client.post("/loyalty/program/transactions/RO1/complete",json={"reservation_id":hold})
    assert result.status_code==200,result.text
    receipt=result.json()
    assert (receipt["gross_cents"],receipt["discount_cents"],receipt["net_cents"])==(20000,2500,17500)
    assert receipt["points_earned"]==175
    assert receipt["balance_after"]==675
    view=client.get("/customer/loyalty",headers=ORIGIN).json()
    assert view["member"]["available"]==675
    assert view["receipts"][0]["points_used"]==2500
    assert len(view["notifications"])==1
    assert client.post("/loyalty/program/transactions/RO1/complete",json={"reservation_id":hold}).json()==receipt
    assert lp.get_member("C1")["available"]==675


def test_customer_session_has_no_staff_authority_and_requires_csrf(setup):
    client,reward=setup
    headers=login(client)
    assert client.post("/customer/loyalty/reserve",headers=ORIGIN,json={"request_key":"x","reward_id":reward["id"],"appointment_id":"A1"}).status_code==401
    assert client.get("/customer/loyalty",headers={"Origin":"https://evil.example"}).status_code==403
    assert client.post("/customer/loyalty/reserve",headers=headers,json={"request_key":"x","reward_id":reward["id"],"appointment_id":"A2"}).status_code==409
    assert client.post("/customer/loyalty/reserve",headers=headers,json={"customer_id":"C2","request_key":"x","reward_id":reward["id"],"appointment_id":"A1"}).status_code==422
    client.app.dependency_overrides.clear()
    assert client.get("/loyalty/program/workspace").status_code==401


def test_invitation_one_use_expiry_and_revoke(setup):
    client,_=setup
    code=flow.invite("C1","staff","Checked identity")["invitation"]
    _,result=flow.accept_invitation(code)
    with pytest.raises(lp.LoyaltyError):flow.accept_invitation(code)
    headers=login(client)
    client.post("/loyalty/program/members/C1/revoke-access",json={})
    assert client.get("/customer/loyalty",headers=ORIGIN).status_code==401
    code=flow.invite("C1","staff","Checked identity")["invitation"]
    with lp.transaction() as db:db.execute("UPDATE loyalty_invites SET expires_at='2000-01-01'")
    with pytest.raises(lp.LoyaltyError):flow.accept_invitation(code)


def test_old_verification_remains_blocked(setup):
    client,_=setup
    assert client.get("/public/garage/vehicles?token=old").status_code==503
    assert client.get("/customer/loyalty",headers=ORIGIN|{"Authorization":"Bearer old"}).status_code==401


def test_self_enrollment_terms_and_preferences(setup):
    client,_=setup
    headers=login(client,"C2")
    assert client.get("/customer/loyalty",headers=ORIGIN).json()["enrolled"] is False
    data={"request_key":"enroll","terms_version":"1","accepted":False}
    assert client.post("/customer/loyalty/enroll",headers=headers,json=data).status_code==422
    data["accepted"]=True
    assert client.post("/customer/loyalty/enroll",headers=headers,json=data).status_code==200
    assert client.post("/customer/loyalty/enroll",headers=headers,json=data).status_code==200
    assert client.post("/customer/loyalty/preferences",headers=headers,json={"promotions":True}).json()=={"promotions":True}
    assert client.get("/customer/loyalty",headers=ORIGIN).json()["preferences"]["promotions"] is True


def test_partial_and_full_native_refund(setup):
    client,reward=setup
    hold=flow.reserve_for_visit("C1",reward["id"],"A1","staff","hold")["reservation_id"]
    flow.complete_transaction("RO1","staff",hold)
    assert flow.refund("RO1",7500,"Returned part","r1","admin")["balance"]==600
    assert flow.refund("RO1",7500,"Returned part","r1","admin")["balance"]==600
    result=flow.refund("RO1",10000,"Full return","r2","admin")
    assert result["balance"]==3000
    with pytest.raises(lp.LoyaltyError):flow.refund("RO1",1,"Too much","r3","admin")
    assert flow.customer_view("C1")["receipts"][0]["refunded_cents"]==17500


def test_native_concurrency_once(setup):
    client,_=setup
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:flow.complete_transaction("RO1","staff"),range(4)))
    assert all(r==results[0] for r in results)
    assert lp.get_member("C1")["available"]==3200


def test_queue_reconciles_without_duplicate_earning(setup):
    client,_=setup
    flow.enqueue("RO1","service")
    assert flow.reconcile()["processed"]==1
    assert flow.reconcile()["processed"]==0
    assert lp.get_member("C1")["available"]==3200


def test_queue_waits_for_reserved_reward(setup):
    client,reward=setup
    flow.reserve_for_visit("C1",reward["id"],"A1","staff","reserve")
    flow.enqueue("RO1","service")
    assert flow.reconcile()["processed"]==0
    with lp.transaction() as db:
        assert db.execute("SELECT status FROM loyalty_jobs WHERE source_id='RO1'").fetchone()[0]=="awaiting_reward"


def test_rejects_unfinished_and_warranty_records(setup):
    client,_=setup
    ledger.entities["RO1"].attributes["Status"]="Open"
    with pytest.raises(lp.LoyaltyError):flow.complete_transaction("RO1","staff")
    ledger.entities["RO1"].attributes.update(Status="Completed",PayType="Warranty")
    with pytest.raises(lp.LoyaltyError):flow.complete_transaction("RO1","staff")

def test_customer_visit_request_is_idempotent_and_owned(setup,monkeypatch):
    client,_=setup
    from core import appointments
    monkeypatch.setattr(appointments,'save_graph',lambda _:None)
    headers=login(client)
    body={'scheduled_start':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),'location':'default','notes':'Oil change','request_key':'booking1'}
    first=client.post('/customer/loyalty/appointments',headers=headers,json=body)
    assert first.status_code==200,first.text
    assert first.json()==client.post('/customer/loyalty/appointments',headers=headers,json=body).json()
    entity=ledger.get_entity(first.json()['appointment_id'])
    assert entity.attributes['customer_id']=='C1'
    assert entity.attributes['confirmation_required'] is True
    assert entity.attributes['loyalty_booking_key']=='C1:booking1'
    with lp.transaction() as db:
        db.execute("DELETE FROM requests WHERE key='booking:C1:booking1'")
    assert first.json()==client.post('/customer/loyalty/appointments',headers=headers,json=body).json()
    with lp.transaction() as db:
        db.execute("DELETE FROM requests WHERE key='booking:C1:booking1'")
    body['notes']='Different request'
    assert client.post('/customer/loyalty/appointments',headers=headers,json=body).status_code==409


def test_parts_and_delivery_native_earning(setup,monkeypatch):
    from core import storage
    monkeypatch.setattr(storage,'save_graph',lambda _:None)
    lp.save_document('rule',dict(name='Parts',status='active',trigger='parts',calculation='per_dollar',points=2),'marketing')
    lp.save_document('rule',dict(name='Delivery',status='active',trigger='delivery',calculation='fixed',points=500),'marketing')
    ledger.add_entity(Entity(id='P1',entity_type=PART_SALE,attributes={'SalePrice':80,'QuantitySold':2}))
    flow.link_parts_sale('P1','C1','default','Verified invoice and photo ID','staff')
    assert flow.reconcile()['processed']==1
    assert flow.complete_transaction('P1','staff')['points_earned']==160
    ledger.add_entity(Entity(id='D1',entity_type=DELIVERY,attributes={'customer_id':'C1','status':'delivered'}))
    flow.enqueue('D1','sales')
    assert flow.reconcile()['processed']==1
    assert lp.get_member('C1')['available']==3660
    ledger.add_entity(Entity(id='P2',entity_type=PART_SALE,attributes={'SalePrice':80,'CustomerID':'C2'}))
    with pytest.raises(lp.LoyaltyError):flow.link_parts_sale('P2','C1','default','Verified invoice','staff')


def test_native_checkout_rejects_changed_source(setup):
    flow.complete_transaction('RO1','staff')
    ledger.entities['RO1'].attributes['Cost']=300
    with pytest.raises(lp.LoyaltyError):flow.complete_transaction('RO1','staff')


def test_service_cannot_refund_or_revoke(setup):
    client,_=setup
    login(client)
    client.app.dependency_overrides[staff]=lambda:{'role':'SERVICE','employee_id':'advisor'}
    assert client.post('/loyalty/program/transactions/RO1/refund',json={'refund_cents':10,'reason':'test','request_key':'x'}).status_code==403
    assert client.post('/loyalty/program/members/C1/revoke-access').status_code==403
    assert client.get('/loyalty/program/members/C1/connections').json()['permissions']=={'fulfill':True,'adjust':False}

def test_reconciliation_recovers_saved_native_source(setup):
    ledger.entities['RO1'].attributes['loyalty_finalized_at']=lp.now()
    assert flow.reconcile()['processed']==1
    assert flow.reconcile()['processed']==0
    assert lp.get_member('C1')['available']==3200
