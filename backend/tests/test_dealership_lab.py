from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import dealership_lab as api
from staff_auth_fixture import staff_token
from core.dealership_lab import service as lab
from core.dealeros import ledger
from core.storage import load_graph


def auth(employee='LAB-STAFF', role='SALES'):
    return {'Authorization': 'Bearer ' + staff_token(employee, role)}


def test_reports_preview_corrections_privacy_and_chrono_lineage(client):
    w=make(client);base='/dealership-lab/workspaces/'+w['id']+'/reports'
    csv='month,rooftop,currency,leads,responded_leads\n'+''.join(f'2025-{m:02d},A,USD,{100+m*4},{80+m*2}\n' for m in range(1,10))
    body=dict(revision=0,workspace_revision=w['revision'],csv=csv,source='Synthetic automated test fixture; not production data.')
    p=client.post(base+'/preview',headers=auth(),json=body)
    assert p.status_code==200,p.text
    assert len(p.json()['changes'])==18
    commit=dict(**body,token=p.json()['token'],acknowledge=True,request_id='test-reports-0001')
    assert client.post(base+'/import',headers=auth(),json={**commit,'acknowledge':False}).status_code==422
    saved=client.post(base+'/import',headers=auth(),json=commit)
    assert saved.status_code==200,saved.text
    assert client.post(base+'/import',headers=auth(),json=commit).json()['id']==saved.json()['id']
    assert client.get(base,headers=auth('OTHER')).status_code==404
    assert client.post(base+'/preview',headers=auth(),json=body).status_code==409
    change={**body,'revision':1,'csv':'month,rooftop,currency,leads,responded_leads\n2025-09,A,USD,145,\n'}
    p=client.post(base+'/preview',headers=auth(),json=change).json()
    assert len(p['changes'])==1
    assert p['rows'][-1]['values']['responded_leads']==98
    assert client.post(base+'/import',headers=auth(),json={**change,'token':'0'*64,'acknowledge':True,'request_id':'test-reports-0002'}).status_code==409
    response=client.post(base+'/import',headers=auth(),json={**change,'token':p['token'],'acknowledge':True,'request_id':'test-reports-0002'})
    assert response.status_code==200,response.text
    req=dict(revision=2,metric='leads',months=3,seed=42,target=140,failure=50,request_id='test-outlook-0001')
    run=client.post(base+'/outlook',headers=auth(),json=req)
    assert run.status_code==200,run.text
    r=run.json();assert len(r['facts'])==9
    assert r['origin_month']=='2025-09'
    assert r['payload']['bands']['leads']['median'][0]==145
    assert saved.json()['id'] in r['facts'][0]['evidence']['parent_ids']
    assert client.post(base+'/outlook',headers=auth(),json=req).json()['id']==r['id']
    assert client.post(base+'/outlook',headers=auth(),json={**req,'target':141}).status_code==409
    ledger.reset();load_graph(lab.GRAPH_PATH)
    restored=client.get(base,headers=auth()).json()
    assert restored['revision']==2 and len(restored['imports'])==2 and len(restored['outlooks'])==1
    assert restored['imports'][0]['rows'][-1]['values']['leads']==136


def test_report_missing_scope_and_bad_relationships_fail_closed(client):
    w=make(client);base='/dealership-lab/workspaces/'+w['id']+'/reports'
    body=dict(revision=0,workspace_revision=1,csv='month,rooftop,currency,leads,responded_leads\n2025-01,A,USD,10,20\n',source='Synthetic automated test fixture')
    assert client.post(base+'/preview',headers=auth(),json=body).status_code==422
    body['csv']='month,rooftop,currency,leads\n2025-01,A,USD,10\n'
    p=client.post(base+'/preview',headers=auth(),json=body).json()
    client.post(base+'/import',headers=auth(),json={**body,'token':p['token'],'acknowledge':True,'request_id':'test-report-small'})
    req=dict(revision=1,metric='leads',months=3,target=20,failure=1,request_id='test-outlook-small')
    assert client.post(base+'/outlook',headers=auth(),json=req).status_code==422
    assert client.post(base+'/outlook',headers=auth(),json={**req,'rooftop':'Missing'}).status_code==422


