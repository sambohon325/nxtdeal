from datetime import timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers import campaign_workflow as w
from core.entities import Entity
from core.relationships import Relationship
from staff_auth_fixture import staff_token

def headers(role="MARKETING"):
    return {"Authorization":"Bearer "+staff_token("EMP-QA",role)}

@pytest.fixture
def client():
    w.store.ledger.reset()
    for eid,kind,attrs in [
        ("EMP-QA","Employee",{"Name":"QA"}), ("C1","Customer",{"Name":"QA Customer","CustomerID":"C1"}), ("C2","Customer",{"Name":"Other"}),
        ("L1","Lead",{"ConvertedCustomerID":"C1"}), ("CAMP1","Campaign",{"name":"QA"}),
        ("BRIEF1","MarketingCampaignBrief",{"name":"QA","department":"Service","campaign_id":"CAMP1","routing_owner_id":"EMP-QA","response_minutes":30,"next_step":"Confirm a service time"})]:
        w.store.ledger.add_entity(Entity(eid,kind,attrs))
    w.store.ledger.add_relationship(Relationship("L1","C1","BECAME"))
    app=FastAPI(); app.include_router(w.router)
    with TestClient(app) as c: yield c
    w.store.ledger.reset()

def signal(client,**patch):
    return client.post('/marketing/workflow/signals',headers=headers(),json={"brief_id":"BRIEF1","person_id":"C1","kind":"reply","event_key":"provider-123","evidence":"Customer requested service appointment",**patch})

def case(client):
    signal(client)
    return client.get('/marketing/workflow',headers=headers()).json()['cases'][0]

def booking(c,**patch):
    start=w.store.now()+timedelta(days=3)
    return {"revision":c['revision'],"scheduled_start":start.isoformat(),"scheduled_end":(start+timedelta(minutes=30)).isoformat(),"assigned_to":"EMP-QA","appointment_type":"service",**patch}

def link(client,c,kind,rid):
    return client.post(f'/marketing/workflow/{c["id"]}/link/{kind}',headers=headers(),json={"revision":c['revision'],"record_id":rid,"evidence":"Reviewed canonical appointment and customer record"})

@pytest.mark.parametrize('kind',['open','click'])
def test_passive_signals_never_create_work(client,kind):
    assert signal(client,kind=kind).status_code==200
    assert w.store.all_of(w.CASE)==[]
    assert w.store.all_of('FieldNote')==[]

def test_response_deduplication_conversion_and_reload(client):
    first=signal(client).json()
    assert signal(client).json()['replayed']
    assert signal(client,kind='call').status_code==409
    assert signal(client,person_id='L1',event_key='provider-456').status_code==200
    assert len(w.store.all_of(w.CASE))==1
    w.store.ledger.reset();w.store.ledger.load(w.store.GRAPH_PATH)
    c=client.get('/marketing/workflow',headers=headers()).json()['cases'][0]
    assert c['owner_id']=='EMP-QA' and c['next_step']=='Confirm a service time'
    assert w.store.crm.timestamp(c['due_at'])>w.store.now()
    assert len(w.store.all_of('Customer'))==2

def test_missing_owner_requires_fix_before_work(client):
    w.store.ledger.get_entity('BRIEF1').attributes['routing_owner_id']=None
    assert signal(client).status_code==422
    assert not w.store.all_of(w.SIGNAL)

def test_department_access(client):
    c=case(client)
    assert client.get('/marketing/workflow',headers=headers('SALES')).json()['cases']==[]
    assert client.get(f'/marketing/workflow/{c["id"]}/links',headers=headers('SALES')).status_code==403
    assert client.get('/marketing/workflow').status_code==401

def test_booking_duplicate_and_collision_guards(client):
    c=case(client); data=booking(c)
    booked=client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=data)
    assert booked.status_code==200,booked.text
    b=booked.json(); assert b['stage']=='appointment_booked'
    assert client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=data).status_code==409
    assert client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=booking(b)).status_code==409
    assert len(w.store.all_of('Appointment'))==1
    appt=w.store.ledger.get_entity(b['appointment_id'])
    assert appt.attributes['customer_id']=='C1' and appt.attributes['campaign_id']=='CAMP1'

def test_failed_booking_rolls_back_everything(client,monkeypatch):
    c=case(client)
    def fail(*args):raise OSError('disk unavailable')
    monkeypatch.setattr(w.store,'save_graph',fail)
    with pytest.raises(OSError):client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=booking(c))
    assert not w.store.all_of('Appointment')
    assert not w.store.ledger.get_entity(c['id']).attributes.get('appointment_id')

