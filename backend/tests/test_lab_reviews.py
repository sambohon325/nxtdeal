from datetime import date
from test_dealership_lab import client,auth,make
from test_lab_setup import action
from core.dealership_lab import reviews,service as lab

def test_closed_review_period_year_boundaries():
    assert reviews.closed_periods(date(2026,1,2))==[('monthly','2025-12',['2025-12']),('quarterly','2025-Q4',['2025-10','2025-11','2025-12'])]


def test_report_correction_requires_fresh_review_and_preserves_published_lineage(client):
    from core.dealeros import ledger
    from core.storage import load_graph
    source=action(client,make(client),'path',{'mode':'hybrid'}).json()
    base=f"/dealership-lab/workspaces/{source['id']}"
    month=reviews.closed_periods(lab.now().date())[0][2][0]

    def import_value(revision,value):
        body=dict(revision=revision,workspace_revision=source['revision'],
                  csv=f'month,rooftop,currency,leads\n{month},A,USD,{value}\n',
                  source=f'Synthetic closed-period correction {revision}; not production data')
        preview=client.post(base+'/reports/preview',headers=auth(),json=body)
        assert preview.status_code==200,preview.text
        saved=client.post(base+'/reports/import',headers=auth(),json=dict(
            **body,token=preview.json()['token'],acknowledge=True,
            request_id=f'review-correction-{revision:04d}'))
        assert saved.status_code==200,saved.text
        return saved.json()

    first=import_value(0,100)
    prepare=dict(revision=source['revision'],report_revision=1)
    assert client.post(base+'/period-reviews/prepare',headers=auth(role='ADMIN'),json=prepare).status_code==200
    record=next(r for r in reviews.listing(source['id'],'LAB-STAFF',True)['reviews'] if r['cadence']=='monthly')
    url='/dealership-lab/period-reviews/'+record['id']
    publish=dict(revision=record['revision'],action='publish',reviewed=True,
                 notes='Reviewed corrected source figures, period and rooftop coverage.')
    second=import_value(1,120)
    assert client.put(url,headers=auth(role='ADMIN'),json=publish).status_code==409
    assert client.post(base+'/period-reviews/prepare',headers=auth(role='ADMIN'),json={**prepare,'report_revision':2}).status_code==200
    publish['revision']+=1
    assert client.put(url,headers=auth(),json=publish).status_code==403
    published=client.put(url,headers=auth(role='ADMIN'),json=publish)
    assert published.status_code==200,published.text
    frozen=published.json()
    cell=frozen['snapshot']['rows'][0]
    assert cell['values']=={'leads':120}
    assert cell['sources']['leads']['import_id']==second['id']
    import_value(2,130)
    assert client.post(base+'/period-reviews/prepare',headers=auth(role='ADMIN'),json={**prepare,'report_revision':3}).status_code==200
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert lab.serial(ledger.get_entity(record['id']))==frozen
    history=client.get(url+'/history',headers=auth(role='ADMIN')).json()['versions']
    assert history[0]['snapshot']['rows'][0]['values']['leads']==100
    assert history[0]['snapshot']['rows'][0]['sources']['leads']['import_id']==first['id']
    assert history[-1]['snapshot']==frozen['snapshot']
    assert client.get(base+'/period-reviews',headers=auth('OTHER',role='ADMIN')).status_code==404