def test_report_calibration_forks_reviewed_unit_economics_only(client):
    from core.dealership_lab import analysis
    w=make(client);base='/dealership-lab/workspaces/'+w['id']+'/reports'
    before=analysis.compile_inputs(w)
    body=dict(revision=0,workspace_revision=1,csv='month,rooftop,currency,new_units,used_units,used_revenue,used_gross\n2025-09,A,USD,0,10,250000,28000\n',source='Synthetic automated calibration test fixture')
    p=client.post(base+'/preview',headers=auth(),json=body).json()
    client.post(base+'/import',headers=auth(),json={**body,'token':p['token'],'acknowledge':True,'request_id':'test-report-calibrate'})
    req=dict(revision=1,workspace_revision=1,rooftop=None)
    p=client.post(base+'/calibration',headers=auth(),json=req)
    assert p.status_code==200,p.text
    assert p.json()['input']['segments']['used']['gross']==2800
    req.update(token=p.json()['token'],name='Calibrated test option')
    fork=client.post(base+'/calibrated-option',headers=auth(),json=req)
    assert fork.status_code==200,fork.text
    f=fork.json();assert f['parent_id']==w['id']
    assert f['model_definition']['workflow']['mode']=='hybrid'
    assert f['model_definition']['scenario']['operating']==before['scenario']['operating']
    assert client.post(base+'/calibrated-option',headers=auth(),json=req).json()['id']==f['id']
    assert analysis.compile_inputs(lab.serial(lab.workspace(w['id'],'LAB-STAFF')))==before

    # A corrected source requires a new preview and option; the old option
    # continues to represent the source revision originally reviewed.
    correction={**body,'revision':1,'csv':body['csv'].replace('28000','35000')}
    preview=client.post(base+'/preview',headers=auth(),json=correction)
    assert preview.status_code==200,preview.text
    saved=client.post(base+'/import',headers=auth(),json={**correction,
        'token':preview.json()['token'],'acknowledge':True,'request_id':'test-report-calibrate-correction'})
    assert saved.status_code==200,saved.text
    assert client.post(base+'/calibrated-option',headers=auth(),json=req).status_code==409
    fresh=dict(revision=2,workspace_revision=1,rooftop=None)
    preview=client.post(base+'/calibration',headers=auth(),json=fresh)
    assert preview.status_code==200,preview.text
    assert preview.json()['input']['segments']['used']['gross']==3500
    replacement=client.post(base+'/calibrated-option',headers=auth(),json={**fresh,
        'token':preview.json()['token'],'name':'Corrected source option'})
    assert replacement.status_code==200,replacement.text
    updated=replacement.json()
    assert updated['id']!=f['id']
    assert updated['report_source']['revision']==2
    assert f['report_source']['revision']==1
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert lab.serial(lab.workspace(f['id'],'LAB-STAFF'))==f
    assert analysis.compile_inputs(lab.serial(lab.workspace(w['id'],'LAB-STAFF')))==before
    assert client.get(base,headers=auth('OTHER')).status_code==404


def test_hub_lab_policy_refuses_fallback_and_enforces_disabled(client,monkeypatch):
    from api.routers.dealership_lab_policy import router
    from core.dealership_lab import policy
    client.app.include_router(router)
    path='/network/dealership-lab-policy'
    monkeypatch.setattr(policy,'get_secret',lambda *_:'dev-only-insecure-network-key-change-me')
    monkeypatch.setenv('NXTDEAL_DEALER_ID','DLR-TEST')
    assert client.get(path,params={'dealer_id':'DLR-TEST'}).status_code==503
    monkeypatch.setattr(policy,'get_secret',lambda *_:'unit-test-key-not-for-live-00000000000')
    headers={'X-NXTDeal-Network-Key':'unit-test-key-not-for-live-00000000000'}
    assert client.get(path,params={'dealer_id':'DLR-TEST'}).status_code==401
    assert client.get(path,headers=headers,params={'dealer_id':'WRONG'}).status_code==409
    assert client.get(path,headers=headers,params={'dealer_id':'DLR-TEST'}).json()['revision']==0
    assert client.post(path,headers=headers,json={'dealer_id':'DLR-TEST','enabled':False,'revision':0}).status_code==200
    assert client.get('/dealership-lab',headers=auth()).status_code==403
    assert client.post('/dealership-lab/workspaces',headers=auth(),json={'name':'Blocked'}).status_code==403
    assert client.post(path,headers=headers,json={'dealer_id':'DLR-TEST','enabled':True,'revision':0}).status_code==409
    assert client.post(path,headers=headers,json={'dealer_id':'DLR-TEST','enabled':True,'revision':1}).status_code==200
    assert client.get('/dealership-lab',headers=auth()).status_code==200
    assert len(lab.items('DealershipLabPolicyAudit'))==2


