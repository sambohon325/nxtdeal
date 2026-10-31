import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers import readiness_mappings as m
from core import data_connections as d
from core.csv_mapping import mapped_csv
from core.entities import Entity
@pytest.fixture
def client(monkeypatch,tmp_path):
 m.store.ledger.reset();path=str(tmp_path/'graph.json');monkeypatch.setattr(m.store,'GRAPH_PATH',path);monkeypatch.setattr(d,'GRAPH_PATH',path)
 monkeypatch.setattr(m,'_authenticate',lambda h:({'employee_id':'A','role':h},None))
 m.store.ledger.add_entity(Entity('C1','Connection',{'name':'Synthetic source','department':'sales','connection_type':'csv'}))
 app=FastAPI();app.include_router(m.router)
 with TestClient(app) as c:yield c
 m.store.ledger.reset()
def test_mapping_ingestion_and_persistence(client):
 body={'revision':0,'columns':{'VehicleNumber':'VIN'}}
 assert client.put('/readiness/mappings/C1',headers={'Authorization':'ADMIN'},json=body).status_code==200
 assert client.put('/readiness/mappings/C1',headers={'Authorization':'ADMIN'},json=body).status_code==409
 result=d.ingest_csv('C1','synthetic.csv',b'VehicleNumber,Make\nSYN-MAPPING-1,Synthetic\n');assert result['records_created']==1
 m.store.ledger.reset();m.store.ledger.load(m.store.GRAPH_PATH)
 vehicles=m.store.all_of('Vehicle');assert vehicles[0].attributes['VIN']=='SYN-MAPPING-1'
 assert m.store.ledger.get_entity('C1').attributes['mapping_revision']==1
 assert len(m.store.ledger.get_entity('C1').attributes['mapping_history'])==1
@pytest.mark.parametrize('content',[b'Wrong\nX\n',b'VIN,VIN\nX,Y\n',b'VIN,Make\nX,A\nY\n',b'VIN\n\n',b'VIN,Make\nX,A\n,B\n'])
def test_bad_upload_does_not_partially_import(client,content):
 result=d.ingest_csv('C1','bad.csv',content);assert 'error' in result;assert m.store.all_of('Vehicle')==[]
def test_mapping_role_and_collision(client):
 body={'revision':0,'columns':{'A':'VIN','B':'VIN'}}
 assert client.put('/readiness/mappings/C1',headers={'Authorization':'ADMIN'},json=body).status_code==422
 assert client.get('/readiness/mappings',headers={'Authorization':'SALES'}).status_code==403
 with pytest.raises(ValueError):mapped_csv(b'A,VIN\nX,Y\n','sales',{'A':'VIN'})

def test_import_storage_failure_restores_graph_and_identity_indexes(client,monkeypatch):
 from core.dealeros import registry
 original=dict(registry.vehicle_vins)
 monkeypatch.setattr(d,'save_graph',lambda _:(_ for _ in ()).throw(OSError('synthetic disk failure')))
 result=d.ingest_csv('C1','synthetic.csv',b'VIN,Make\nSYN-ROLLBACK-MAPPING,Synthetic\n')
 assert 'error' in result
 assert m.store.all_of('Vehicle')==[]
 assert registry.vehicle_vins==original

def test_csv_connection_routes_do_not_collide_with_provider_connections(monkeypatch):
    import api.app as application
    import api.administration_boundary as boundary
    from api.routers import connections
    authenticate=lambda _: ({"employee_id":"SYN-TEST","role":"ADMIN"},None)
    monkeypatch.setattr(application,"_authenticate",authenticate)
    monkeypatch.setattr(boundary,"_authenticate",authenticate)
    monkeypatch.setattr(boundary,"is_system_admin",lambda payload: True)
    monkeypatch.setattr(connections,"_authenticate",authenticate)
    monkeypatch.setattr(connections,"get_connections_api",lambda role:{"provider_marker":True})
    monkeypatch.setattr(application,"list_connections_api",lambda role,department:{"csv_marker":True})
    with TestClient(application.app) as c:
     assert c.get('/connections').json()=={"provider_marker":True}
     assert c.get('/readiness/connections').json()=={"csv_marker":True}
