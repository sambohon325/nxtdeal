"""Synthetic multi-rooftop BHPH journey through real API persistence boundaries."""
import json
from copy import deepcopy
import pytest
from chrono.shared.dealership import model, configuration
from core.dealership_lab import service as lab
from core.storage import load_graph
from test_dealership_lab import client, auth


def test_import_review_chained_decisions_frozen_finance_and_procedure(client):
    def post(path,body,status=200):
        response=client.post('/dealership-lab'+path,headers=auth(),json=body)
        assert response.status_code==status,response.text
        return response.json()
    definition=configuration.configure(model.default_experiment(),dict(
        kind='Buy Here Pay Here (BHPH) / Subprime Lots',size='small',
        country='United States',region='Texas',city='Synthetic QA',rooftops=2),reset=True)
    definition['scenario']=deepcopy(definition['baseline'])
    definition['finance']['scenario']=deepcopy(definition['finance']['baseline'])
    definition['regional']['tax_enabled']=False
    for side in ('baseline','scenario'):
        definition['finance'][side]['tax_rate']=0
    definition['workflow']=dict(mode='real',selected=True)
    p=post('/experiment-import/preview',dict(content=json.dumps({'input':definition})))
    source=post('/experiment-import/save',dict(preview_id=p['preview_id'],name='Synthetic two-roof BHPH'))
    base='/workspaces/'+source['id']
    cost=dict(revision=1,name='Extra occupancy',decision='cost',values={'monthly_cost':1000})
    post(base+'/decisions',cost,422)  # A file cannot certify its own real baseline.
    source=post(base+'/setup',dict(revision=1,action='baseline_review',values=dict(
        confirmed=True,note='Synthetic closed-period records for this automated acceptance test only.')))
    first=post(base+'/decisions',{**cost,'revision':source['revision']})
    second_body=dict(revision=1,name='Second expense',decision='cost',values={'monthly_cost':500})
    post('/workspaces/'+first['id']+'/decisions',second_body,422)
    second=post('/workspaces/'+first['id']+'/decisions',{**second_body,'acknowledge_hybrid':True})
    assert second['parent_id']==first['id']
    assert second['model_definition']['workflow']['mode']=='hybrid'
    assert second['imported_from']==source['imported_from']
    assert 'import_preview_id' not in second
    reviewed={side:client.get('/dealership-lab/workspaces/'+w['id']+'/model',headers=auth()).json()['input_hash']
              for side,w in [('baseline',first),('proposed',second)]}
    run=post('/runs',dict(baseline_id=first['id'],proposed_id=second['id'],
        baseline_revision=1,proposed_revision=1,months=4,seed=42,request_id='import-bhph-journey-0001',reviewed_inputs=reviewed))
    # Added cost is per rooftop per month: 500 * 2 * 4.
    assert run['payload']['difference']['profit']['median'][-1]==pytest.approx(-4000)
    finance_path='/dealership-lab/runs/'+run['id']+'/finance-detail?include_register=true'
    finance=client.get(finance_path,headers=auth())
    assert finance.status_code==200,finance.text
    assert client.get(finance_path,headers=auth('OTHER')).status_code==404
    book=post('/notebooks',dict(run_id=run['id'],department='bhph',kind='procedure'))
    assert all(p['available'] for p in book['projections'])
    assert [p['days'] for p in book['checkpoints']]==[30,60,90,120]
    fields={**book,'responsible':'Synthetic reviewer','reviewer':'Synthetic reviewer',
        'review_due':'2099-01-01','objective':'Inspect synthetic portfolio assumptions',
        'steps':'Reconcile the frozen comparison with the source hypotheses.',
        'exceptions':'Escalate unknown records for review.','acknowledge':True}
    for c in fields['controls']:c.update(status='reviewed',evidence='Synthetic test evidence only.')
    for c in fields['checkpoints']:c.update(action='Inspect results',target='Record sources and unknowns')
    path='/dealership-lab/notebooks/'+book['id']
    locked=client.put(path,headers=auth(),json=dict(revision=1,action='lock',fields=fields))
    assert locked.status_code==200,locked.text
    export_path=path+'/export?revision=2'
    original_export=client.get(export_path,headers=auth()).json()
    assert 'Modeled checkpoint outlook' in original_export['html']
    revised=client.put(path,headers=auth(),json=dict(revision=2,action='revise',fields={}))
    assert revised.status_code==200 and revised.json()['edition']==2
    post('/workspaces/'+second['id']+'/archive',dict(revision=1))
    lab.ledger.reset();load_graph(lab.GRAPH_PATH)
    assert client.get(export_path,headers=auth()).json()==original_export
    assert client.get(finance_path,headers=auth()).json()==finance.json()
    assert lab.serial(lab.workspace(source['id'],'LAB-STAFF'))==source