@pytest.fixture
def client(monkeypatch):
    ledger.reset()
    monkeypatch.delenv('DEALEROS_DEMO', raising=False)
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as c:
        yield c
    ledger.reset()


def make(client, name='Test dealership', source=None, employee='LAB-STAFF'):
    response = client.post('/dealership-lab/workspaces', headers=auth(employee), json={'name': name, 'source_id': source})
    assert response.status_code == 200, response.text
    return response.json()


def review(client, w, section='identity', **extra):
    return client.put('/dealership-lab/workspaces/' + w['id'] + '/sections/' + section, headers=auth(), json={'values':w['sections'][section]['values'], 'revision':w['revision'], 'note':'Illustrative assumptions only, not actual dealership data.', 'basis':'assumed', 'reviewed':True, **extra})


def test_auth_and_employee_scope(client):
    assert client.get('/dealership-lab').status_code == 401
    assert client.get('/dealership-lab', headers=auth(role='CUSTOMER')).status_code == 403
    w = make(client)
    assert client.get('/dealership-lab', headers=auth('OTHER')).json()['workspaces'] == []
    assert client.get('/dealership-lab/workspaces/' + w['id'] + '/versions', headers=auth('OTHER')).status_code == 404
    assert client.post('/dealership-lab/workspaces', headers=auth('OTHER'), json={'name':'Illicit fork','source_id':w['id']}).status_code == 404
    assert client.get('/dealership-lab', headers=auth()).json()['analysis']['status'] == 'assumption_scenarios'


def test_review_rewards_are_idempotent_and_persist(client):
    w = make(client)
    updated = review(client, w).json()
    assert updated['revision'] == 2
    state = client.get('/dealership-lab', headers=auth()).json()['progress']
    assert state['xp'] == 160  # milestone + daily review + first inspection
    assert 'principal' in state['unlocked']
    assert review(client, updated).json()['revision'] == 2
    assert client.get('/dealership-lab', headers=auth()).json()['progress']['xp'] == 160
    ledger.reset()
    load_graph(lab.GRAPH_PATH)
    reloaded = client.get('/dealership-lab', headers=auth()).json()
    assert reloaded['progress']['xp'] == 160
    assert reloaded['workspaces'][0]['revision'] == 2
    assert len(client.get('/dealership-lab/workspaces/' + w['id'] + '/versions', headers=auth()).json()['versions']) == 2


def test_stale_save_and_archive(client):
    w = make(client)
    updated = review(client, w).json()
    assert review(client, w).status_code == 409
    response = client.post('/dealership-lab/workspaces/' + w['id'] + '/archive', headers=auth(), json={'revision':updated['revision']})
    assert response.json()['archived']
    assert review(client, response.json()).status_code == 409
    restored = client.post('/dealership-lab/workspaces/' + w['id'] + '/archive', headers=auth(), json={'revision':response.json()['revision']})
    assert not restored.json()['archived']


def test_fork_and_history_are_independent(client):
    w = make(client)
    w = review(client, w).json()
    child = make(client, 'Changed team', w['id'])
    assert child['parent_id'] == w['id']
    grandchild = make(client, 'Another option', child['id'])
    assert grandchild['parent_id'] == w['id']
    changed = child['sections']['identity']['values'] | {'name':'Separate name'}
    assert review(client, child, values=changed).status_code == 200
    assert lab.workspace(w['id'], 'LAB-STAFF').attributes['sections']['identity']['values']['name'] == 'My dealership'
    versions = client.get('/dealership-lab/workspaces/' + child['id'] + '/versions', headers=auth()).json()['versions']
    assert versions[0]['sections']['identity']['values']['name'] == 'My dealership'
    assert versions[1]['sections']['identity']['values']['name'] == 'Separate name'


@pytest.mark.parametrize('patch', [{'reviewed':True,'note':'short'}, {'values':{}}, {'basis':'verified'}, {'revision':True}, {'xp':999}])
def test_invalid_review_rejected(client, patch):
    w = make(client)
    assert review(client, w, **patch).status_code == 422
    assert client.get('/dealership-lab', headers=auth()).json()['progress']['xp'] == 0


