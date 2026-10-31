from copy import deepcopy
from test_dealership_lab import client, auth, make
from test_lab_setup import action
from chrono.shared.dealership import mixes
from core.dealership_lab import analysis, service as lab
from core.dealeros import ledger
from core.storage import load_graph


def preview(client,w,draft,kind='generate',scope='both'):
    url=f"/dealership-lab/workspaces/{w['id']}/mix"
    body=dict(revision=w['revision'],draft=draft,action=kind,scope=scope)
    response=client.post(url+'/preview',headers=auth(),json=body)
    return url,body,response


def test_mix_preview_exact_adoption_and_persistence(client):
    w=action(client,make(client),'path',{'mode':'hybrid'}).json()
    url=f"/dealership-lab/workspaces/{w['id']}/mix"
    state=client.get(url,headers=auth()).json();draft=state['mix']
    draft.update(vehicle_count=17,customer_count=23,seed=81)
    draft['templates'][0]['locked']=True
    original=analysis.compile_inputs(w)
    _,body,p=preview(client,w,draft,'random-unlocked')
    assert p.status_code==200,p.text
    generated=p.json()
    assert len(generated['mix']['inventory'])==17 and len(generated['mix']['people'])==23
    assert generated['mix']['templates'][0]['share']==draft['templates'][0]['share']
    assert client.post(url+'/preview',headers=auth(),json=body).json()==generated
    assert lab.serial(lab.workspace(w['id'],'LAB-STAFF'))==w
    canonical=deepcopy(original);canonical['mix']=draft
    expected=mixes.action(dict(input=canonical,action='random-unlocked',scope='both'))
    assert generated['mix']==expected['mix']
    assert generated['segments']==original['segments']
    assert client.post(url+'/save',headers=auth(),json=body).status_code==409
    assert client.post(url+'/preview',headers=auth('OTHER'),json=body).status_code==404
    saved=client.post(url+'/save',headers=auth(),json={**body,'token':generated['token']}).json()
    assert saved['revision']==w['revision']+1
    assert client.post(url+'/save',headers=auth(),json={**body,'token':generated['token']}).status_code==409
    _,adopt_body,adopt=preview(client,saved,generated['mix'],'apply-inventory')
    assert adopt.status_code==200,adopt.text
    assert sum(s['inventory'] for s in adopt.json()['segments'].values())==17
    assert adopt.json()['segments']['used']['replenishment']==original['segments']['used']['replenishment']
    assert client.post(url+'/save',headers=auth(),json={**adopt_body,'token':generated['token']}).status_code==409
    adopted=client.post(url+'/save',headers=auth(),json={**adopt_body,'token':adopt.json()['token']}).json()
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert lab.serial(lab.workspace(w['id'],'LAB-STAFF'))==adopted


def test_mix_real_path_invalid_shares_and_bhph_option_scope(client):
    w=action(client,make(client),'path',{'mode':'real'}).json()
    draft=analysis.compile_inputs(w)['mix']
    assert preview(client,w,draft)[2].status_code==422
    w=action(client,w,'path',{'mode':'hybrid'}).json()
    invalid=deepcopy(draft);invalid['templates'][0]['share']=0
    assert preview(client,w,invalid)[2].status_code==422
    assert preview(client,w,draft,'apply-customers')[2].status_code==422
    w=action(client,w,'configure',{'kind':'Buy Here Pay Here (BHPH) / Subprime Lots','reset_confirmed':True}).json()
    option=client.post(f"/dealership-lab/workspaces/{w['id']}/decisions",headers=auth(),json=dict(revision=w['revision'],name='Mix option',decision='cost',values={'monthly_cost':100})).json()
    model=analysis.compile_inputs(option);draft=model['mix']
    for row in draft['customers']:row.update(collection_rate=80,monthly_default=2)
    url,body,p=preview(client,option,draft,'apply-customers')
    assert p.status_code==200,p.text
    assert p.json()['finance']['scenario']['collection_rate']==80
    assert p.json()['finance']['baseline']==model['finance']['baseline']
    saved=client.post(url+'/save',headers=auth(),json={**body,'token':p.json()['token']})
    assert saved.status_code==200,saved.text
    assert lab.serial(lab.workspace(w['id'],'LAB-STAFF'))==w

def test_mix_current_bhph_sync_and_used_only_inventory_guard(client):
    w=action(client,make(client),'configure',{'kind':'Buy Here Pay Here (BHPH) / Subprime Lots','reset_confirmed':True}).json()
    w=action(client,w,'path',{'mode':'hybrid'}).json()
    draft=analysis.compile_inputs(w)['mix']
    for row in draft['customers']:row.update(collection_rate=73,monthly_default=3)
    _,_,p=preview(client,w,draft,'apply-customers')
    assert p.status_code==200,p.text
    assert p.json()['finance']['baseline']['collection_rate']==73
    assert p.json()['finance']['scenario']['collection_rate']==73
    draft['inventory']=[dict(make='Synthetic',model='Fixture',body='Sedan',condition='new',price=20000,cost=18000,year=2026,mileage=1)]
    assert preview(client,w,draft,'apply-inventory')[2].status_code==422
    draft['templates'][0]['share']=1
    # Incomplete proportions can be saved as a draft but cannot be generated.
    assert preview(client,w,draft,'save-draft')[2].status_code==200
    assert preview(client,w,draft,'generate')[2].status_code==422
