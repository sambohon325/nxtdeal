from test_dealership_lab import client, auth, make
import pytest
from copy import deepcopy


def test_historical_copy_isolated_idempotent_and_persisted(client):
    from core.dealeros import ledger
    from core.dealership_lab import service as lab
    from core.storage import load_graph
    source = action(client, make(client), 'path', {'mode': 'hybrid'}).json()
    base = f"/dealership-lab/workspaces/{source['id']}"
    version = client.get(base + '/versions', headers=auth()).json()['versions'][-1]
    current = action(client, source, 'configure', {'city': 'Changed after snapshot'}).json()
    frozen = deepcopy(client.get(base + '/versions', headers=auth()).json())
    url = base + '/versions/' + version['id'] + '/copy'
    body = dict(revision=current['revision'], name='Recovered synthetic plan', request_id='recover-version-test-0001')
    assert client.post(url, headers=auth('OTHER'), json=body).status_code == 404
    assert client.post(url, headers=auth(), json={**body, 'revision':1}).status_code == 409
    saved = client.post(url, headers=auth(), json=body)
    assert saved.status_code == 200, saved.text
    copy = saved.json()
    assert copy['id'] != source['id'] and copy['revision'] == 1
    assert copy['model_definition'] == version['model_definition']
    assert copy['setup_managed'] is True
    assert copy['recovered_from']['revision'] == source['revision']
    assert client.post(url, headers=auth(), json=body).json()['id'] == copy['id']
    assert client.post(url, headers=auth(), json={**body, 'name':'Different'}).status_code == 409
    assert client.get(base + '/versions', headers=auth()).json() == frozen
    assert client.get(base + '/setup', headers=auth()).json()['workspace'] == current
    other = make(client)
    wrong = f"/dealership-lab/workspaces/{other['id']}/versions/{version['id']}/copy"
    assert client.post(wrong, headers=auth(), json={**body, 'revision':1, 'request_id':'recover-wrong-owner-0001'}).status_code == 404
    archived = client.post(base + '/archive', headers=auth(), json={'revision':current['revision']}).json()
    assert client.post(url, headers=auth(), json={**body,'revision':archived['revision'],'request_id':'recover-archived-test-0001'}).status_code == 200
    ledger.reset(); load_graph(lab.GRAPH_PATH)
    assert lab.serial(lab.workspace(copy['id'], 'LAB-STAFF')) == copy


def action(client, workspace, kind, values):
    return client.post(f"/dealership-lab/workspaces/{workspace['id']}/setup", headers=auth(),
                       json=dict(revision=workspace['revision'], action=kind, values=values))


def test_setup_paths_review_staleness_and_isolation(client):
    workspace = make(client)
    url = f"/dealership-lab/workspaces/{workspace['id']}/setup"
    assert client.get(url, headers=auth('OTHER')).status_code == 404
    assert client.post(url, headers=auth('OTHER'), json=dict(revision=1, action='path', values={'mode': 'real'})).status_code == 404
    result = action(client, workspace, 'path', {'mode': 'real'})
    assert result.status_code == 200, result.text
    real = result.json()
    assert action(client, workspace, 'path', {'mode': 'hybrid'}).status_code == 409
    assert client.get(url, headers=auth()).json()['baseline_ready'] is False
    assert action(client, real, 'baseline_review', {'note': 'Synthetic automated test source period', 'confirmed': False}).status_code == 422
    reviewed = action(client, real, 'baseline_review', {'note': 'Synthetic automated test source period', 'confirmed': True}).json()
    assert client.get(url, headers=auth()).json()['baseline_ready'] is True
    # Recorded source lineage must not be erased by switching mode.
    assert action(client, reviewed, 'path', {'mode': 'simulation'}).status_code == 422
    changed = action(client, reviewed, 'configure', {'city': 'Synthetic changed location'})
    assert changed.status_code == 200, changed.text
    assert client.get(url, headers=auth()).json()['baseline_ready'] is False
    # Versions preserve the review and original configuration.
    versions = client.get(url.replace('/setup', '/versions'), headers=auth()).json()
    assert len(versions['versions']) >= 4


