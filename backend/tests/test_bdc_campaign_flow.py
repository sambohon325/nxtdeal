import hashlib, hmac, json, time
from datetime import timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers import bdc, sales_crm_advanced as seq, marketing_operations as delivery
from core.dealeros import ledger
from core.entities import Entity
from staff_auth_fixture import staff_token

def headers(role="MARKETING", actor="QA"):
    return {"Authorization":"Bearer "+staff_token(actor,role)}

@pytest.fixture
def client(monkeypatch):
    ledger.reset()
    ledger.add_entity(Entity("SYSCFG-00001", "SystemConfig", {"dealership_name":"Synthetic Dealer", "address_line1":"100 Test Street", "city":"Test City", "state":"TX", "zip_code":"75001"}))
    monkeypatch.setenv("NXTDEAL_MARKETING_PUBLIC_URL", "https://api.example.test")
    monkeypatch.delenv("DEALEROS_DEMO",raising=False)
    monkeypatch.setenv("NXTDEAL_MARKETING_APPROVER_EMPLOYEE_ID","QA")
    monkeypatch.setenv("NXTDEAL_CHANNEL_CALLBACK_SECRET","test-secret")
    monkeypatch.setattr(delivery,"channel_ready",lambda channel:True)
    monkeypatch.setattr(delivery.marketing_delivery,"configured",lambda channel:False)
    monkeypatch.setattr(delivery,"send_gateway",lambda action:"synthetic-provider-reference")
    app=FastAPI();app.include_router(bdc.router);app.include_router(seq.router);app.include_router(delivery.router)
    ledger.add_entity(Entity("L1","Lead",{"Name":"Synthetic eligible","Email":"eligible@example.test","marketing_email_consent":True}))
    ledger.add_entity(Entity("L2","Lead",{"Name":"Synthetic excluded","Email":"excluded@example.test"}))
    ledger.add_entity(Entity("LIST1","MarketingList",{"name":"QA audience","member_ids":["L1","L2","L1"]}))
    ledger.add_entity(Entity("EMAIL1","EmailTemplate",{"name":"QA branded email","channel":"email","subject":"Synthetic test","created_by":"QA","blocks":[{"block_key":"html","fields":{"email_source":"imported_html","html":"<h1>Matching design</h1><p>Synthetic email</p>"}}]}))
    with TestClient(app) as c:yield c
    ledger.reset()

def create(c):
    response=c.post("/bdc/campaigns",headers=headers(),json={"name":"QA campaign","audience_id":"LIST1","steps":[{"template_id":"EMAIL1","delay_minutes":0},{"channel":"call","body":"Follow up","delay_minutes":0}]})
    assert response.status_code==200,response.text
    return response.json()

def schedule(c,campaign):
    review=c.get(f'/bdc/campaigns/{campaign["id"]}/review',headers=headers()).json()
    body={"revision":campaign["revision"],"review_token":review["review_token"],"start_at":(seq.now()-timedelta(seconds=1)).isoformat()}
    result=c.post(f'/bdc/campaigns/{campaign["id"]}/launch',headers=headers(),json=body)
    assert result.status_code==200,result.text
    return body,result.json()