def test_invalid_field_values(client):
    w = make(client)
    for value in [True, -1, 101, '15']:
        values = w['sections']['identity']['values'] | {'rooftops':value}
        assert review(client, w, values=values).status_code == 422


def test_quest_reset_and_repeated_reviews(client, monkeypatch):
    at = datetime(2026, 10, 5, 22, tzinfo=timezone.utc)
    monkeypatch.setattr(lab, 'now', lambda: at)
    w = make(client)
    w = review(client, w).json()
    monkeypatch.setattr(lab, 'now', lambda: at + timedelta(days=1))
    assert client.get('/dealership-lab', headers=auth()).json()['progress']['quests'][0]['progress'] == 0
    review(client, w)
    state = client.get('/dealership-lab', headers=auth()).json()['progress']
    assert state['xp'] == 210  # daily quest again, no milestone or achievement replay
    assert state['quests'][2]['progress'] == 1  # distinct sections in weekly quest


def test_packs_unlocks_and_idempotent_concurrent_draw(client):
    assert client.post('/dealership-lab/packs/open', headers=auth(), json={'request_id':'pack-attempt-0000001'}).status_code == 409
    w = make(client)
    for section in lab.SECTIONS:
        w = review(client, w, section).json()
    state = lab.snapshot('LAB-STAFF')
    assert state['level'] >= 4
    assert len(state['unlocked']) == 11  # champion still requires an actual run
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: lab.open_pack('LAB-STAFF', 'same-request-0000001'), range(4)))
    assert sum(not r['replayed'] for r in results) == 1
    assert all(r['cards'] == results[0]['cards'] for r in results)
    assert len(set(results[0]['cards'])) == 5
    rarity = {v['id']:v['rarity'] for v in lab.CATALOG['variants']}
    assert rarity[results[0]['cards'][-1]] in {'Rare','Legendary'}
    assert lab.snapshot('LAB-STAFF')['packs']['opened'] == 1
    assert lab.snapshot('LAB-STAFF')['xp'] == state['xp']
    assert client.post('/dealership-lab/packs/equip', headers=auth(), json={'item':results[0]['cards'][0]}).status_code == 200
    assert client.post('/dealership-lab/packs/equip', headers=auth('OTHER'), json={'item':results[0]['cards'][0]}).status_code == 409


def test_deck_and_cosmetic_gates(client):
    assert client.post('/dealership-lab/progress/deck',headers=auth(),json={'cards':['host','caller','analyst']}).status_code == 200
    for cards in [['host','host','analyst'],['host','caller','champion'],['made-up','caller','analyst']]:
        assert client.post('/dealership-lab/progress/deck',headers=auth(),json={'cards':cards}).status_code == 422
    assert client.post('/dealership-lab/progress/equip',headers=auth(),json={'item':'spacecats'}).status_code == 409
    assert client.post('/dealership-lab/progress/equip',headers=auth(),json={'item':'silver'}).status_code == 200


def test_failed_persistence_rolls_back_rewards_and_versions(client, monkeypatch):
    w = make(client)
    def fail(_):
        raise OSError('disk unavailable')
    monkeypatch.setattr(lab, 'save_graph', fail)
    with pytest.raises(OSError):
        review(client, w)
    assert lab.workspace(w['id'], 'LAB-STAFF').attributes['revision'] == 1
    assert lab.snapshot('LAB-STAFF')['xp'] == 0
    assert len(lab.items(lab.VERSION)) == 1


def reviewed_workspace(client):
    w=make(client)
    for section in lab.SECTIONS:
        response=review(client,w,section)
        assert response.status_code==200,response.text
        w=response.json()
    return w