def test_setup_preset_requires_explicit_reset_and_finish_requires_steps(client):
    workspace = make(client)
    state = client.get(f"/dealership-lab/workspaces/{workspace['id']}/setup", headers=auth()).json()
    assert len(state['kinds']) == 5
    assert action(client, workspace, 'configure', {'size': 'large'}).status_code == 422
    response = action(client, workspace, 'configure', {'size': 'large', 'reset_confirmed': True})
    assert response.status_code == 200, response.text
    workspace = response.json()
    assert workspace['model_definition']['dealership']['size'] == 'large'
    assert action(client, workspace, 'step', {'step': 'finish'}).status_code == 422
    workspace = action(client, workspace, 'path', {'mode': 'hybrid'}).json()
    for step in ('path', 'identity', 'operations', 'data', 'review'):
        response = action(client, workspace, 'step', {'step': step})
        assert response.status_code == 200, response.text
        workspace = response.json()
    finished = action(client, workspace, 'step', {'step': 'finish'})
    assert finished.status_code == 200, finished.text
    assert finished.json()['model_definition']['workflow']['setup_complete'] is True


def test_full_setup_runs_without_fabricating_compact_reviews(client):
    source = action(client, make(client), 'path', {'mode': 'hybrid'}).json()
    assert not any(s['reviewed_hash'] for s in source['sections'].values())
    option = client.post(f"/dealership-lab/workspaces/{source['id']}/decisions", headers=auth(), json=dict(
        revision=source['revision'], name='Synthetic monthly expense', decision='cost',
        values={'monthly_cost': 1000}, implementation_cost=0)).json()
    body = dict(baseline_id=source['id'], proposed_id=option['id'], baseline_revision=source['revision'],
                proposed_revision=option['revision'], months=2, request_id='full-model-review-0001')
    assert client.post('/dealership-lab/runs', headers=auth(), json=body).status_code == 422
    def loaded(w):
        return client.get(f"/dealership-lab/workspaces/{w['id']}/model", headers=auth()).json()
    hashes = dict(baseline=loaded(source)['input_hash'], proposed=loaded(option)['input_hash'])
    assert client.post('/dealership-lab/runs', headers=auth(), json={**body, 'reviewed_inputs': {**hashes, 'proposed': 'wrong'}}).status_code == 422
    result = client.post('/dealership-lab/runs', headers=auth(), json={**body, 'reviewed_inputs': hashes})
    assert result.status_code == 200, result.text
    assert result.json()['payload']['difference']['profit']['median'][-1] == pytest.approx(-2000)
    assert result.json()['intent']['reviewed_inputs'] == hashes
    # A newer revision must be reviewed again even if the browser retained old inputs.
    changed = loaded(option)['input']
    changed['scenario']['operating']['expenses'][0]['rate'] += 100
    response = client.put(f"/dealership-lab/workspaces/{option['id']}/model", headers=auth(),
                          json=dict(revision=option['revision'], definition=changed))
    assert response.status_code == 200, response.text
    retry = {**body, 'proposed_revision': response.json()['revision'], 'request_id': 'full-model-review-0002', 'reviewed_inputs': hashes}
    assert client.post('/dealership-lab/runs', headers=auth(), json=retry).status_code == 422
    fork = make(client, source=source['id'])
    assert fork['setup_managed'] is True
    assert loaded(source)['input_hash'] == hashes['baseline']


