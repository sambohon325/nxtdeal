from test_dealership_lab import client,auth,make
from test_lab_setup import action
from core.dealership_lab import service as lab

def planning_source(client):
    configured=action(client,make(client),'configure',{'size':'large','reset_confirmed':True}).json()
    state=client.get(f"/dealership-lab/workspaces/{configured['id']}/setup",headers=auth()).json()
    values=dict(profile={f[0]:state['input']['profile'][f[0]] for f in state['customer_fields']},segments=state['input']['segments'])
    values['profile'].update(organic_leads=500,response_rate=80,appointment_rate=50,show_rate=70,close_rate=30,market_index=100)
    configured=action(client,configured,'customers',values).json()
    return action(client,configured,'path',{'mode':'hybrid'}).json()

def test_goal_preview_source_isolation_and_explicit_idempotent_adoption(client):
    source=planning_source(client)
    url=f"/dealership-lab/workspaces/{source['id']}/goals"
    body=dict(revision=source['revision'],metric='vehicle_revenue',target=600000,months=2,seed=42,sales_per_person=10)
    response=client.post(url+'/preview',headers=auth(),json=body)
    assert response.status_code==200,response.text
    preview=response.json()
    assert preview['proposal']['changes']
    assert lab.serial(lab.workspace(source['id'],'LAB-STAFF'))==source
    assert len(lab.items(lab.WORKSPACE))==1
    assert preview['result']['terminal_expected']['sales']>0
    assert client.post(url+'/preview',headers=auth('OTHER'),json=body).status_code==404
    adopt=dict(revision=source['revision'],preview_id=preview['id'],name='Goal option')
    saved=client.post(url+'/adopt',headers=auth(),json=adopt)
    assert saved.status_code==200,saved.text
    option=saved.json();assert option['parent_id']==source['id']
    assert option['model_definition']['baseline']==source['model_definition']['baseline']
    assert option['model_definition']['segments']==preview['proposal']['input']['segments']
    assert client.post(url+'/adopt',headers=auth(),json=adopt).json()['id']==option['id']
    assert client.post(url+'/adopt',headers=auth(),json={**adopt,'name':'Different'}).status_code==409
    assert lab.serial(lab.workspace(source['id'],'LAB-STAFF'))==source
    from core.dealeros import ledger
    from core.storage import load_graph
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert lab.serial(ledger.get_entity(preview['id']))==preview
    assert client.post(url+'/adopt',headers=auth(),json=adopt).json()['id']==option['id']

def test_goal_stale_and_real_path_guard(client):
    source=planning_source(client)
    url=f"/dealership-lab/workspaces/{source['id']}/goals"
    body=dict(revision=source['revision'],metric='contribution',target=1000,months=2)
    result=client.post(url+'/preview',headers=auth(),json=body)
    assert result.status_code==200,result.text
    changed=action(client,source,'configure',{'city':'Changed after preview'}).json()
    assert client.post(url+'/adopt',headers=auth(),json=dict(revision=changed['revision'],preview_id=result.json()['id'],name='Stale')).status_code==409
    real=action(client,changed,'path',{'mode':'real'}).json()
    assert client.post(url+'/preview',headers=auth(),json={**body,'revision':real['revision']}).status_code==422

def test_goal_admission_failure_does_not_persist_preview(client):
    from chrono.shared.compute_admission import numerical_jobs
    from core.dealership_lab.goals import PREVIEW
    source=planning_source(client)
    with numerical_jobs.enter():
        result=client.post(f"/dealership-lab/workspaces/{source['id']}/goals/preview",headers=auth(),json=dict(revision=source['revision'],metric='vehicle_revenue',target=600000,months=2))
    assert result.status_code==503
    assert result.headers['retry-after']=='5'
    assert not lab.items(PREVIEW)
    assert lab.serial(lab.workspace(source['id'],'LAB-STAFF'))==source



def test_goal_history_keeps_frozen_results_and_scopes_access(client):
    source=planning_source(client)
    url=f"/dealership-lab/workspaces/{source['id']}/goals"
    body=dict(revision=source['revision'],metric='vehicle_revenue',target=600000,months=2,seed=42)
    result=client.post(url+'/preview',headers=auth(),json=body)
    assert result.status_code==200,result.text
    saved=result.json();detail=url+'/'+saved['id']
    assert [r['id'] for r in client.get(url,headers=auth()).json()['previews']]==[saved['id']]
    assert client.get(url,headers=auth('OTHER')).status_code==404
    assert client.get(detail,headers=auth('OTHER')).status_code==404
    other=make(client)
    assert client.get(f"/dealership-lab/workspaces/{other['id']}/goals/{saved['id']}",headers=auth()).status_code==404
    assert client.get(detail,headers=auth()).json()['can_adopt'] is True
    option=client.post(url+'/adopt',headers=auth(),json=dict(revision=source['revision'],preview_id=saved['id'],name='Saved goal')).json()
    action(client,source,'configure',{'city':'Changed'})
    from core.dealeros import ledger
    from core.storage import load_graph
    ledger.reset();load_graph(lab.GRAPH_PATH)
    reopened=client.get(detail,headers=auth()).json()
    assert reopened['can_adopt'] is False
    assert reopened['adopted_option']['id']==option['id']
    assert {k:reopened[k] for k in saved}==saved
    assert lab.serial(ledger.get_entity(saved['id']))==saved