def test_save_reload_review_schedule_approve_deliver_followup(client):
    campaign=create(client);ledger.reset();ledger.load(seq.GRAPH_PATH)
    assert client.get('/bdc/campaigns',headers=headers()).json()[0]['id']==campaign['id']
    review=client.get(f'/bdc/campaigns/{campaign["id"]}/review',headers=headers()).json()
    assert review['eligible_ids']==['L1'] and len(review['excluded'])==1
    body,result=schedule(client,campaign)
    assert result['enrolled']==1
    assert client.post(f'/bdc/campaigns/{campaign["id"]}/launch',headers=headers(),json=body).json()['replayed']
    assert len(seq.all_of(seq.ENROLLMENT))==1
    seq.run_due();seq.run_due()
    assert len(seq.all_of(delivery.ACTION))==1
    action=seq.all_of(delivery.ACTION)[0];assert 'Matching design' in action.attributes['html_body']
    url=f'/marketing/operations/actions/{action.id}'
    assert client.post(url+'/dispatch',headers=headers()).status_code==409
    assert client.post(url+'/decision',headers=headers(actor='another'),json={'revision':1,'decision':'approve'}).status_code==403
    assert client.post(url+'/decision',headers=headers(),json={'revision':1,'decision':'approve'}).status_code==200
    assert client.post(url+'/dispatch',headers=headers()).json()['status']=='accepted'
    assert client.post(url+'/dispatch',headers=headers()).status_code==409
    seq.run_due();assert not seq.all_of('LeadTask')
    stamp=str(int(time.time()));payload=json.dumps({'action_id':action.id,'provider_reference':'synthetic-provider-reference','event_id':'qa-delivered','status':'delivered'}).encode()
    sig=hmac.new(b'test-secret',stamp.encode()+b'.'+payload,hashlib.sha256).hexdigest()
    event=client.post('/marketing/operations/provider-events',content=payload,headers={'X-Nxtdeal-Timestamp':stamp,'X-Nxtdeal-Signature':sig})
    assert event.status_code==200,event.text
    seq.run_due();seq.run_due();seq.run_due();assert len(seq.all_of('LeadTask'))==1
    seq.all_of('LeadTask')[0].attributes['completed']=True;seq.run_due()
    assert seq.all_of(seq.ENROLLMENT)[0].attributes['status']=='completed'
    assert client.get('/bdc/results',headers=headers()).json()['messages']['delivered']==1

@pytest.mark.parametrize('change',['consent','membership','revision'])
def test_review_invalidated(client,change):
    campaign=create(client);review=client.get(f'/bdc/campaigns/{campaign["id"]}/review',headers=headers()).json()
    if change=='consent':ledger.get_entity('L1').attributes['DoNotContact']=True
    if change=='membership':ledger.get_entity('LIST1').attributes['member_ids']=[]
    if change=='revision':ledger.get_entity(campaign['id']).attributes['revision']+=1
    response=client.post(f'/bdc/campaigns/{campaign["id"]}/launch',headers=headers(),json={'revision':1,'review_token':review['review_token'],'start_at':seq.now().isoformat()})
    assert response.status_code==409 and not seq.all_of(seq.ENROLLMENT)

@pytest.mark.parametrize('exit_kind',['reply','appointment','optout','sold'])
def test_exit_cancels_drafts_blocks_dispatch(client,exit_kind):
    campaign=create(client);schedule(client,campaign);seq.run_due();action=seq.all_of(delivery.ACTION)[0]
    assert client.post(f'/marketing/operations/actions/{action.id}/decision',headers=headers(),json={'revision':1,'decision':'approve'}).status_code==200
    if exit_kind=='reply':ledger.add_entity(Entity('REPLY','Communication',{'linked_entity_id':'L1','direction':'inbound','channel':'email','created_at':seq.now().isoformat()}))
    if exit_kind=='appointment':ledger.add_entity(Entity('APPT','Appointment',{'lead_id':'L1','status':'scheduled','created_at':seq.now().isoformat()}))
    if exit_kind=='optout':ledger.get_entity('L1').attributes['DoNotContact']=True
    if exit_kind=='sold':ledger.get_entity('L1').attributes['PipelineState']='SOLD'
    assert client.post(f'/marketing/operations/actions/{action.id}/dispatch',headers=headers()).status_code==409
    seq.run_due();assert seq.all_of(seq.ENROLLMENT)[0].attributes['status']=='stopped'
    assert action.attributes['status']=='cancelled'