def test_operating_edits_preserve_source_and_history_and_change_costs(client):
    source = action(client, make(client), 'path', {'mode': 'real'}).json()
    source = action(client, source, 'baseline_review', {'note': 'Synthetic payroll and occupancy records', 'confirmed': True}).json()
    original = deepcopy(source['model_definition'])
    values = dict(operating=deepcopy(original['scenario']['operating']), operating_enabled=True, staffing_capacity_enabled=False)
    values['operating']['expenses'][0]['rate'] += 100
    changed = action(client, source, 'operating', values)
    assert changed.status_code == 200, changed.text
    source = changed.json()
    model = source['model_definition']
    assert model['baseline']['operating'] == model['scenario']['operating']
    assert model['workflow']['review'] == original['workflow']['review']  # historical declaration preserved, now stale
    assert client.get(f"/dealership-lab/workspaces/{source['id']}/setup", headers=auth()).json()['baseline_ready'] is False
    source = action(client, source, 'path', {'mode': 'hybrid'}).json()
    option = make(client, source=source['id'])
    before = deepcopy(option['model_definition'])
    values['operating']['expenses'].append(dict(name='Synthetic group bill', quantity=1, rate=700, scope='group'))
    response = action(client, option, 'operating', values)
    assert response.status_code == 200, response.text
    option = response.json()
    assert option['model_definition']['baseline'] == before['baseline']
    assert client.get(f"/dealership-lab/workspaces/{source['id']}/setup", headers=auth()).json()['input'] == source['model_definition']
    hashes = {side: client.get(f"/dealership-lab/workspaces/{w['id']}/model", headers=auth()).json()['input_hash'] for side,w in [('baseline',source),('proposed',option)]}
    result = client.post('/dealership-lab/runs', headers=auth(), json=dict(baseline_id=source['id'], proposed_id=option['id'], baseline_revision=source['revision'], proposed_revision=option['revision'], months=2, request_id='operating-cost-test-001', reviewed_inputs=hashes))
    assert result.status_code == 200, result.text
    assert result.json()['payload']['difference']['profit']['median'][-1] == pytest.approx(-1400)
    bad = deepcopy(values)
    bad['operating']['tasks'][0]['role'] = 'missing-role'
    assert action(client, option, 'operating', bad).status_code == 422
    bad = {**values, 'operating_enabled': 1}
    assert action(client, option, 'operating', bad).status_code == 422
    assert action(client, {**option, 'revision': option['revision']-1}, 'operating', values).status_code == 409
    assert client.post(f"/dealership-lab/workspaces/{option['id']}/setup", headers=auth('OTHER'), json=dict(revision=option['revision'], action='operating', values=values)).status_code == 404

@pytest.mark.parametrize('country,region', [('United States', 'Texas'), ('Canada', 'Ontario')])
def test_operating_preview_is_readonly_and_matches_saved_draft(client, country, region):
    source = action(client, make(client), 'configure', {'country': country, 'region': region, 'rooftops': 2}).json()
    model = source['model_definition']
    values = dict(operating=deepcopy(model['scenario']['operating']), operating_enabled=True, staffing_capacity_enabled=False)
    values['operating']['expenses'].append(dict(name='Group preview bill', quantity=1, rate=800, scope='group'))
    values['operating']['roles'][0].update(salary=6000, people=1, shifts=1, burden=20, commission=0, embedded=0, scope='group')
    url = f"/dealership-lab/workspaces/{source['id']}/operating-preview"
    body = dict(revision=source['revision'], values=values)
    response = client.post(url, headers=auth(), json=body)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview['draft']['overhead'] - preview['saved']['overhead'] == pytest.approx(400)
    assert preview['draft']['roles'][0]['payroll'] == pytest.approx(3600)
    from chrono.shared.dealership.model import simulate_one
    expected = deepcopy(model)
    expected['scenario']['operating'] = deepcopy(values['operating'])
    expected['baseline']['operating'] = deepcopy(values['operating'])
    expected.update(months=1, operating_enabled=True, staffing_capacity_enabled=False)
    assert preview['draft'] == simulate_one(expected, 'scenario', 0)[0]['_work']
    assert preview['rooftops'] == 2
    assert 'per rooftop' in preview['basis']
    assert client.get(url.replace('/operating-preview','/setup'), headers=auth()).json()['workspace'] == source
    assert client.post(url, headers=auth('OTHER'), json=body).status_code == 404
    saved = action(client, source, 'operating', values).json()
    assert client.post(url, headers=auth(), json=body).status_code == 409
    repeated = client.post(url, headers=auth(), json={**body, 'revision': saved['revision']}).json()
    assert repeated['saved'] == preview['draft']
    assert repeated['draft'] == preview['draft']


