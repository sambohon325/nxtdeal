from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import sales_crm_advanced as advanced
from api.routers import sales_crm as crm
from staff_auth_fixture import staff_token
from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship


def headers(role="SALES", employee="EMP-1"):
    return {"Authorization": "Bearer " + staff_token(employee, role)}


@pytest.fixture
def client(monkeypatch):
    ledger.reset()
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    app = FastAPI()
    app.include_router(advanced.router)
    app.include_router(crm.router)
    with TestClient(app) as c:
        yield c
    ledger.reset()


def seed():
    ledger.add_entity(Entity("L1", "Lead", {"Name":"Alex", "Email":"test@example.test", "Phone":"+1 (555) 123-4567", "PipelineState":"NEW", "Source":"Website", "marketing_email_consent":True}))
    ledger.add_entity(Entity("L2", "Lead", {"Name":"Alex Duplicate", "Email":"TEST@example.test", "Phone":"5551234567", "PipelineState":"CONTACTED", "DoNotContact":True}))
    ledger.add_entity(Entity("C1", "Customer", {"Name":"Another", "Email":"test@example.test"}))
    ledger.add_entity(Entity("TASK1", "LeadTask", {"lead_id":"L2", "completed":False, "due_at":"2000-01-01"}))
    ledger.add_entity(Entity("ACC1", "SalesCrmAccount", {"member_ids":["L1","L2"],"revision":1}))
    ledger.add_relationship(Relationship("E1","L1","ASSIGNED_TO"))
    ledger.add_relationship(Relationship("E2","L2","ASSIGNED_TO"))
    ledger.add_relationship(Relationship("L2","V1","INTERESTED_IN"))


def rule(field="kind", op="eq", value="Lead"):
    return {"field":field,"op":op,"value":value}


def rules(*groups):
    return {"groups":[{"conditions":g} for g in groups]}


def post(c, path, body, role="SALES", employee="EMP-1"):
    return c.post("/sales/crm"+path,json=body,headers=headers(role,employee))


def test_segment_boolean_rules_live_membership_and_pagination(client):
    seed()
    r=rules([rule(),rule("source","eq","Website")],[rule("kind","eq","Customer")])
    response=post(client,"/segments/preview",r)
    assert response.status_code==200
    assert {r["id"] for r in response.json()["records"]}=={"L1","C1"}
    ledger.get_entity("L1").attributes["Source"]="Walk-In"
    assert post(client,"/segments/preview",r).json()["total"]==1
    assert post(client,"/segments/preview?offset=50",r).json()["records"]==[]
    assert post(client,"/segments/preview",rules([rule("overdue_tasks","gt","0")])).json()["records"][0]["id"]=="L2"
    assert post(client,"/segments/preview",rules([rule("last_contact","empty","")])).json()["total"]==3
    assert post(client,"/segments/preview",rules([rule("last_contact","before","2026-01-01")])).json()["total"]==0


@pytest.mark.parametrize("body", [rules([rule("SSN")]),rules([rule("open_tasks","contains","1")]),rules([rule("name","gt","a")]),rules([rule("created_at","before","nonsense")]),rules([rule("overdue_tasks","gt","NaN")]),{"groups":[]}])
def test_invalid_segment_rules(client,body):
    assert post(client,"/segments/preview",body).status_code==422


def test_segments_permissions_revisions_and_persistence(client):
    body={"name":"Web inquiries","shared":False,**rules([rule()])}
    saved=post(client,"/segments",body).json()
    assert not client.get("/sales/crm/segments",headers=headers(employee="EMP-2")).json()["segments"]
    path="/sales/crm/segments/"+saved["id"]
    assert client.put(path,json={**body,"revision":1},headers=headers(employee="EMP-2")).status_code==403
    assert client.put(path,json={**body,"revision":9},headers=headers()).status_code==409
    assert client.put(path,json={**body,"shared":True,"revision":1},headers=headers()).status_code==200
    assert client.get("/sales/crm/segments",headers=headers(employee="EMP-2")).json()["segments"]
    ledger.reset();ledger.load(advanced.GRAPH_PATH)
    assert ledger.get_entity(saved["id"]).attributes["shared"] is True
    assert post(client,"/segments",body,role="SERVICE").status_code==403
    assert client.get("/sales/crm/segments").status_code==401