def test_access_and_disk_failure(client,monkeypatch):
    assert client.get('/bdc/campaigns').status_code==401
    assert client.get('/bdc/campaigns',headers=headers(role='SERVICE')).status_code==403
    ledger.get_entity('EMAIL1').attributes['created_by']='OTHER'
    request={'name':'Private email','audience_id':'LIST1','steps':[{'template_id':'EMAIL1'}]}
    assert client.post('/bdc/campaigns',headers=headers(role='SALES'),json=request).status_code==403
    def fail(_):raise OSError('full')
    monkeypatch.setattr(seq,'save_graph',fail)
    with pytest.raises(OSError):create(client)
    assert not seq.all_of(seq.SEQUENCE)

def test_launch_disk_failure_rollback(client,monkeypatch):
    campaign=create(client)
    def fail(_):raise OSError('full')
    monkeypatch.setattr(seq,'save_graph',fail)
    with pytest.raises(OSError):schedule(client,campaign)
    assert not seq.all_of(seq.ENROLLMENT)
    assert ledger.get_entity(campaign['id']).attributes['bdc_status']=='draft'
    ledger.reset();ledger.load(seq.GRAPH_PATH);assert not seq.all_of(seq.ENROLLMENT)

def test_pause_and_legacy_cannot_bypass_review(client):
    campaign=create(client)
    assert client.post(f'/sales/crm/sequences/{campaign["id"]}/enroll',headers=headers(),json={'recipient_ids':['L1'],'start_at':seq.now().isoformat()}).status_code==409
    schedule(client,campaign);seq.run_due();e=seq.all_of(seq.ENROLLMENT)[0]
    assert client.post(f'/sales/crm/enrollments/{e.id}/status',headers=headers(),json={'revision':e.attributes['revision'],'status':'paused'}).status_code==200
    assert seq.all_of(delivery.ACTION)[0].attributes['status']=='cancelled'

def test_html_smtp_multipart(monkeypatch):
    from core import marketing_delivery
    captured=[]
    class SMTP:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def login(self,*a):pass
        def send_message(self,message):captured.append(message);return {}
    monkeypatch.setenv('NXTDEAL_PRIVATEEMAIL_USERNAME','test@example.test');monkeypatch.setenv('NXTDEAL_PRIVATEEMAIL_PASSWORD','synthetic')
    monkeypatch.setattr(marketing_delivery.smtplib,'SMTP_SSL',SMTP)
    marketing_delivery.send({'id':'QA','channel':'email','to':'recipient@example.test','subject':'Test','body':'Plain','html_body':'<h1>Branded</h1>'})
    assert captured[0].is_multipart()
    assert captured[0].get_body(preferencelist=('html',)).get_content().strip()=='<h1>Branded</h1>'


def test_incomplete_draft_saves_but_cannot_review(client):
    data={"name":"Draft", "audience_id":"LIST1", "start_local":"2026-10-25T09:30", "steps":[{"channel":"email"}]}
    saved=client.post('/bdc/campaigns',headers=headers(role='BDC'),json=data)
    assert saved.status_code==200,saved.text
    campaign=saved.json()
    assert campaign['bdc_config']['start_local']=='2026-10-25T09:30'
    assert client.get(f"/bdc/campaigns/{campaign['id']}/review",headers=headers(role='BDC')).status_code==422
    assert not seq.all_of(seq.ENROLLMENT)


def single_email(c):
    return c.post('/bdc/campaigns',headers=headers(),json={"name":"Single authorized email","audience_id":"LIST1","steps":[{"template_id":"EMAIL1"}]}).json()