def test_period_reviews_role_scope_freeze_refresh_and_publication(client):
    source=make(client)
    url=f"/dealership-lab/workspaces/{source['id']}/period-reviews"
    body=dict(revision=source['revision'],report_revision=0)
    assert client.post(url+'/prepare',headers=auth(),json=body).status_code==403
    assert client.post(url+'/prepare',headers=auth(role='ADMIN'),json=body).status_code==422
    source=action(client,source,'path',{'mode':'hybrid'}).json();body['revision']=source['revision']
    first=client.post(url+'/prepare',headers=auth(role='ADMIN'),json=body)
    assert first.status_code==200,first.text
    assert len(first.json()['changed'])==2
    assert client.post(url+'/prepare',headers=auth(role='ADMIN'),json=body).json()['changed']==[]
    items=client.get(url,headers=auth(role='ADMIN')).json()['reviews']
    record=items[0];assert record['snapshot']['rows']==[]
    assert any('Data-readiness' in g for g in record['snapshot']['gaps'])
    assert client.get(url,headers=auth()).json()['reviews']==[]
    assert client.get(url,headers=auth('OTHER',role='ADMIN')).status_code==404
    update='/dealership-lab/period-reviews/'+record['id']
    payload=dict(revision=1,action='publish',notes='No imported figures. Controller to provide period data.',reviewed=False)
    assert client.put(update,headers=auth(role='ADMIN'),json=payload).status_code==422
    source=action(client,source,'configure',{'city':'Updated source'}).json()
    payload['reviewed']=True
    assert client.put(update,headers=auth(role='ADMIN'),json=payload).status_code==409
    refreshed=client.post(url+'/prepare',headers=auth(role='ADMIN'),json=dict(revision=source['revision'],report_revision=0))
    assert len(refreshed.json()['changed'])==2
    payload['revision']=2
    published=client.put(update,headers=auth(role='ADMIN'),json=payload)
    assert published.status_code==200,published.text
    frozen=published.json()
    assert len(client.get(url,headers=auth()).json()['reviews'])==1
    assert client.put(update,headers=auth(role='ADMIN'),json=payload).status_code==409
    from core.dealeros import ledger
    from core.storage import load_graph
    ledger.reset();load_graph(lab.GRAPH_PATH)
    assert lab.serial(ledger.get_entity(record['id']))==frozen
    assert len([r for r in lab.items(reviews.HISTORY) if r.attributes['review_id']==record['id']])==3

def test_review_uses_reported_cells_and_retains_per_month_balances(client):
    from core.dealership_lab import reports
    source=action(client,make(client),'path',{'mode':'hybrid'}).json()
    months=reviews.closed_periods(lab.now().date())[1][2]
    with lab.transaction():
        lab.create('LABD',reports.DATA,dict(owner='LAB-STAFF',workspace_id=source['id'],revision=1,rows=[dict(month=m,rooftop='A',currency='USD',values={'inventory_units':n},sources={'inventory_units':{'source':'Synthetic report fixture','import_id':'fixture'}}) for m,n in zip(months[:2],[70,50])]))
    reviews.prepare(source['id'],'LAB-STAFF',source['revision'],1)
    quarterly=next(r for r in reviews.listing(source['id'],'LAB-STAFF',True)['reviews'] if r['cadence']=='quarterly')
    assert [r['values']['inventory_units'] for r in quarterly['snapshot']['rows']]==[70,50]
    assert any(months[2] in gap for gap in quarterly['snapshot']['gaps'])
    assert all(set(r['values'])=={'inventory_units'} for r in quarterly['snapshot']['rows'])
    assert quarterly['snapshot']['rows'][0]['sources']['inventory_units']['import_id']=='fixture'

def test_review_history_requires_manager_and_preserves_prior_assessments(client):
    source=action(client,make(client),'path',{'mode':'hybrid'}).json()
    reviews.prepare(source['id'],'LAB-STAFF',source['revision'],0)
    record=reviews.listing(source['id'],'LAB-STAFF',True)['reviews'][0]
    reviews.update(record['id'],'LAB-STAFF',1,'save','Draft assessment from reported evidence.',False)
    reviews.update(record['id'],'LAB-STAFF',2,'publish','Final assessment with recorded gaps and next steps.',True)
    url=f"/dealership-lab/period-reviews/{record['id']}/history"
    assert client.get(url,headers=auth()).status_code==403
    assert client.get(url,headers=auth('OTHER',role='ADMIN')).status_code==404
    result=client.get(url,headers=auth(role='ADMIN'))
    assert result.status_code==200,result.text
    versions=result.json()['versions']
    assert [r['revision'] for r in versions]==[1,2,3]
    assert versions[0]['notes']==''
    assert versions[1]['notes']=='Draft assessment from reported evidence.'
    assert versions[2]['status']=='published'
    assert versions[0]['snapshot']==versions[2]['snapshot']
