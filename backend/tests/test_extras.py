from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from api.routers import dealership_lab as api
from staff_auth_fixture import staff_token
from core.dealership_lab import service as lab, learning
from core.dealeros import ledger
from core.storage import load_graph

def auth(employee='EXTRA-A', role='SALES'):
    return {'Authorization':'Bearer '+staff_token(employee,role)}

@pytest.fixture
def client(monkeypatch):
    ledger.reset()
    # This suite exercises explicit claiming; automatic completion has its own tests.
    from core.dealership_lab import engagement
    monkeypatch.setattr(engagement, "on_work_completed", lambda actor: None)
    monkeypatch.delenv('DEALEROS_DEMO', raising=False)
    app=FastAPI();app.include_router(api.router);app.include_router(api.extras_router)
    with TestClient(app) as c: yield c
    ledger.reset()

def test_extras_remains_private_and_independent_of_lab_policy(client,monkeypatch):
    def blocked(): raise HTTPException(403,'Lab disabled')
    monkeypatch.setattr(api.policy,'require_enabled',blocked)
    assert client.get('/extras').status_code==401
    assert client.get('/extras',headers=auth(role='CUSTOMER')).status_code==403
    assert client.get('/dealership-lab',headers=auth()).status_code==403
    r=client.get('/extras',headers=auth());assert r.status_code==200
    assert r.json()['workspaces']==[]
    assert client.post('/extras/progress/deck',headers=auth(),json={'cards':['host','caller','analyst']}).status_code==200
    assert client.post('/extras/progress/equip',headers=auth(),json={'item':'invented'}).status_code==409

def test_learning_answer_validation_owner_isolation_and_persistence(client):
    k,_,_,_,_,_,answer=learning.LESSONS[0]
    path='/extras/learning/'+k
    assert client.post(path,headers=auth(),json={'answer':(answer+1)%3}).status_code==422
    for body in ({'answer':True},{'answer':answer,'xp':99999},{'answer':3}):
        assert client.post(path,headers=auth(),json=body).status_code==422
    assert client.get('/extras/progress',headers=auth()).json()['xp']==0
    def complete(_):return client.post(path,headers=auth(),json={'answer':answer})
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(r.status_code==200 for r in pool.map(complete,range(8)))
    assert client.get('/extras/progress',headers=auth()).json()['xp']==100
    assert client.get('/extras/progress',headers=auth('EXTRA-B')).json()['xp']==0
    assert not client.get('/extras/learning',headers=auth('EXTRA-B')).json()[0]['complete']
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert client.get('/extras/learning',headers=auth()).json()[0]['complete']
    assert client.get('/extras/progress',headers=auth()).json()['xp']==100

def test_existing_rewards_and_new_learning_share_one_profile(client):
    with lab.transaction():
        lab.record(lab.profile('EXTRA-A',True).attributes,'review','identity')
    before=client.get('/dealership-lab',headers=auth()).json()['progress']['xp']
    for key,*rest in learning.LESSONS:
        assert client.post('/extras/learning/'+key,headers=auth(),json={'answer':rest[-1]}).status_code==200
    p=client.get('/extras/progress',headers=auth()).json()
    assert p['xp']==before+800 and p['packs']['available']>=1
    assert len(lab.items(lab.PROFILE))==1
    assert client.get('/dealership-lab',headers=auth()).json()['progress']['xp']==p['xp']
    assert client.post('/extras/learning/unknown',headers=auth(),json={'answer':0}).status_code==404

def test_work_credit_requires_linked_completed_work_and_actual_completing_actor(client):
    from core.workflow_tracking import start_workflow_instance, advance_workflow_instance
    from core.workflow_catalog import get_catalog
    linked=lab.create('VEH','Vehicle',{'vin':'SYNTHETIC-TEST-ONLY'})
    definition=get_catalog()['Operations'][0]
    instance,error=start_workflow_instance(definition['key'],'EXTRA-A',linked.id)
    assert not error
    claim=lambda who='EXTRA-A':client.post('/extras/work-milestones/claim',headers=auth(who),json={})
    claim();assert lab.snapshot('EXTRA-A')['xp']==0
    for _ in definition['stages']:
        _,error=advance_workflow_instance(instance.id,'EXTRA-B');assert not error
    claim();assert lab.snapshot('EXTRA-A')['xp']==0
    claim('EXTRA-B');assert lab.snapshot('EXTRA-B')['xp']==150
    claim('EXTRA-B');assert lab.snapshot('EXTRA-B')['xp']==150
    assert client.post('/extras/work-milestones/claim',headers=auth(),json={'xp':999}).status_code==422
    # Missing source linkage is never treated as completed dealership work.
    instance,error=start_workflow_instance(definition['key'],'EXTRA-A')
    for _ in definition['stages']:advance_workflow_instance(instance.id,'EXTRA-A')
    claim();assert lab.snapshot('EXTRA-A')['xp']==0

