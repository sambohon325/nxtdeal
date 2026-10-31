import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers import commission_work as c
from core.entities import Entity
@pytest.fixture
def client(monkeypatch,tmp_path):
 c.store.ledger.reset();monkeypatch.setattr(c.store,'GRAPH_PATH',str(tmp_path/'graph.json'))
 monkeypatch.setattr(c,'_authenticate',lambda h:({'employee_id':h.split(':')[0],'role':h.split(':')[1]},None) if h else (None,True))
 for id,kind,a in [('D1','Deal',{'status':'funded'}),('D2','Deal',{'status':'draft'}),('E1','Employee',{'Name':'Synthetic Employee'})]:c.store.ledger.add_entity(Entity(id,kind,a))
 app=FastAPI();app.include_router(c.router)
 with TestClient(app) as t:yield t
 c.store.ledger.reset()
def headers(who='A',role='FINANCE'):return {'Authorization':who+':'+role}
def plan(t):return t.post('/finance/commission-work/plans',headers=headers(),json={'name':'Synthetic plan','percent':'12.50','flat_amount':'50','currency':'USD','policy_reference':'Approved synthetic policy'}).json()
def claim(t,p,deal='D1'):return t.post('/finance/commission-work',headers=headers(),json={'plan_id':p['id'],'deal_id':deal,'employee_id':'E1','approved_basis':'1000.04','basis_evidence':'Documented approved commission basis'})
def decision(t,item,action,who='B',ref='SYN-REF-1'):return t.post('/finance/commission-work/'+item['id']+'/decision',headers=headers(who),json={'revision':item['revision'],'action':action,'evidence':'Independently checked synthetic records','reference':ref})
def test_end_to_end_rounding_approval_payment_reload(client):
 p=plan(client);r=claim(client,p);assert r.status_code==200;r=r.json();assert r['amount_cents']==17501
 assert decision(client,r,'approve','A').status_code==403
 assert decision(client,r,'approve','E1').status_code==403
 a=decision(client,r,'approve');assert a.status_code==200;a=a.json()
 assert decision(client,r,'approve').status_code==409
 paid=decision(client,a,'record_paid');assert paid.status_code==200
 assert decision(client,a,'record_paid').status_code==409
 c.store.ledger.reset();c.store.ledger.load(c.store.GRAPH_PATH)
 persisted=client.get('/finance/commission-work',headers=headers()).json();assert persisted['commissions'][0]['status']=='paid';assert len(persisted['commissions'][0]['history'])==3
 assert [d['id'] for d in persisted['deals']]==['D1']
def test_nonfunded_duplicate_and_reversal(client):
 p=plan(client);assert claim(client,p,'D2').status_code==422
 r=claim(client,p).json();assert claim(client,p).status_code==409
 a=decision(client,r,'approve').json();c.store.ledger.get_entity('D1').attributes['status']='cancelled'
 assert decision(client,a,'record_paid').status_code==409
 assert decision(client,a,'void').status_code==200
@pytest.mark.parametrize('role',['SALES','SERVICE','BDC','MARKETING','INVENTORY'])
def test_roles(client,role):assert client.get('/finance/commission-work',headers=headers(role=role)).status_code==403
def test_failed_persistence_rolls_back(client,monkeypatch):
 p=plan(client);r=claim(client,p).json()
 monkeypatch.setattr(c.store,'save_graph',lambda _:(_ for _ in ()).throw(OSError('disk failure')))
 with pytest.raises(OSError):decision(client,r,'approve')
 assert c.store.ledger.get_entity(r['id']).attributes['status']=='requested'
 assert c.store.ledger.get_entity(r['id']).attributes['revision']==1