def test_merge_preview_safe_apply_and_archive(client):
    seed()
    groups=client.get("/sales/crm/duplicates",headers=headers()).json()["groups"]
    assert len(groups)==2 and all({r["kind"] for r in g["records"]}=={"Lead"} for g in groups)
    body={"survivor_id":"L1","duplicate_id":"L2"}
    preview=post(client,"/duplicates/preview",body).json()
    assert "marketing_email_consent" not in str(preview)
    assert preview["referencing_records"]==2
    request={**body,"token":preview["token"],"take_duplicate":["Name"]}
    assert post(client,"/duplicates/merge",request).status_code==403
    response=post(client,"/duplicates/merge",request,role="ADMIN")
    assert response.status_code==200, response.text
    a=ledger.get_entity("L1").attributes
    assert a["Name"]=="Alex Duplicate" and a["PipelineState"]=="NEW"
    assert a["DoNotContact"] is True and a["marketing_email_consent"] is False
    assert ledger.get_entity("TASK1").attributes["lead_id"]=="L1"
    assert ledger.get_entity("ACC1").attributes["member_ids"]==["L1"]
    assert ledger.get_entity("L2").entity_type=="SalesCrmMergedRecord"
    assert [r.source_id for r in ledger.relationships if r.relationship_type=="ASSIGNED_TO"]==["E1"]
    audit=ledger.get_entity(response.json()["audit_id"])
    assert audit.attributes["duplicate_before"]["PipelineState"]=="CONTACTED"
    assert post(client,"/duplicates/merge",request,role="ADMIN").status_code==422
    ledger.reset();ledger.load(advanced.GRAPH_PATH)
    assert ledger.get_entity("TASK1").attributes["lead_id"]=="L1"