def test_job_removal_cleans_option_software_only_and_role_references_reject(client):
    from core.dealership_lab import analysis
    source = action(client, make(client), 'path', {'mode':'hybrid'}).json()
    model = deepcopy(source['model_definition'])
    module = analysis.software('custom')
    task = model['scenario']['operating']['tasks'][0]
    module['task_savings'] = {task['id']: 15}
    for side in ('baseline','scenario'):
        model[side]['software'] = [deepcopy(module)]
    response = client.put(f"/dealership-lab/workspaces/{source['id']}/model", headers=auth(), json=dict(revision=source['revision'],definition=model))
    assert response.status_code == 200, response.text
    source = response.json()
    option = make(client, source=source['id'])
    op = deepcopy(option['model_definition']['scenario']['operating'])
    values = dict(operating=op, operating_enabled=True, staffing_capacity_enabled=False)
    invalid = deepcopy(values)
    invalid['operating']['roles'] = [r for r in op['roles'] if r['id'] != task['role']]
    assert action(client, option, 'operating', invalid).status_code == 422
    op['tasks'] = [t for t in op['tasks'] if t['id'] != task['id']]
    result = action(client, option, 'operating', values)
    assert result.status_code == 200, result.text
    edited = result.json()['model_definition']
    assert edited['scenario']['software'][0]['task_savings'] == {}
    assert edited['baseline']['software'][0]['task_savings'] == {task['id']:15}
    assert client.get(f"/dealership-lab/workspaces/{source['id']}/setup", headers=auth()).json()['input'] == source['model_definition']

@pytest.mark.parametrize('kind', range(5))
def test_customer_inventory_model_paths_all_types(client, kind):
    from chrono.shared.dealership.configuration import KINDS, USED_ONLY
    from chrono.shared.dealership.model import simulate_one
    source = action(client, make(client), 'configure', {'kind':KINDS[kind], 'reset_confirmed':True, 'rooftops':2}).json()
    state = client.get(f"/dealership-lab/workspaces/{source['id']}/setup", headers=auth()).json()
    model = state['input']
    values = dict(profile={f[0]:model['profile'][f[0]] for f in state['customer_fields']}, segments=deepcopy(model['segments']))
    values['profile'].update(organic_leads=1000, response_rate=100, appointment_rate=100, show_rate=100, close_rate=100, lead_capacity=10000, sales_capacity=10000, new_share=0, seasonality=0, demand_volatility=0)
    values['segments']['new'].update(inventory=0,replenishment=0)
    values['segments']['used'].update(inventory=10,replenishment=0,price=25000,gross=3000,fi=500,holding=0)
    option = make(client, source=source['id'])
    response = action(client, option, 'customers', values)
    assert response.status_code == 200, response.text
    saved = response.json()
    executed = deepcopy(saved['model_definition'])
    executed['months']=1
    row=simulate_one(executed,'scenario',0)[0]
    assert row['sales'] == 20  # ten vehicles per rooftop, two rooftops
    assert row['used_revenue'] == 500000
    assert row['gross'] == 60000
    assert row['fi_gross'] == 10000
    assert executed['profile']['inventory'] == 10
    assert client.get(f"/dealership-lab/workspaces/{source['id']}/setup",headers=auth()).json()['input'] == model
    assert action(client, option, 'customers',values).status_code == 409
    bad=deepcopy(values);bad['segments']['used']['gross']=26000
    assert action(client,saved,'customers',bad).status_code == 422
    bad=deepcopy(values);bad['profile']['country']='Canada'
    assert action(client,saved,'customers',bad).status_code == 422
    if KINDS[kind] in USED_ONLY:
        bad=deepcopy(values);bad['segments']['new']['inventory']=1
        assert action(client,saved,'customers',bad).status_code == 422
    from core.dealeros import ledger
    from core.storage import load_graph
    from core.dealership_lab import service as lab
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert client.get(f"/dealership-lab/workspaces/{saved['id']}/setup",headers=auth()).json()['input'] == saved['model_definition']

