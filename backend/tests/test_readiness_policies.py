import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers import readiness_policies as p
from core import prediction
@pytest.fixture
def client(monkeypatch,tmp_path):
 p.store.ledger.reset();monkeypatch.setattr(p.store,'GRAPH_PATH',str(tmp_path/'graph.json'))
 monkeypatch.setattr(p,'_authenticate',lambda h:({'employee_id':'A','role':h},None))
 monkeypatch.setattr(prediction,'predict',lambda d,h:{'confidence_pct':95,'basis':'ledger'})
 app=FastAPI();app.include_router(p.router)
 with TestClient(app) as c:yield c
 p.store.ledger.reset()
def change(c,rev,action,threshold=90,role='ADMIN'):return c.post('/readiness/policies/sales',headers={'Authorization':role},json={'revision':rev,'action':action,'threshold':threshold,'evidence':'Synthetic review of source coverage'})
def test_threshold_activate_suspend_and_reload(client,monkeypatch):
 r=change(client,0,'set_threshold',92);assert r.status_code==200;assert r.json()['threshold']==92
 r=change(client,1,'activate');assert r.json()['active'] is True
 p.store.ledger.reset();p.store.ledger.load(p.store.GRAPH_PATH);assert prediction.department_readiness('sales')['active'] is True
 monkeypatch.setattr(prediction,'predict',lambda d,h:{'confidence_pct':70,'basis':'blended'})
 assert prediction.department_readiness('sales')['active'] is False
 assert change(client,2,'activate').status_code==422
 assert change(client,2,'pause').json()['enabled'] is False
 assert change(client,2,'activate').status_code==409
 assert len(client.get('/readiness/policies',headers={'Authorization':'ADMIN'}).json()['departments'][0]['history'])==3
def test_policy_permissions_and_validation(client,monkeypatch):
 assert change(client,0,'set_threshold',0).status_code==422
 assert change(client,0,'set_threshold',101).status_code==422
 assert change(client,0,'activate',role='SALES').status_code==403
 monkeypatch.setattr(prediction,'predict',lambda d,h:{'confidence_pct':95,'basis':'industry_estimate'})
 assert change(client,0,'activate').status_code==422
 assert p.store.ledger.get_entity('READINESS-sales') is None