def test_service_outcome_reads_actual_status_value_and_reversal(client):
    c=case(client)
    c=client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=booking(c)).json()
    w.store.ledger.add_entity(Entity('RO1','ServiceRecord',{'CustomerID':'C1','Status':'Open','Cost':'250.50'}))
    linked=link(client,c,'outcome','RO1');assert linked.status_code==200,linked.text
    assert linked.json()['recorded_value'] is None
    w.store.ledger.get_entity('RO1').attributes['Status']='Completed'
    c=client.get('/marketing/workflow',headers=headers()).json()['cases'][0]
    assert c['stage']=='service_completed' and c['recorded_value']==250.5
    w.store.ledger.get_entity('RO1').attributes['Status']='Open'
    assert client.get('/marketing/workflow',headers=headers()).json()['cases'][0]['recorded_value'] is None

def test_wrong_customer_outcome_rejected(client):
    c=case(client)
    w.store.ledger.add_entity(Entity('D1','Deal',{'customer_id':'C2','status':'funded','contract':{'sale_price':20000}}))
    assert link(client,c,'outcome','D1').status_code==422

def test_sales_funded_outcome_and_missing_value(client):
    w.store.ledger.get_entity('BRIEF1').attributes['department']='Sales'
    c=case(client); c=client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=booking(c,appointment_type='showroom_visit')).json()
    w.store.ledger.add_entity(Entity('D1','Deal',{'customer_id':'C1','status':'funded','contract':{'sale_price':20000},'currency':'USD'}))
    c=link(client,c,'outcome','D1').json()
    assert c['stage']=='sale_completed' and c['recorded_value']==20000 and c['currency']=='USD'
    w.store.ledger.get_entity('D1').attributes['contract']={}
    assert client.get('/marketing/workflow',headers=headers()).json()['cases'][0]['recorded_value'] is None

def test_no_show_requires_recovery(client):
    c=case(client);c=client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=booking(c)).json()
    w.store.ledger.get_entity(c['appointment_id']).attributes['status']='no_show'
    assert client.get('/marketing/workflow',headers=headers()).json()['cases'][0]['stage']=='recover_appointment'

def test_stale_work_update_rejected(client):
    c=case(client)
    payload={'revision':c['revision'],'owner_id':'EMP-QA','due_at':c['due_at'],'next_step':'Call to confirm availability','evidence':'Manager reviewed next customer step','closed':False}
    assert client.put(f'/marketing/workflow/{c["id"]}',headers=headers(),json=payload).status_code==200
    assert client.put(f'/marketing/workflow/{c["id"]}',headers=headers(),json=payload).status_code==409

def test_provider_response_sync_is_idempotent_and_reports_routing_gaps(client):
    w.store.ledger.add_entity(Entity('MSG1',w.store.delivery.ACTION,{'sequence_id':'CAMP1','recipient_id':'C1'}))
    w.store.ledger.add_entity(Entity('EV1',w.store.delivery.EVENT,{'action_id':'MSG1','status':'response'}))
    assert client.post('/marketing/workflow/sync',headers=headers()).json()['routed']==1
    assert client.post('/marketing/workflow/sync',headers=headers()).json()['routed']==0
    assert len(w.store.all_of(w.CASE))==1
    w.store.ledger.add_entity(Entity('EV2',w.store.delivery.EVENT,{'action_id':'MSG1','status':'response'}))
    w.store.ledger.get_entity('BRIEF1').attributes['routing_owner_id']=None
    result=client.post('/marketing/workflow/sync',headers=headers()).json()
    assert result['pending'] and len(w.store.all_of(w.CASE))==1

def test_signal_stops_pending_nurture_without_sending(client):
    w.store.ledger.add_entity(Entity('MSG1',w.store.delivery.ACTION,{'status':'approved','revision':1}))
    w.store.ledger.add_entity(Entity('ENR1',w.store.ENROLLMENT,{'recipient_id':'L1','status':'active','output_id':'MSG1','revision':1}))
    assert signal(client).status_code==200
    assert w.store.ledger.get_entity('MSG1').attributes['status']=='cancelled'
    assert w.store.ledger.get_entity('ENR1').attributes['status']=='stopped'