def test_one_message_permission_is_scoped_and_persisted(client):
    c=single_email(client)
    url=f'/bdc/campaigns/{c["id"]}/permission'
    body={"recipient_id":"L2","revision":c["revision"],"evidence":"Recipient requested this one specific email in person."}
    assert client.post(url,headers=headers(),json=body).status_code==200
    ledger.reset();ledger.load(seq.GRAPH_PATH)
    assert ledger.get_entity('L2').attributes.get('marketing_email_consent') is not True
    with pytest.raises(Exception):delivery.check_recipient({"channel":"email","recipient_id":"L2"})
    with pytest.raises(Exception):delivery.check_recipient({"channel":"email","recipient_id":"L2","sequence_id":c['id'],"sequence_revision":99})
    assert client.get(f'/bdc/campaigns/{c["id"]}/review',headers=headers()).json()['eligible_ids']==['L1','L2']
    schedule(client,c);seq.run_due()
    a=next(a for a in seq.all_of(delivery.ACTION) if a.attributes['recipient_id']=='L2')
    assert delivery.check_recipient(a.attributes)=='excluded@example.test'
    assert client.post(url,headers=headers(),json=body).status_code==409
    ledger.get_entity('L2').attributes['unsubscribed']=True
    with pytest.raises(Exception):delivery.check_recipient(a.attributes)


@pytest.mark.parametrize('change,code',[('optout',409),('revision',409),('audience',422),('role',403),('multiple_steps',422)])
def test_permission_rejects_invalid_scope(client,change,code):
    c=create(client) if change=='multiple_steps' else single_email(client)
    body={"recipient_id":"L2","revision":c['revision'],"evidence":"Recipient requested this specific message by email."}
    if change=='optout':ledger.get_entity('L2').attributes['DoNotContact']=True
    if change=='revision':body['revision']=99
    if change=='audience':ledger.get_entity('LIST1').attributes['member_ids']=[]
    result=client.post(f'/bdc/campaigns/{c["id"]}/permission',headers=headers(role='SERVICE' if change=='role' else 'MARKETING'),json=body)
    assert result.status_code==code,result.text
    assert not ledger.get_entity('L2').attributes.get('bdc_email_permissions')


def test_verified_receipt_completes_smtp_campaign_without_resend(client):
    c=single_email(client);schedule(client,c);seq.run_due();a=seq.all_of(delivery.ACTION)[0]
    url=f'/marketing/operations/actions/{a.id}'
    client.post(url+'/decision',headers=headers(),json={"revision":1,"decision":"approve"})
    assert client.post(url+'/dispatch',headers=headers()).json()['status']=='accepted'
    body={"provider_reference":"wrong-ref","status":"delivered","evidence":"Recipient inbox verified for this exact message."}
    assert client.post(url+'/reconcile',headers=headers(),json=body).status_code==409
    body['provider_reference']='synthetic-provider-reference'
    assert client.post(url+'/reconcile',headers=headers(actor='other'),json=body).status_code==403
    result=client.post(url+'/reconcile',headers=headers(),json=body)
    assert result.json()['status_source']=='human_provider_reconciliation'
    assert client.post(url+'/dispatch',headers=headers()).status_code==409
    seq.run_due();assert seq.all_of(seq.ENROLLMENT)[0].attributes['status']=='completed'


def test_inventory_snapshot_blocks_sold_vehicle_before_sending(client):
    ledger.add_entity(Entity("V1", "Vehicle", {"Year":2024,"Make":"Ford","Model":"F-150","Price":32000}))
    data={"name":"Suggested trucks", "audience_id":"LIST1", "steps":[{"channel":"email","subject":"Truck options", "body":"Take a look", "inventory_ids":["V1"]}]}
    response=client.post("/bdc/campaigns",headers=headers(),json=data)
    assert response.status_code==200,response.text
    campaign=response.json()
    assert "F-150" in campaign["steps"][0]["html_body"]
    assert campaign["bdc_config"]["steps"][0]["inventory_ids"]==["V1"]
    schedule(client,campaign);seq.run_due()
    action=seq.all_of(delivery.ACTION)[0]
    url=f"/marketing/operations/actions/{action.id}"
    assert client.post(url+"/decision",headers=headers(),json={"revision":1,"decision":"approve"}).status_code==200
    ledger.get_entity("V1").attributes["DateSold"]="2026-10-21"
    assert client.post(url+"/dispatch",headers=headers()).status_code==409
    assert not client.get("/bdc/inventory-options",headers=headers()).json()
    assert client.post("/bdc/campaigns",headers=headers(),json=data).status_code==409
