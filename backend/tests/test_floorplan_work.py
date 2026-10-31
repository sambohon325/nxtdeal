import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers import floorplan_work as f
from core.entities import Entity
@pytest.fixture
def client(monkeypatch,tmp_path):
 f.store.ledger.reset();monkeypatch.setattr(f.store,'GRAPH_PATH',str(tmp_path/'graph.json'))
 monkeypatch.setattr(f,'_authenticate',lambda h:({'employee_id':h.split(':')[0],'role':h.split(':')[1]},None) if h else (None,True))
 f.store.ledger.add_entity(Entity('V1','Vehicle',{'VIN':'SYNTHETIC'}))
 app=FastAPI();app.include_router(f.router)
 with TestClient(app) as c:yield c
 f.store.ledger.reset()
def headers(who='A',role='FINANCE'):return {'Authorization':who+':'+role}
def create(c,amount='12000.00'):return c.post('/finance/floorplan-work',headers=headers(),json={'vehicle_id':'V1','lender':'Synthetic Lender','principal':amount,'currency':'USD','source_reference':'Synthetic statement 1'})
def test_floorplan_end_to_end_persistence_and_double_payment(client):
 a=create(client).json();url='/finance/floorplan-work'
 p=client.post(f'{url}/{a["id"]}/payoffs',headers=headers(),json={'revision':a['revision'],'amount':'12000','evidence':'Reviewed the current lender statement'}).json()
 body={'revision':p['revision'],'action':'approve','reference':'Approval 1','evidence':'Reviewed independently by second employee'}
 assert client.post(f'{url}/payoffs/{p["id"]}/decision',headers=headers(),json=body).status_code==403
 approved=client.post(f'{url}/payoffs/{p["id"]}/decision',headers=headers('B'),json=body).json()
 body.update(revision=approved['revision'],action='record_payment',reference='BANK-SYN-1')
 assert client.post(f'{url}/payoffs/{p["id"]}/decision',headers=headers('B'),json=body).status_code==200
 assert client.post(f'{url}/payoffs/{p["id"]}/decision',headers=headers('B'),json=body).status_code==409
 f.store.ledger.reset();f.store.ledger.load(f.store.GRAPH_PATH)
 a=client.get(url,headers=headers()).json()['accounts'][0];assert a['balance_cents']==0
 assert client.post(f'{url}/{a["id"]}/title',headers=headers(),json={'revision':a['revision'],'status':'received','evidence':'Original title received from lender'}).status_code==200
 assert len(client.get(url,headers=headers()).json()['accounts'][0]['history'])==5
@pytest.mark.parametrize('amount',['0','-1','NaN','Infinity','0.001','10000001'])
def test_invalid_principal(client,amount):assert create(client,amount).status_code==422
@pytest.mark.parametrize('role',['SALES','MARKETING','SERVICE','BDC'])
def test_role_denied(client,role):assert client.get('/finance/floorplan-work',headers=headers(role=role)).status_code==403
def test_order_conflict_and_rollback(client,monkeypatch):
 a=create(client).json();url='/finance/floorplan-work'
 assert create(client).status_code==409
 assert client.post(f'{url}/{a["id"]}/title',headers=headers(),json={'revision':a['revision'],'status':'released','evidence':'Invalid early release attempt'}).status_code==422
 assert client.post(f'{url}/{a["id"]}/payoffs',headers=headers(),json={'revision':99,'amount':'100','evidence':'Current lender statement reviewed'}).status_code==409
 assert client.post(f'{url}/{a["id"]}/payoffs',headers=headers(),json={'revision':a['revision'],'amount':'12001','evidence':'Current lender statement reviewed'}).status_code==422
 monkeypatch.setattr(f.store,'save_graph',lambda _:(_ for _ in ()).throw(OSError('disk failure')))
 with pytest.raises(OSError):client.post(f'{url}/{a["id"]}/payoffs',headers=headers(),json={'revision':a['revision'],'amount':'100','evidence':'Current lender statement reviewed'})
 assert f.store.all_of(f.PAYOFF)==[]
 assert f.store.ledger.get_entity(a['id']).attributes['revision']==1