def test_customer_changes_invalidate_real_review_and_reject_other_owner(client):
    source = action(client, make(client), 'path', {'mode':'real'}).json()
    source = action(client, source, 'baseline_review', {'note':'Synthetic inventory and lead report period','confirmed':True}).json()
    url=f"/dealership-lab/workspaces/{source['id']}/setup"
    state=client.get(url,headers=auth()).json()
    values=dict(profile={f[0]:state['input']['profile'][f[0]] for f in state['customer_fields']},segments=deepcopy(state['input']['segments']))
    values['profile']['organic_leads']+=1
    assert client.post(url,headers=auth('OTHER'),json=dict(revision=source['revision'],action='customers',values=values)).status_code==404
    changed=action(client,source,'customers',values)
    assert changed.status_code==200,changed.text
    assert client.get(url,headers=auth()).json()['baseline_ready'] is False
    assert changed.json()['model_definition']['workflow']['review']==source['model_definition']['workflow']['review']

def financial_values(client,w):
    state=client.get(f"/dealership-lab/workspaces/{w['id']}/setup",headers=auth()).json()
    return {'assumptions':{f[0]:state['input']['finance']['scenario'][f[0]] for f in state['finance_fields']}}


def test_finance_group_profit_cash_and_isolation(client):
    source=action(client,make(client),'configure',{'rooftops':3}).json()
    values=financial_values(client,source)
    assert len(values['assumptions'])==7
    values['assumptions']['tax_rate']=0
    source=action(client,source,'finance',values).json()
    assert source['model_definition']['finance']['baseline']==source['model_definition']['finance']['scenario']
    option=make(client,source=source['id'])
    values['assumptions']['depreciation']+=1000
    values['assumptions']['capex']+=2000
    edited=action(client,option,'finance',values)
    assert edited.status_code==200,edited.text
    option=edited.json()
    assert option['model_definition']['finance']['baseline']==source['model_definition']['finance']['baseline']
    hashes={side:client.get(f"/dealership-lab/workspaces/{w['id']}/model",headers=auth()).json()['input_hash'] for side,w in [('baseline',source),('proposed',option)]}
    run=client.post('/dealership-lab/runs',headers=auth(),json=dict(baseline_id=source['id'],proposed_id=option['id'],baseline_revision=source['revision'],proposed_revision=option['revision'],months=2,request_id='finance-profit-cash-001',reviewed_inputs=hashes))
    assert run.status_code==200,run.text
    assert run.json()['payload']['difference']['profit']['median'][-1]==pytest.approx(-2000)
    assert run.json()['payload']['difference']['cash']['median'][-1]==pytest.approx(-4000)
    assert client.get(f"/dealership-lab/workspaces/{source['id']}/setup",headers=auth()).json()['input']==source['model_definition']
    assert action(client,{**option,'revision':option['revision']-1},'finance',values).status_code==409
    values['assumptions']['apr']=10
    assert action(client,option,'finance',values).status_code==422
    assert client.post(f"/dealership-lab/workspaces/{option['id']}/setup",headers=auth('OTHER'),json=dict(revision=option['revision'],action='finance',values=values)).status_code==404


def test_bhph_finance_completeness_and_collections(client):
    from chrono.shared.dealership import earnings
    from chrono.shared.dealership.configuration import KINDS
    from chrono.shared.dealership.model import simulate_one
    source=action(client,make(client),'configure',{'kind':KINDS[3],'reset_confirmed':True,'rooftops':2}).json()
    values=financial_values(client,source)
    assert set(values['assumptions'])==set(earnings.DEFAULTS)
    values['assumptions'].update(opening_receivables=12000,existing_term=12,apr=0,monthly_default=0,collection_rate=100,funding_apr=0,financed_share=0)
    result=action(client,source,'finance',values)
    assert result.status_code==200,result.text
    model=result.json()['model_definition'];model['months']=2
    cash=earnings.cashflow(simulate_one(model,'scenario',0),model,'scenario')
    assert [r['principal_collections'] for r in cash]==[1000,1000]
    assert cash[-1]['receivables']==10000
    assert cash[-1]['originations']==0
    values['assumptions']['term']=12.5
    assert action(client,result.json(),'finance',values).status_code==422