def test_merge_rejects_stale_cross_kind_pending_and_rolls_back(client,monkeypatch):
    seed();body={"survivor_id":"L1","duplicate_id":"L2"}
    token=post(client,"/duplicates/preview",body).json()["token"]
    ledger.get_entity("L1").attributes["Phone"]="changed"
    assert post(client,"/duplicates/merge",{**body,"token":token},role="ADMIN").status_code==409
    assert post(client,"/duplicates/preview",{**body,"duplicate_id":"C1"}).status_code==422
    ledger.add_entity(Entity("PENDING",advanced.delivery.ACTION,{"recipient_id":"L2","status":"unknown"}))
    preview=post(client,"/duplicates/preview",body).json()
    assert preview["blocked_by"]==["PENDING"]
    assert post(client,"/duplicates/merge",{**body,"token":preview["token"]},role="ADMIN").status_code==409
    ledger.entities.pop("PENDING")
    token=post(client,"/duplicates/preview",body).json()["token"]
    before=deepcopy(ledger.entities)
    monkeypatch.setattr(advanced,"save_graph",lambda _: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        post(client,"/duplicates/merge",{**body,"token":token},role="ADMIN")
    assert ledger.entities==before


def sequence(client, channels=("call","email")):
    body={"name":"Follow-up","steps":[{"channel":c,"delay_minutes":0,"subject":"Follow-up","body":"Contact the customer"} for c in channels]}
    response=post(client,"/sequences",body)
    assert response.status_code==200,response.text
    return response.json()


def enroll(client, seq, ids=None, **extra):
    return post(client,f'/sequences/{seq["id"]}/enroll',{"recipient_ids":ids or ["L1"],"start_at":datetime.now(timezone.utc).isoformat(),**extra})


def test_sequence_task_schedule_idempotency_restart_and_delivery_gate(client, monkeypatch):
    seed();seq=sequence(client)
    enrollment=enroll(client,seq).json()[0]
    assert enroll(client,seq).status_code==409
    monkeypatch.setattr(advanced.delivery.marketing_delivery,"send",lambda _: pytest.fail("No sends allowed"))
    at=datetime.now(timezone.utc)+timedelta(seconds=1)
    advanced.run_due(at)
    e=ledger.get_entity(enrollment["id"])
    task_id=e.attributes["output_id"]
    assert ledger.get_entity(task_id).entity_type=="LeadTask"
    advanced.run_due(at);advanced.run_due(at)
    assert len([x for x in ledger.entities.values() if x.entity_type=="LeadTask"])==2
    ledger.reset();ledger.load(advanced.GRAPH_PATH)
    advanced.run_due(at)
    assert ledger.get_entity(enrollment["id"]).attributes["output_id"]==task_id
    ledger.get_entity(task_id).attributes["completed"]=True
    advanced.run_due(at);advanced.run_due(at)
    e=ledger.get_entity(enrollment["id"])
    action=ledger.get_entity(e.attributes["output_id"])
    assert action.entity_type==advanced.delivery.ACTION and action.attributes["status"]=="draft"
    action.attributes["status"]="accepted"
    advanced.run_due(at)
    assert e.attributes["status"]=="active" and e.attributes["step_index"]==1
    action.attributes["status"]="delivered"
    advanced.run_due(at)
    assert e.attributes["status"]=="completed"


def test_sequence_consent_optout_closed_lead_and_inbound_reply(client):
    seed();seq=sequence(client,("sms",))
    en=enroll(client,seq).json()[0];at=datetime.now(timezone.utc)+timedelta(seconds=1)
    advanced.run_due(at)
    e=ledger.get_entity(en["id"])
    assert e.attributes["output_id"] is None and "consent" in e.attributes["reason"]
    ledger.get_entity("L1").attributes["DoNotContact"]=True
    advanced.run_due(at)
    assert e.attributes["status"]=="stopped"
    ledger.get_entity("L1").attributes["DoNotContact"]=False
    en=enroll(client,seq).json()[0];e=ledger.get_entity(en["id"])
    ledger.add_entity(Entity("REPLY","FieldNote",{"linked_entity_id":"L1","direction":"inbound","category":"email","created_at":at.isoformat()}))
    advanced.run_due(at)
    assert e.attributes["status"]=="stopped" and "reply" in e.attributes["reason"]
    ledger.entities.pop("REPLY")
    en=enroll(client,seq).json()[0];e=ledger.get_entity(en["id"])
    ledger.get_entity("L1").attributes["PipelineState"]="SOLD"
    advanced.run_due(at)
    assert e.attributes["status"]=="stopped"


def test_sequence_pause_resume_snapshot_and_cancel_approval(client):
    seed();seq=sequence(client,("email",));en=enroll(client,seq).json()[0]
    at=datetime.now(timezone.utc)+timedelta(seconds=1);advanced.run_due(at)
    e=ledger.get_entity(en["id"]);action=ledger.get_entity(e.attributes["output_id"])
    action.attributes["status"]="approved"
    path=f'/enrollments/{e.id}/status'
    response=post(client,path,{"revision":e.attributes["revision"],"status":"paused"})
    assert response.status_code==200 and action.attributes["status"]=="cancelled"
    advanced.run_due(at)
    assert e.attributes["status"]=="paused"
    assert post(client,path,{"revision":1,"status":"active"}).status_code==409
    # A stale request restores state from rollback; refetch authoritative entity.
    e=ledger.get_entity(en["id"])
    assert post(client,path,{"revision":e.attributes["revision"],"status":"active"}).status_code==200
    e=ledger.get_entity(en["id"])
    assert e.attributes["output_id"] is None
    seqbody={"name":"Changed", "revision":1,"steps":[{"channel":"call","delay_minutes":10,"body":"New text"}]}
    assert client.put('/sales/crm/sequences/'+seq["id"],json=seqbody,headers=headers()).status_code==200
    assert e.attributes["steps"][0]["channel"]=="email"
    advanced.run_due(at)
    assert ledger.get_entity(e.attributes["output_id"]).id!=action.id


def test_enrollment_validation_segment_ownership_and_atomicity(client):
    seed();seq=sequence(client)
    assert enroll(client,seq,["C1"]).status_code==422
    assert enroll(client,seq,["L1","MISSING"]).status_code==422
    assert advanced.all_of(advanced.ENROLLMENT)==[]
    assert enroll(client,seq,start_at="2026-01-01T12:00:00").status_code==422
    segment=post(client,"/segments",{"name":"Private",**rules([rule()])}).json()
    response=post(client,f'/sequences/{seq["id"]}/enroll',{"segment_id":segment["id"],"start_at":datetime.now(timezone.utc).isoformat()},employee="EMP-2")
    assert response.status_code==403
    assert post(client,"/sequences/process-due",{},role="SERVICE").status_code==403


def test_merge_never_reassigns_customer_login(client):
    seed()
    ledger.add_entity(Entity("LOGIN","CustomerAccount",{"linked_customer_id":"L2"}))
    body={"survivor_id":"L1","duplicate_id":"L2"}
    preview=post(client,"/duplicates/preview",body).json()
    assert "LOGIN" in preview["blocked_by"]
    assert post(client,"/duplicates/merge",{**body,"token":preview["token"]},role="ADMIN").status_code==409
    assert ledger.get_entity("LOGIN").attributes["linked_customer_id"]=="L2"


def test_sequence_inbound_communication_provider_response_and_future_wait(client):
    seed();seq=sequence(client,("email",))
    future=datetime.now(timezone.utc)+timedelta(days=1)
    en=enroll(client,seq,start_at=future.isoformat()).json()[0]
    advanced.run_due()
    e=ledger.get_entity(en["id"])
    assert e.attributes["output_id"] is None
    rev=e.attributes["revision"]
    assert post(client,f'/enrollments/{e.id}/status',{"revision":rev,"status":"paused"}).status_code==200
    e=ledger.get_entity(en["id"])
    assert e.attributes["remaining_seconds"]>86000
    assert post(client,f'/enrollments/{e.id}/status',{"revision":e.attributes["revision"],"status":"active"}).status_code==200
    advanced.run_due()
    assert ledger.get_entity(en["id"]).attributes["output_id"] is None
    ledger.add_entity(Entity("COMM","Communication",{"linked_entity_id":"L1","direction":"inbound","channel":"email","created_at":datetime.now(timezone.utc).isoformat()}))
    advanced.run_due()
    assert ledger.get_entity(en["id"]).attributes["status"]=="stopped"
    ledger.entities.pop("COMM")
    en=enroll(client,seq).json()[0]
    ledger.add_entity(Entity("ACTION",advanced.delivery.ACTION,{"recipient_id":"L1","status":"accepted"}))
    ledger.add_entity(Entity("EVENT",advanced.delivery.EVENT,{"action_id":"ACTION","status":"response","created_at":datetime.now(timezone.utc).isoformat()}))
    advanced.run_due()
    assert ledger.get_entity(en["id"]).attributes["reason"]=="Provider reply recorded"


def test_dispatch_checks_sequence_state_and_exit_without_scheduler_tick(client,monkeypatch):
    client.app.include_router(advanced.delivery.router)
    seed();seq=sequence(client,("email",));en=enroll(client,seq).json()[0]
    advanced.run_due(datetime.now(timezone.utc)+timedelta(seconds=1))
    e=ledger.get_entity(en["id"]);action=ledger.get_entity(e.attributes["output_id"])
    action.attributes.update(status="approved",scheduled_at=None)
    monkeypatch.setenv("NXTDEAL_MARKETING_APPROVER_EMPLOYEE_ID","EMP-1")
    monkeypatch.setattr(advanced.delivery,"channel_ready",lambda _:True)
    monkeypatch.setattr(advanced.delivery.marketing_delivery,"send",lambda _:pytest.fail("Must not dispatch"))
    e.attributes["status"]="paused"
    url=f'/marketing/operations/actions/{action.id}/dispatch'
    assert client.post(url,headers=headers("ADMIN")).status_code==409
    e.attributes["status"]="active"
    ledger.get_entity("L1").attributes["PipelineState"]="SOLD"
    assert client.post(url,headers=headers("ADMIN")).status_code==409
    assert action.attributes["attempt_count"]==0


def test_failed_schedule_write_has_no_orphan_task_and_retry_is_single(client,monkeypatch):
    seed();seq=sequence(client,("call",));en=enroll(client,seq).json()[0]
    save=advanced.save_graph
    monkeypatch.setattr(advanced,"save_graph",lambda _:(_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError): advanced.run_due(datetime.now(timezone.utc)+timedelta(seconds=1))
    assert ledger.get_entity(en["id"]).attributes["output_id"] is None
    assert len(advanced.all_of("LeadTask"))==1
    monkeypatch.setattr(advanced,"save_graph",save)
    advanced.run_due(datetime.now(timezone.utc)+timedelta(seconds=1))
    assert len(advanced.all_of("LeadTask"))==2
