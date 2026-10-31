"""Exercise the real HTTP route boundary where same-name imports previously collided."""
import ast
import importlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from core.dealeros import ledger
from core.entities import Entity
routes = importlib.import_module('api.app')

@pytest.fixture
def client(monkeypatch):
    ledger.reset()
    monkeypatch.setattr(routes, '_authenticate', lambda _: ({'role':'ADMIN','employee_id':'QA-ACTOR'},None))
    c=TestClient(routes.app)
    yield c
    c.close()
    ledger.reset()

@pytest.mark.parametrize('path,binding',[
    ('/assets/pending','list_asset_pending_approvals_api'),
    ('/document-workflows/pending-approvals','list_pending_approvals_api'),
    ('/opportunities/sales-employees','list_opportunity_sales_employees_api'),
    ('/sales/employees','list_sales_employees_api'),
    ('/alerts/feed?alert_type=recall_open&status=new&target_entity_type=Customer','get_trigger_alert_feed_api'),
    ('/operations-alerts/feed','get_alert_feed_api'),
])
def test_read_routes_dispatch_to_their_own_service(client,monkeypatch,path,binding):
    calls=[]
    original=getattr(routes,binding)
    def record(*args,**kwargs):
        import inspect
        inspect.signature(original).bind(*args,**kwargs)
        calls.append((args,kwargs))
        return {'source':binding}
    monkeypatch.setattr(routes,binding,record)
    response=client.get(path)
    assert response.status_code==200
    assert response.json()=={'source':binding}
    assert len(calls)==1


def seed_deal():
    for id,typ,attrs in [('QA-CUSTOMER','Customer',{'Name':'Synthetic customer'}),('QA-VEHICLE','Vehicle',{}),('QA-DEAL','Deal',{'status':'contract','customer_id':'QA-CUSTOMER','vehicle_id':'QA-VEHICLE'})]:
        ledger.add_entity(Entity(id=id,entity_type=typ,attributes=attrs))


def test_social_draft_accepts_null_schedule_from_actual_composer(client, monkeypatch):
    from api.routers import social
    monkeypatch.setattr(social, '_authenticate', lambda _: ({'role':'ADMIN','employee_id':'QA-ACTOR'},None))
    response = client.post('/social/posts', json={'platform':'facebook','content':'Synthetic draft','linked_vehicle_ids':[], 'scheduled_time':None,'target_date':'2026-10-21'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'draft'


def test_operations_delivery_creates_persistent_calendar_appointment(client):
    seed_deal()
    response=client.post('/operations-scheduling/delivery/QA-DEAL/schedule',json={'scheduled_start':'2099-10-23T15:00:00Z','assigned_to':'QA-ACTOR','notes':'Synthetic delivery'})
    assert response.status_code==200
    data=response.json();assert 'error' not in data
    assert ledger.get_entity(data['id']).entity_type=='Appointment'
    board=client.get('/operations-scheduling/delivery-risk').json()
    assert board['on_track']['count']==1
    assert board['no_delivery_scheduled']['count']==0


def test_fulfillment_uses_its_own_request_model_and_syncs_calendar(client):
    seed_deal()
    response=client.post('/delivery',json={'deal_id':'QA-DEAL','mode':'home_delivery','window_start':'2099-10-23T15:00:00Z','address':'Synthetic test address'})
    assert response.status_code==200
    data=response.json();assert 'error' not in data
    assert data['delivery']['mode']=='home_delivery'
    assert ledger.get_entity(data['delivery']['id']) is not None
    assert data['delivery']['ops_appointment_id']


def test_event_task_creates_event_task_not_sales_task(client):
    from core.dealership_events import create_event
    event=create_event('QA-ACTOR','Synthetic event','community','2099-10-23T15:00:00Z')
    response=client.post('/events/'+event.id+'/tasks',json={'title':'Prepare event','notes':'Synthetic task'})
    assert response.status_code==200
    data=response.json();assert 'error' not in data
    saved=ledger.get_entity(data['id'])
    assert saved.entity_type=='EventTask'
    assert saved.attributes['event_id']==event.id


def test_no_duplicate_module_bindings_can_silently_replace_handlers():
    tree=ast.parse(Path(routes.__file__).read_text(encoding='utf8'))
    bindings={}
    for node in tree.body:
        names=[]
        if isinstance(node,ast.ImportFrom):names=[a.asname or a.name for a in node.names]
        elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):names=[node.name]
        for name in names:
            assert name not in bindings, f'{name} redefined at {node.lineno}; first binding {bindings.get(name)}'
            bindings[name]=node.lineno