def test_reward_save_failure_does_not_leave_in_memory_credit(client,monkeypatch):
    def fail(*a,**k):raise OSError('Synthetic storage failure')
    monkeypatch.setattr(lab,'save_graph',fail)
    lesson=learning.LESSONS[0]
    with pytest.raises(OSError):learning.complete('EXTRA-A',lesson[0],lesson[-1])
    assert lab.snapshot('EXTRA-A')['xp']==0

def test_v2_work_requires_all_steps_and_normal_completion(client):
    from core.workflow_engine_v2 import start_workflow_instance_v2, advance_step
    from core.workflow_definitions_v2 import list_workflow_defs_v2
    linked=lab.create('VEH','Vehicle',{'vin':'SYNTHETIC-V2-ONLY'})
    definition=list_workflow_defs_v2()[0]
    instance,error=start_workflow_instance_v2(definition['key'],'EXTRA-A',linked.id)
    assert not error
    for _ in definition['steps']:
        _,error=advance_step(instance.id,'EXTRA-A');assert not error
    assert any(m['eligible'] for m in learning.work_milestones('EXTRA-A'))
    instance.attributes['steps'][0]['status']='blocked'
    assert not any(m['eligible'] for m in learning.work_milestones('EXTRA-A'))

    instance.attributes['steps'][0]['status']='completed'
    instance.attributes['history'][-1]['action']='force_closed'
    assert not any(m['eligible'] for m in learning.work_milestones('EXTRA-A'))


def test_work_credit_uses_catalog_department_and_rejects_simulation_links(client):
    from core.workflow_tracking import start_workflow_instance, advance_workflow_instance
    from core.workflow_catalog import get_catalog
    vehicle=lab.create('VEH','Vehicle',{'vin':'SYNTHETIC-LINK-TEST'})
    definition=get_catalog()['Operations'][0]
    instance,error=start_workflow_instance(definition['key'],'EXTRA-A',vehicle.id)
    assert not error
    for _ in definition['stages']:advance_workflow_instance(instance.id,'EXTRA-A')
    instance.attributes['department']='Finance'
    milestones={m['department']:m for m in learning.work_milestones('EXTRA-A')}
    assert milestones['Operations']['eligible']
    assert not milestones['Finance']['eligible']
    simulation=lab.new_workspace('EXTRA-A','Synthetic simulation')
    for linked in (instance.id,simulation['id'],lab.profile('EXTRA-A',True).id,'MISSING'):
        instance.attributes['linked_entity_id']=linked
        response=client.post('/extras/work-milestones/claim',headers=auth(),json={})
        assert response.status_code==200
        assert not any(m['eligible'] for m in response.json())
        assert lab.snapshot('EXTRA-A')['xp']==0


def test_extras_pack_deck_and_game_resume_share_private_persisted_profile(client):
    import json
    from pathlib import Path
    for key,*rest in learning.LESSONS:
        assert client.post('/extras/learning/'+key,headers=auth(),json={'answer':rest[-1]}).status_code==200
    before=client.get('/extras/progress',headers=auth()).json()
    receipt=client.post('/extras/packs/open',headers=auth(),json={'request_id':'extras-parity-pack-001'})
    assert receipt.status_code==200,receipt.text
    card=receipt.json()['cards'][0]
    assert client.post('/extras/packs/equip',headers=auth(),json={'item':card}).status_code==200
    assert client.post('/extras/progress/deck',headers=auth(),json={'cards':['analyst','caller','host']}).status_code==200
    checkpoint=json.loads((Path(__file__).parent/'fixtures/lab-battle.json').read_text())
    saved=client.put('/extras/game',headers=auth(),json={'checkpoint':checkpoint})
    assert saved.status_code==200,saved.text
    ledger.reset();load_graph(lab.GRAPH_PATH)
    after=client.get('/extras/progress',headers=auth()).json()
    assert after['xp']==before['xp']
    assert after['game_checkpoint']==checkpoint
    assert after['deck']==['analyst','caller','host']
    assert card in after['packs']['equipped'].values()
    retry=client.post('/extras/packs/open',headers=auth(),json={'request_id':'extras-parity-pack-001'}).json()
    assert retry['cards']==receipt.json()['cards'] and retry['replayed']
    assert client.post('/extras/packs/equip',headers=auth('EXTRA-B'),json={'item':card}).status_code==409
    other=client.get('/extras/progress',headers=auth('EXTRA-B')).json()
    assert other['game_checkpoint'] is None and other['packs']['opened']==0 and other['xp']==0
