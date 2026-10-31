from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers import dealership_lab as api
from core.dealership_lab import service as lab, engagement, learning
from staff_auth_fixture import staff_token


def auth(who='STAFF', role='SALES'):
    return {'Authorization':'Bearer '+staff_token(who,role)}


@pytest.fixture
def client():
    lab.ledger.reset()
    app=FastAPI()
    app.include_router(api.extras_router)
    app.include_router(api.router)
    with TestClient(app) as c:
        yield c
    lab.ledger.reset()


def test_exploration_is_bounded_owned_and_persisted(client):
    headers=auth()
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: engagement.visit('STAFF','Sales'), range(12)))
    p=lab.snapshot('STAFF')
    assert p['xp']==25
    assert engagement.journey('STAFF')['active_days']==1
    assert lab.snapshot('OTHER')['xp']==0
    assert client.post('/extras/exploration',headers=headers,json={'area':'Sales','xp':5000}).status_code==422
    assert client.post('/extras/exploration',headers=headers,json={'area':'Finance'}).status_code==403
    assert client.post('/extras/exploration',headers=headers,json={'area':'Unknown'}).status_code==422
    from core.storage import load_graph
    lab.ledger.reset()
    load_graph(lab.GRAPH_PATH)
    assert lab.snapshot('STAFF')['xp']==25


def test_return_days_capped_without_consecutive_streak(client,monkeypatch):
    base=datetime(2026,1,1,tzinfo=timezone.utc)
    for n in range(30):
        monkeypatch.setattr(lab,'now',lambda n=n:base+timedelta(days=n*2))
        engagement.visit('STAFF','Sales')
        engagement.visit('STAFF','Sales')
    assert engagement.journey('STAFF')['active_days']==20
    assert lab.snapshot('STAFF')['xp']==375
    assert all(m['complete'] for m in engagement.journey('STAFF')['milestones'])


def test_policy_admin_only_revision_and_individual_override(client):
    staff=auth(); admin=auth('BOSS','ADMIN')
    assert client.get('/extras/policy',headers=staff).status_code==403
    assert client.put('/extras/policy',headers=staff,json={'enabled':False,'disabled_users':[],'revision':0}).status_code==403
    assert client.get('/extras/policy').status_code==401
    settings={'enabled':True,'disabled_users':['STAFF'],'revision':0}
    assert client.put('/extras/policy',headers=admin,json=settings).status_code==200
    assert client.put('/extras/policy',headers=admin,json=settings).status_code==409
    assert not client.get('/extras/progress',headers=staff).json()['enabled']
    assert client.get('/extras/progress',headers=admin).json()['enabled']
    assert client.post('/extras/exploration',headers=staff,json={'area':'Sales'}).json()['enabled'] is False
    assert lab.profile('STAFF') is None
    assert client.put('/extras/policy',headers=admin,json={'enabled':True,'disabled_users':['UNKNOWN'],'revision':1}).status_code==422
    assert len(lab.items('StaffRewardsPolicyAudit'))==1


def test_global_off_blocks_all_legacy_reward_writes_preserves_lab(client):
    headers=auth('BOSS','ADMIN')
    engagement.visit('BOSS','Sales')
    before=lab.snapshot('BOSS')['xp']
    assert client.put('/extras/policy',headers=headers,json={'enabled':False,'disabled_users':[],'revision':0}).status_code==200
    for prefix in ('/extras','/dealership-lab'):
        assert client.post(prefix+'/progress/equip',headers=headers,json={'item':'glacier'}).status_code==403
        assert client.post(prefix+'/packs/open',headers=headers,json={'request_id':'test-disabled-pack-0001'}).status_code==403
        assert client.put(prefix+'/game',headers=headers,json={'checkpoint':None}).status_code==403
    assert client.post('/extras/learning/operations-handoff-v1',headers=headers,json={'answer':1}).status_code==403
    assert client.post('/extras/work-milestones/claim',headers=headers,json={}).status_code==403
    # Core business/scenario work is usable with earning switched off.
    w=client.post('/dealership-lab/workspaces',headers=headers,json={'name':'Still usable'}).json()
    r=client.put('/dealership-lab/workspaces/'+w['id']+'/sections/identity',headers=headers,json={'revision':1,'values':w['sections']['identity']['values'],'basis':'assumed','note':'Reviewed synthetic assumptions','reviewed':True})
    assert r.status_code==200, r.text
    assert lab.snapshot('BOSS')['xp']==before
    assert client.put('/extras/policy',headers=headers,json={'enabled':True,'disabled_users':[],'revision':1}).status_code==200
    assert lab.snapshot('BOSS')['xp']==before