def test_financial_source_review_and_reload(client):
    from core.dealeros import ledger
    from core.storage import load_graph
    from core.dealership_lab import service as lab
    w=action(client,make(client),'path',{'mode':'real'}).json()
    w=action(client,w,'baseline_review',{'confirmed':True,'note':'Synthetic monthly balance sheet and cash records'}).json()
    values=financial_values(client,w);values['assumptions']['opening_cash']=12345.67
    response=action(client,w,'finance',values)
    assert response.status_code==200,response.text
    saved=response.json()
    assert saved['model_definition']['workflow']['review']==w['model_definition']['workflow']['review']
    ledger.reset();load_graph(lab.GRAPH_PATH)
    state=client.get(f"/dealership-lab/workspaces/{saved['id']}/setup",headers=auth()).json()
    assert state['input']==saved['model_definition']
    assert state['baseline_ready'] is False

def test_campaign_budget_blend_and_advertising_decision_remain_effective(client):
    from chrono.shared.dealership.model import simulate_one
    source=make(client)
    values=dict(campaigns=[dict(name='Synthetic search',budget=2000,cpl=50),dict(name='Synthetic listings',budget=1000,cpl=100)],saturation_budget=60000)
    response=action(client,source,'campaigns',values)
    assert response.status_code==200,response.text
    source=response.json();model=source['model_definition']
    assert model['scenario']['spend']==3000
    assert model['scenario']['cpl']==60
    assert model['baseline']['campaigns']==model['scenario']['campaigns']
    response=client.post(f"/dealership-lab/workspaces/{source['id']}/decisions",headers=auth(),json=dict(revision=source['revision'],name='Synthetic larger budget',decision='advertising',values=dict(spend=5000,paid_efficiency_lift=0),implementation_cost=0))
    assert response.status_code==200,response.text
    option=response.json();draft=option['model_definition']
    assert draft['scenario']['spend']==5000
    assert draft['scenario']['cpl']==60
    assert draft['baseline']['campaigns']==model['scenario']['campaigns']
    draft['months']=1
    assert simulate_one(draft,'scenario',0)[0]['marketing_cost']==5000*draft['rooftops']
    assert client.get(f"/dealership-lab/workspaces/{source['id']}/setup",headers=auth()).json()['input']==model
    empty=action(client,option,'campaigns',dict(campaigns=[],saturation_budget=60000))
    assert empty.status_code==200,empty.text
    assert empty.json()['model_definition']['scenario']['spend']==0
    assert empty.json()['model_definition']['baseline']['campaigns']==model['baseline']['campaigns']
    assert action(client,option,'campaigns',values).status_code==409
    bad=dict(campaigns=[dict(name='Bad',budget=1,cpl=0)],saturation_budget=60000)
    assert action(client,empty.json(),'campaigns',bad).status_code==422
    bad=dict(campaigns=[dict(name='Too much',budget=600000,cpl=50)]*2,saturation_budget=60000)
    assert action(client,empty.json(),'campaigns',bad).status_code==422


def test_real_campaign_sources_and_record_isolation(client):
    source=action(client,make(client),'path',{'mode':'real'}).json()
    values=dict(campaigns=[dict(name='Synthetic records',budget=1000,cpl=40)],saturation_budget=60000)
    source=action(client,source,'campaigns',values).json()
    source=action(client,source,'baseline_review',dict(confirmed=True,note='Synthetic paid media totals for September')).json()
    response=client.post(f"/dealership-lab/workspaces/{source['id']}/decisions",headers=auth(),json=dict(revision=source['revision'],name='Real-source option',decision='advertising',values=dict(spend=2000,paid_efficiency_lift=0),implementation_cost=0))
    assert response.status_code==200,response.text
    assert response.json()['model_definition']['scenario']['spend']==2000
    option=response.json()
    nested=client.post(f"/dealership-lab/workspaces/{option['id']}/decisions",headers=auth(),json=dict(revision=option['revision'],name='Unreviewed changed source',decision='advertising',values=dict(spend=3000,paid_efficiency_lift=0),implementation_cost=0))
    assert nested.status_code==422  # changed source economics still require review
    url=f"/dealership-lab/workspaces/{source['id']}/setup"
    assert client.post(url,headers=auth('OTHER'),json=dict(revision=source['revision'],action='campaigns',values=values)).status_code==404
    values['campaigns'][0]['budget']=1500
    changed=action(client,source,'campaigns',values)
    assert changed.status_code==200,changed.text
    assert client.get(url,headers=auth()).json()['baseline_ready'] is False