def test_appointment_lifecycle_updates_same_record_and_rejects_stale(client):
    c=case(client);c=client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=booking(c)).json()
    url=f'/marketing/workflow/{c["id"]}/appointment-status'
    p={'revision':c['revision'],'expected_status':'scheduled','status':'completed'}
    assert client.post(url,headers=headers(),json=p).status_code==409
    for old,new in [('scheduled','confirmed'),('confirmed','arrived'),('arrived','completed')]:
        p.update(expected_status=old,status=new)
        result=client.post(url,headers=headers(),json=p)
        assert result.status_code==200,result.text
    assert result.json()['stage']=='awaiting_outcome'
    assert client.post(url,headers=headers(),json=p).status_code==409
    assert len(w.store.all_of('Appointment'))==1

def test_wrong_department_private_history_and_old_appointment_link(client):
    c=case(client)
    w.store.ledger.add_entity(Entity('APOLD','Appointment',{'customer_id':'C1','department':'Service','scheduled_start':'2020-01-01T12:00:00+00:00','status':'completed'}))
    assert link(client,c,'appointment','APOLD').status_code==422

def test_unique_outcome_credit_and_audited_unlink(client):
    c=case(client);c=client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=booking(c)).json()
    w.store.ledger.add_entity(Entity('RO1','ServiceRecord',{'CustomerID':'C1','Status':'Completed','Cost':'250.50'}))
    c=link(client,c,'outcome','RO1').json()
    other=w.new(w.CASE,{**w.store.ledger.get_entity(c['id']).attributes,'outcome_id':None},'EMP-QA')
    assert link(client,w.projection(other),'outcome','RO1').status_code==409
    result=client.post(f'/marketing/workflow/{c["id"]}/unlink/outcome',headers=headers(),json={'revision':c['revision'],'record_id':'RO1','evidence':'Correcting an incorrectly attributed record'})
    assert result.status_code==200
    assert result.json()['recorded_value'] is None
    assert result.json()['history'][-1]['event']=='outcome_unlinked'

def test_ambiguous_service_customer_key_is_not_attributed(client):
    c=case(client)
    w.store.ledger.get_entity('C2').attributes['CustomerID']='C1'
    w.store.ledger.add_entity(Entity('RO1','ServiceRecord',{'CustomerID':'C1','Status':'Completed','Cost':'250'}))
    assert link(client,c,'outcome','RO1').status_code==422

def test_booking_employee_conflict(client):
    c=case(client);b=booking(c)
    w.store.ledger.add_entity(Entity('AP1','Appointment',{'customer_id':'C2','department':'Sales','status':'confirmed','assigned_to':'EMP-QA','scheduled_start':b['scheduled_start'],'scheduled_end':b['scheduled_end']}))
    assert client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=b).status_code==409

def test_failed_response_does_not_leave_partial_work(client,monkeypatch):
    def fail(*args):raise OSError('disk unavailable')
    monkeypatch.setattr(w.store,'save_graph',fail)
    with pytest.raises(OSError):signal(client)
    assert not w.store.all_of(w.CASE) and not w.store.all_of(w.SIGNAL) and not w.store.all_of('FieldNote')

def test_changed_outcome_customer_or_date_removes_credit(client):
    c=case(client);c=client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=booking(c)).json()
    w.store.ledger.add_entity(Entity('RO1','ServiceRecord',{'CustomerID':'C1','Status':'Completed','Cost':'250'}))
    c=link(client,c,'outcome','RO1').json();assert c['recorded_value']==250
    w.store.ledger.get_entity('RO1').attributes['ServiceDate']='2020-01-01'
    c=client.get('/marketing/workflow',headers=headers()).json()['cases'][0]
    assert c['stage']=='attribution_review' and c['recorded_value'] is None
    w.store.ledger.get_entity('RO1').attributes.pop('ServiceDate')
    w.store.ledger.get_entity('RO1').attributes['CustomerID']='C2'
    c=client.get('/marketing/workflow',headers=headers()).json()['cases'][0]
    assert c['stage']=='attribution_review' and c['recorded_value'] is None

def test_closing_work_preserves_verified_outcome_value(client):
    c=case(client);c=client.post(f'/marketing/workflow/{c["id"]}/book',headers=headers(),json=booking(c)).json()
    w.store.ledger.add_entity(Entity('RO1','ServiceRecord',{'CustomerID':'C1','Status':'Completed','Cost':'250'}))
    c=link(client,c,'outcome','RO1').json()
    p={'revision':c['revision'],'owner_id':'EMP-QA','due_at':c['due_at'],'next_step':'Completed follow-up','evidence':'Customer visit finished and follow-up complete','closed':True}
    result=client.put(f'/marketing/workflow/{c["id"]}',headers=headers(),json=p).json()
    assert result['closed'] and result['recorded_value']==250