def test_disabled_period_not_backfilled(client,monkeypatch):
    auth('BOSS','ADMIN');auth()
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    monkeypatch.setattr(lab,'now',lambda:t)
    engagement.update('BOSS',False,[],0)
    monkeypatch.setattr(lab,'now',lambda:t+timedelta(days=2))
    engagement.update('BOSS',True,[],1)
    assert engagement.enabled_at('STAFF',(t-timedelta(days=1)).isoformat())
    assert not engagement.enabled_at('STAFF',(t+timedelta(days=1)).isoformat())
    assert engagement.enabled_at('STAFF',(t+timedelta(days=3)).isoformat())


def test_automatic_work_rewards_are_capped_and_only_for_completer(client):
    auth();auth("OTHER")
    from core.workflow_tracking import start_workflow_instance, advance_workflow_instance
    from core.workflow_catalog import get_catalog
    definition=get_catalog()['Operations'][0]
    source=lab.create('VEH','Vehicle',{'vin':'SYNTHETIC-ONLY'})
    instance,error=start_workflow_instance(definition['key'],'OTHER',source.id)
    assert not error
    for _ in definition['stages']:
        _,error=advance_workflow_instance(instance.id,'STAFF')
        assert not error
    assert lab.snapshot('STAFF')['xp']==200 # awarded immediately after persisted completion
    engagement.visit('OTHER','Sales')
    assert lab.snapshot('OTHER')['xp']==25
    engagement.visit('STAFF','Sales')
    assert lab.snapshot('STAFF')['xp']==225 # exploration + lifetime work + weekly work
    engagement.visit('STAFF','Sales')
    assert lab.snapshot('STAFF')['xp']==225


def test_policy_and_reward_storage_failure_roll_back(client,monkeypatch):
    auth('BOSS','ADMIN')
    def fail(*a,**k):raise OSError('Synthetic storage failure')
    monkeypatch.setattr(lab,'save_graph',fail)
    with pytest.raises(OSError):engagement.update('BOSS',False,[],0)
    assert engagement.enabled('STAFF')
    assert not lab.items('StaffRewardsPolicyAudit')
    with pytest.raises(OSError):engagement.visit('STAFF','Sales')
    assert lab.profile('STAFF') is None


@pytest.mark.parametrize('disabled',[True,False])
def test_work_completion_survives_disabled_or_failed_rewards(client,monkeypatch,disabled):
    from core.workflow_tracking import start_workflow_instance, advance_workflow_instance
    from core.workflow_catalog import get_catalog
    auth()
    if disabled:engagement.update('BOSS',False,[],0)
    else:
        def fail(*a,**k):raise OSError('Synthetic reward-only disk failure')
        monkeypatch.setattr(lab,'save_graph',fail)
    source=lab.create('VEH','Vehicle',{'vin':'SYNTHETIC-NONBLOCKING'})
    definition=get_catalog()['Operations'][0]
    instance,error=start_workflow_instance(definition['key'],'STAFF',source.id)
    assert not error
    for _ in definition['stages']:
        result,error=advance_workflow_instance(instance.id,'STAFF')
        assert not error
    assert result.attributes['status']=='completed'
    assert lab.ledger.get_entity(instance.id).attributes['status']=='completed'
    assert lab.snapshot('STAFF')['xp']==0