def test_software_catalog_estimates_group_costs_and_isolation(client):
    from chrono.shared.dealership import catalogue
    source=action(client,make(client),'configure',{'rooftops':3}).json()
    catalog=client.get('/dealership-lab/software-catalog',headers=auth()).json()
    assert len(catalog['products'])==len(catalogue.CATALOG)
    product=next(p for p in catalogue.CATALOG if 'estimates' in p)
    preview=client.post('/dealership-lab/software-estimate',headers=auth(),json=dict(vendor=product['id'],case='cautious'))
    assert preview.status_code==200,preview.text
    assert preview.json()==catalogue.estimated_module(product['id'],'cautious')
    assert client.post('/dealership-lab/software-estimate',headers=auth(),json=dict(vendor='missing',case='working')).status_code==422
    assert client.get(f"/dealership-lab/workspaces/{source['id']}/setup",headers=auth()).json()['workspace']==source
    option=make(client,source=source['id'])
    module=catalog['templates']['custom'];module.update(monthly_cost=1000,setup_cost=500,cost_scope='group',adoption=0)
    result=action(client,option,'software',dict(modules=[module]))
    assert result.status_code==200,result.text
    option=result.json()
    assert option['model_definition']['baseline']['software']==source['model_definition']['baseline']['software']
    hashes={side:client.get(f"/dealership-lab/workspaces/{w['id']}/model",headers=auth()).json()['input_hash'] for side,w in [('baseline',source),('proposed',option)]}
    run=client.post('/dealership-lab/runs',headers=auth(),json=dict(baseline_id=source['id'],proposed_id=option['id'],baseline_revision=source['revision'],proposed_revision=option['revision'],months=2,request_id='software-group-cost-001',reviewed_inputs=hashes))
    assert run.status_code==200,run.text
    assert run.json()['payload']['difference']['profit']['median'][-1]==pytest.approx(-2500)
    assert client.get(f"/dealership-lab/workspaces/{source['id']}/setup",headers=auth()).json()['workspace']==source
    assert action(client,option,'software',dict(modules=[module]*13)).status_code==422
    bad=deepcopy(module);bad['task_savings']={'followup':101}
    assert action(client,option,'software',dict(modules=[bad])).status_code==422
    disabled=deepcopy(module);disabled['enabled']=False
    result=action(client,option,'software',dict(modules=[disabled]))
    assert result.status_code==200,result.text
    from chrono.shared.dealership.model import simulate_one
    assert simulate_one(result.json()['model_definition'],'scenario',0)[0]['software_cost']==0
    assert client.post(f"/dealership-lab/workspaces/{source['id']}/setup",headers=auth('OTHER'),json=dict(revision=source['revision'],action='software',values=dict(modules=[]))).status_code==404