def test_shared_chrono_bundle_has_no_local_fork():
    import hashlib,json
    from pathlib import Path
    root=Path(__file__).parents[1]/'chrono/shared'
    manifest=json.loads((root/'MANIFEST.json').read_text())
    assert len(manifest['commit'])==40
    for name,expected in manifest['files'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name


def test_paired_comparison_is_saved_private_and_idempotent(client):
    w=reviewed_workspace(client)
    body=dict(baseline_id=w['id'],proposed_id=w['id'],baseline_revision=w['revision'],proposed_revision=w['revision'],months=2,seed=42,target=0,request_id='comparison-request-0001')
    result=client.post('/dealership-lab/runs',headers=auth(),json=body)
    assert result.status_code==200,result.text
    run=result.json()
    assert all(v==0 for v in run['payload']['difference']['profit']['median'])
    assert not run['payload']['baseline']['input_fact_ids']
    assert client.post('/dealership-lab/runs',headers=auth(),json=body).json()==run
    assert client.get('/dealership-lab/runs/'+run['id'],headers=auth('OTHER')).status_code==404
    assert client.get('/dealership-lab/runs',headers=auth('OTHER')).json()=={'runs':[]}
    assert client.post('/dealership-lab/runs',headers=auth(),json={**body,'seed':43}).status_code==409
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert client.get('/dealership-lab/runs/'+run['id'],headers=auth()).json()==run


def test_comparison_requires_reviewed_current_inputs(client):
    w=make(client)
    body=dict(baseline_id=w['id'],proposed_id=w['id'],baseline_revision=1,proposed_revision=1,request_id='comparison-request-0002')
    assert client.post('/dealership-lab/runs',headers=auth(),json=body).status_code==422
    w=review(client,w).json()
    assert client.post('/dealership-lab/runs',headers=auth(),json=body).status_code==409


def test_detailed_model_roundtrip_and_builder_lock(client):
    w=make(client)
    model=client.get('/dealership-lab/workspaces/'+w['id']+'/model',headers=auth())
    assert model.status_code==200,model.text
    response=client.put('/dealership-lab/workspaces/'+w['id']+'/model',headers=auth(),json={'revision':w['revision'],'definition':model.json()['input']})
    assert response.status_code==200,response.text
    w=response.json()
    assert review(client,w).status_code==409
    assert client.put('/dealership-lab/workspaces/'+w['id']+'/model',headers=auth('OTHER'),json={'revision':w['revision'],'definition':None}).status_code==404
    response=client.put('/dealership-lab/workspaces/'+w['id']+'/model',headers=auth(),json={'revision':w['revision'],'definition':None})
    assert review(client,response.json()).status_code==200


def test_game_checkpoint_resumes_and_does_not_award_xp(client):
    import json
    from pathlib import Path
    state=json.loads((Path(__file__).parent/'fixtures/lab-battle.json').read_text())
    response=client.put('/dealership-lab/game',headers=auth(),json={'checkpoint':state})
    assert response.status_code==200,response.text
    assert response.json()['game_checkpoint']==state
    assert response.json()['xp']==0
    assert client.get('/dealership-lab',headers=auth('OTHER')).json()['progress']['game_checkpoint'] is None
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert client.get('/dealership-lab',headers=auth()).json()['progress']['game_checkpoint']==state
    for invalid in ({'id':{}},{'status':[]},{'team':[{}, {}, {}]},{'foes':None},{'enemy':1.5}):
        assert client.put('/dealership-lab/game',headers=auth(),json={'checkpoint':{**state,**invalid}}).status_code==422


def test_decision_option_keeps_source_and_has_real_model_effect(client):
    w=reviewed_workspace(client)
    before=client.get('/dealership-lab/workspaces/'+w['id']+'/model',headers=auth()).json()['input']
    body=dict(name='Extra occupancy cost',revision=w['revision'],decision='cost',values={'monthly_cost':1000},implementation_cost=0)
    response=client.post('/dealership-lab/workspaces/'+w['id']+'/decisions',headers=auth(),json=body)
    assert response.status_code==200,response.text
    option=response.json()
    assert option['parent_id']==w['id']
    assert client.get('/dealership-lab/workspaces/'+w['id']+'/model',headers=auth()).json()['input']==before
    result=client.post('/dealership-lab/runs',headers=auth(),json=dict(baseline_id=w['id'],proposed_id=option['id'],baseline_revision=w['revision'],proposed_revision=1,months=2,request_id='decision-comparison-001'))
    assert result.status_code==200,result.text
    assert result.json()['payload']['difference']['profit']['median'][-1]==pytest.approx(-2000)
    assert client.post('/dealership-lab/workspaces/'+w['id']+'/decisions',headers=auth('OTHER'),json=body).status_code==404
    assert client.post('/dealership-lab/workspaces/'+w['id']+'/decisions',headers=auth(),json={**body,'values':{'monthly_cost':0}}).status_code==422


def saved_comparison(client):
    w=reviewed_workspace(client)
    result=client.post('/dealership-lab/runs',headers=auth(),json=dict(baseline_id=w['id'],proposed_id=w['id'],baseline_revision=w['revision'],proposed_revision=w['revision'],months=2,request_id='notebook-comparison-0001'))
    assert result.status_code==200,result.text
    return result.json()


def test_notebook_freezes_evidence_and_preserves_unknowns(client):
    run=saved_comparison(client)
    result=client.post('/dealership-lab/notebooks',headers=auth(),json=dict(run_id=run['id'],department='parts',kind='workbook'))
    assert result.status_code==200,result.text
    book=result.json()
    assert book['measures'][0]['proposed'] is None
    fields={**book,'notes':'A private learning worksheet'}
    fields['measures'][0]['manual']=200
    assert client.put('/dealership-lab/notebooks/'+book['id'],headers=auth(),json=dict(revision=1,fields=fields)).status_code==422
    fields['measures'][0]['source']='User-reported October 2026; unverified'
    response=client.put('/dealership-lab/notebooks/'+book['id'],headers=auth(),json=dict(revision=1,fields=fields))
    assert response.status_code==200,response.text
    assert response.json()['measures'][0]['proposed'] is None
    assert client.put('/dealership-lab/notebooks/'+book['id'],headers=auth(),json=dict(revision=1,fields=fields)).status_code==409
    assert client.get('/dealership-lab/notebooks/'+book['id']+'/history',headers=auth('OTHER')).status_code==404
    assert client.get('/dealership-lab/notebooks',headers=auth('OTHER')).json()['notebooks']==[]
    assert len(client.get('/dealership-lab/notebooks/'+book['id']+'/history',headers=auth()).json()['versions'])==2


def test_procedure_lock_requires_reviews_and_preserves_edition(client):
    run=saved_comparison(client)
    book=client.post('/dealership-lab/notebooks',headers=auth(),json=dict(run_id=run['id'],department='sales',kind='procedure')).json()
    assert [p['available'] for p in book['projections']]==[True,True,False,False]
    assert all(m['delta']==0 for p in book['projections'] for m in p['measures'] if m['delta'] is not None)
    assert {'security','used'}.issubset({c['id'] for c in book['controls']})
    assert book['costs']==dict(setup=0,monthly=0,hours=0,rate=0)
    path='/dealership-lab/notebooks/'+book['id']
    assert client.put(path,headers=auth(),json=dict(revision=1,action='lock',fields=book)).status_code==422
    fields={**book,'responsible':'QA reviewer','reviewer':'QA reviewer','review_due':'2099-01-01','objective':'Test learning workflow','steps':'Inspect the saved inputs and record the outcome.','exceptions':'Escalate uncertain inputs to a qualified reviewer.','acknowledge':True}
    for c in fields['controls']:c.update(status='reviewed',evidence='Synthetic test review only, not compliance evidence.')
    for c in fields['checkpoints']:c.update(action='Review outcome',target='Document one evidence-backed observation')
    response=client.put(path,headers=auth(),json=dict(revision=1,action='lock',fields=fields))
    assert response.status_code==200,response.text
    assert response.json()['status']=='locked'
    assert client.put(path,headers=auth(),json=dict(revision=2,fields=fields)).status_code==409
    response=client.put(path,headers=auth(),json=dict(revision=2,action='revise',fields={}))
    assert response.json()['edition']==2
    history=client.get(path+'/history',headers=auth()).json()['versions']
    assert history[1]['status']=='locked' and history[1]['edition']==1
    assert history[2]['status']=='draft' and history[2]['controls'][0]['status']=='open'


def test_compact_finance_scales_rooftops_without_reinterpreting_frozen_inputs(client):
    from core.dealership_lab import analysis,notebooks
    w=make(client)
    w['sections']['identity']['values']['rooftops']=3
    w['sections']['economics']['values'].update(cash=20000,debt_service=1200)
    e=analysis.compile_inputs(w)
    assert e['finance']['scenario']['opening_cash']==60000
    assert e['finance']['scenario']['debt_principal']==3600
    run=saved_comparison(client)
    assert notebooks.frozen_input(run,'proposed')==run['calculation_inputs']['proposed']


def test_finance_detail_replays_frozen_inputs_without_rewriting_run(client):
    from chrono.shared.dealership.model import simulate_one
    from chrono.shared.dealership.earnings import cashflow
    from core.dealership_lab import analysis
    w=reviewed_workspace(client)
    body=dict(baseline_id=w['id'],proposed_id=w['id'],baseline_revision=w['revision'],proposed_revision=w['revision'],months=2,seed=71,target=0,request_id='finance-detail-test-0001')
    run=client.post('/dealership-lab/runs',headers=auth(),json=body).json()
    url='/dealership-lab/runs/'+run['id']+'/finance-detail'
    response=client.get(url,headers=auth());assert response.status_code==200,response.text
    detail=response.json()
    model=analysis.validate({**run['calculation_inputs']['baseline'],'months':2,'seed':71,'trials':100})
    expected=cashflow(simulate_one(model,'scenario',0),model,'scenario')
    assert detail['sides']['baseline']['monthly']==expected
    assert detail['sides']['baseline']==detail['sides']['proposed']
    assert expected[-1]['cash_balance']==pytest.approx(model['finance']['scenario']['opening_cash']+sum(r['net_cash'] for r in expected))
    assert client.get(url,headers=auth('OTHER')).status_code==404
    client.post('/dealership-lab/workspaces/'+w['id']+'/archive',headers=auth(),json={'revision':w['revision']})
    assert client.get(url,headers=auth()).json()==detail
    assert client.get('/dealership-lab/runs/'+run['id'],headers=auth()).json()==run
    ledger.get_entity(run['id']).attributes['shared_engine_commit']='0'*40
    assert client.get(url,headers=auth()).status_code==409


def test_c120_new_schedule_and_explicit_legacy_edition_preserve_evidence(client):
    from copy import deepcopy
    from core.dealership_lab import notebooks
    run=saved_comparison(client)
    book=client.post('/dealership-lab/notebooks',headers=auth(),json=dict(run_id=run['id'],department='sales',kind='procedure')).json()
    assert [c['days'] for c in book['checkpoints']]==[30,60,90,120]
    assert book['checkpoint_schedule']=='c30-c60-c90-c120-v2'
    assert book['projections'][-1]['available'] is False
    # Seed an old locked edition, as persisted by the previous implementation.
    with lab.transaction():
        entity=notebooks.get(book['id'],'LAB-STAFF')
        entity.attributes.pop('checkpoint_schedule')
        entity.attributes.update(status='locked',revision=2)
        entity.attributes['checkpoints'][-1].update(days=365,actual='Annual result',evidence='Synthetic annual period evidence',status='complete')
        notebooks.history(entity)
    path='/dealership-lab/notebooks/'+book['id']
    old=deepcopy(client.get(path+'/history',headers=auth()).json()['versions'])
    request=dict(revision=2,action='upgrade-checkpoints',fields={})
    assert client.put(path,headers=auth('OTHER'),json=request).status_code==404
    updated=client.put(path,headers=auth(),json=request)
    assert updated.status_code==200,updated.text
    result=updated.json()
    assert result['status']=='draft' and result['edition']==2 and result['revision']==3
    assert [c['days'] for c in result['checkpoints']]==[30,60,90,120]
    assert result['checkpoints'][-1]['actual']=='' and result['checkpoints'][-1]['status']=='planned'
    assert result['checkpoint_migrations'][0]['checkpoints'][-1]['actual']=='Annual result'
    assert client.get(path+'/history',headers=auth()).json()['versions'][:len(old)]==old
    assert client.put(path,headers=auth(),json=request).status_code==409
    assert client.put(path,headers=auth(),json={**request,'revision':3}).status_code==422
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert notebooks.get(book['id'],'LAB-STAFF').attributes['checkpoint_migrations']==result['checkpoint_migrations']

def test_finance_replay_previous_bundle_hash_evidence_and_fail_closed(client, monkeypatch):
    from core.dealership_lab import replay, analysis
    run=saved_comparison(client)
    prior='9be8c951f177289b4635d11d38327bfab46d1677'
    ledger.get_entity(run['id']).attributes['shared_engine_commit']=prior
    frozen=lab.serial(ledger.get_entity(run['id']))
    url='/dealership-lab/runs/'+run['id']+'/finance-detail'
    response=client.get(url,headers=auth())
    assert response.status_code==200,response.text
    detail=response.json()
    assert detail['shared_engine_commit']==prior
    assert detail['replay_engine_commit']==analysis.SHARED_VERSION
    assert detail['compatibility']=='verified unchanged prior bundle'
    assert lab.serial(ledger.get_entity(run['id']))==frozen
    changed=dict(replay.EVIDENCE[prior]);changed['dealership/model.py']='0'*64
    monkeypatch.setattr(replay,'EVIDENCE',{prior:changed})
    assert client.get(url,headers=auth()).status_code==409
    assert lab.serial(ledger.get_entity(run['id']))==frozen

def test_notebook_readable_export_preserves_historical_fields_and_escapes_html(client):
    from core.dealership_lab import notebooks
    run=saved_comparison(client)
    book=client.post('/dealership-lab/notebooks',headers=auth(),json=dict(run_id=run['id'],department='sales',kind='procedure')).json()
    with lab.transaction():
        entity=notebooks.get(book['id'],'LAB-STAFF')
        entity.attributes.update(title='<script>alert(1)</script>',notes='Original evidence\nSecond line',revision=2)
        entity.attributes['measures'][0].update(manual=0,source='Synthetic recorded period October')
        entity.attributes['checkpoints'][-1].update(days=365,actual='Annual result',evidence='Annual source period')
        notebooks.history(entity)
    url=f"/dealership-lab/notebooks/{book['id']}/export?revision=2"
    first=client.get(url,headers=auth());assert first.status_code==200,first.text
    exported=first.json()
    assert '<script>' not in exported['html'] and '&lt;script&gt;' in exported['html']
    assert 'Original evidence\nSecond line' in exported['html']
    assert '<dt>Manual</dt><dd>0</dd>' in exported['html']
    assert 'Annual result' in exported['html'] and '<dd>365</dd>' in exported['html']
    assert 'Unknown / unavailable' in exported['html']
    with lab.transaction():
        entity=notebooks.get(book['id'],'LAB-STAFF');entity.attributes.update(notes='Later edition',revision=3,edition=2);notebooks.history(entity)
    from core.storage import load_graph
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert client.get(url,headers=auth()).json()==exported
    assert client.get(url,headers=auth('OTHER')).status_code==404
    assert client.get(url.replace('revision=2','revision=999'),headers=auth()).status_code==404

def test_notebook_review_cues_do_not_mutate_saved_evidence_or_expose_other_owner(client):
    from core.dealership_lab import notebooks
    run=saved_comparison(client)
    book=client.post('/dealership-lab/notebooks',headers=auth(),json=dict(run_id=run['id'],department='sales',kind='procedure')).json()
    with lab.transaction():
        entity=notebooks.get(book['id'],'LAB-STAFF');entity.attributes.update(due='2000-01-01',review_due=lab.now().date().isoformat())
    frozen=lab.serial(entity)
    response=client.get('/dealership-lab/notebooks',headers=auth()).json()
    cues=response['review_states'][book['id']]
    assert cues['needs_attention']
    assert any('overdue' in n for n in cues['notices'])
    assert any('due today' in n for n in cues['notices'])
    assert not any('location changed' in n for n in cues['notices'])
    workspace=lab.workspace(book['workspace_id'],'LAB-STAFF')
    with lab.transaction():
        workspace.attributes['sections']['identity']['values']['city']='Changed city'
    response=client.get('/dealership-lab/notebooks',headers=auth()).json()
    assert any('location changed' in n for n in response['review_states'][book['id']]['notices'])
    assert lab.serial(entity)==frozen
    with lab.transaction():workspace.attributes['owner']='OTHER'
    cues=client.get('/dealership-lab/notebooks',headers=auth()).json()['review_states'][book['id']]['notices']
    assert any('unavailable' in n for n in cues)
    assert not any('location changed' in n for n in cues)
    assert book['id'] not in client.get('/dealership-lab/notebooks',headers=auth('OTHER')).json()['review_states']

def test_procedure_lock_names_missing_fields_and_preserves_saved_draft(client):
    run=saved_comparison(client)
    book=client.post('/dealership-lab/notebooks',headers=auth(),json=dict(run_id=run['id'],department='sales',kind='procedure')).json()
    fields={**book,'responsible':'Synthetic lead','reviewer':'Synthetic reviewer','objective':'Synthetic test','steps':'Review authorized report','exceptions':'Escalate missing records','acknowledge':True}
    response=client.put('/dealership-lab/notebooks/'+book['id'],headers=auth(),json=dict(revision=1,action='lock',fields=fields))
    assert response.status_code==422,response.text
    assert response.json()['detail']=='Complete before locking: next review date.'
    from core.dealership_lab import notebooks
    assert lab.serial(notebooks.get(book['id'],'LAB-STAFF'))==book