def test_decision_retry_deduplication_and_nested_request_isolation(client):
    from core.dealeros import ledger
    from core.dealership_lab import service as lab
    from core.storage import load_graph
    source = action(client, make(client), 'path', {'mode':'hybrid'}).json()
    url = f"/dealership-lab/workspaces/{source['id']}/decisions"
    body = dict(revision=source['revision'],name='Synthetic expense',decision='cost',values={'monthly_cost':1000},request_id='decision-retry-test-0001')
    response = client.post(url,headers=auth(),json=body)
    assert response.status_code == 200, response.text
    option = response.json()
    assert client.post(url,headers=auth(),json=body).json()['id'] == option['id']
    assert client.post(url,headers=auth(),json={**body,'values':{'monthly_cost':2000}}).status_code == 409
    assert client.post(url,headers=auth('OTHER'),json=body).status_code == 404
    nested_url = f"/dealership-lab/workspaces/{option['id']}/decisions"
    nested_body = {**body,'revision':1,'request_id':'decision-retry-test-0002'}
    nested = client.post(nested_url,headers=auth(),json=nested_body)
    assert nested.status_code == 200, nested.text
    assert nested.json()['parent_id'] == option['id']
    assert nested.json()['decision_intent']['source_id'] == option['id']
    # A retry still resolves its original option after the source changes.
    current = action(client,source,'configure',{'city':'Changed after request'}).json()
    assert current['revision'] > source['revision']
    assert client.post(url,headers=auth(),json=body).json()['id'] == option['id']
    assert client.post(url,headers=auth(),json={**body,'request_id':'decision-stale-test-0003'}).status_code == 409
    ledger.reset(); load_graph(lab.GRAPH_PATH)
    assert client.post(url,headers=auth(),json=body).json()['id'] == option['id']
    assert len([w for w in lab.items(lab.WORKSPACE) if w.attributes.get('decision_request_id')==body['request_id']]) == 1

def test_real_option_chain_requires_explicit_hybrid_without_recertifying_models(client):
    from core.dealership_lab import service as lab
    from core.dealeros import ledger
    from core.storage import load_graph
    source=action(client,make(client),'path',{'mode':'real'}).json()
    source=action(client,source,'baseline_review',{'note':'Synthetic September records for chain test','confirmed':True}).json()
    def decision(w,name,**extra):
        return client.post(f"/dealership-lab/workspaces/{w['id']}/decisions",headers=auth(),json=dict(revision=w['revision'],name=name,decision='cost',values={'monthly_cost':100},implementation_cost=0,**extra))
    first=decision(source,'First modeled expense').json()
    original=deepcopy(first)
    model=client.get(f"/dealership-lab/workspaces/{first['id']}/model",headers=auth()).json()
    assert model['decision_requires_hybrid'] is True
    assert decision(first,'Second modeled expense').status_code==422
    response=decision(first,'Second modeled expense',acknowledge_hybrid=True,request_id='hybrid-chain-00000001')
    assert response.status_code==200,response.text
    second=response.json()
    assert second['parent_id']==first['id']
    assert second['model_definition']['workflow']['mode']=='hybrid'
    assert second['model_definition']['workflow']['review']==source['model_definition']['workflow']['review']
    assert second['model_definition']['baseline']['operating']==first['model_definition']['scenario']['operating']
    assert len(second['model_definition']['scenario']['operating']['expenses'])==len(first['model_definition']['scenario']['operating']['expenses'])+1
    assert decision(first,'Second modeled expense',acknowledge_hybrid=True,request_id='hybrid-chain-00000001').json()['id']==second['id']
    assert decision(first,'Second modeled expense',request_id='hybrid-chain-00000001').status_code==409
    hashes={side:client.get(f"/dealership-lab/workspaces/{w['id']}/model",headers=auth()).json()['input_hash'] for side,w in [('baseline',first),('proposed',second)]}
    run=client.post('/dealership-lab/runs',headers=auth(),json=dict(baseline_id=first['id'],proposed_id=second['id'],baseline_revision=first['revision'],proposed_revision=second['revision'],months=2,request_id='hybrid-chain-run-00001',reviewed_inputs=hashes))
    assert run.status_code==200,run.text
    assert run.json()['payload']['difference']['profit']['median'][-1]==pytest.approx(-200)
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert lab.serial(lab.workspace(first['id'],'LAB-STAFF'))==original
    assert lab.serial(lab.workspace(source['id'],'LAB-STAFF'))==source
    changed=action(client,source,'configure',{'city':'Changed source location'}).json()
    assert decision(changed,'Cannot bypass stale actuals',acknowledge_hybrid=True).status_code==422
