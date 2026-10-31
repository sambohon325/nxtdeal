from uuid import uuid4
from test_website_studio import site
from core import websites
from core.website_visits import collect, report
from core.websites_api import get_website_analytics_api
from core.entities import Entity

def event(**kw):return {'id':str(uuid4()),'session':str(uuid4()),'event':'page_view','page':'home','source':'google','device':'mobile',**kw}

def test_public_only_idempotent_persistent_and_scoped(site,monkeypatch):
    saves=[];monkeypatch.setattr(websites,'save_graph',lambda *_:saves.append(True))
    data=event()
    assert 'error' in collect(site.id,data)
    site.attributes['status']='published'
    assert collect(site.id,data)=={'ok':True}
    assert collect(site.id,data)=={'ok':True}
    assert len(saves)==1
    assert report(site.id)['pageviews']==1
    assert report('other')['pageviews']==0
    assert 'error' in get_website_analytics_api('SALES','stranger',site.id)
    assert get_website_analytics_api('SALES','owner',site.id)['traffic']['sessions']==1

def test_schema_bots_sources_and_actual_leads(site):
    site.attributes['status']='published'
    assert 'error' in collect(site.id,event(page='email@example.com'))
    assert 'error' in collect(site.id,event(event='lead'))
    collect(site.id,event(source='https://example.test/?email=private@example.test'))
    collect(site.id,event(),'Googlebot')
    websites.ledger.add_entity(Entity(id='lead-test',entity_type='Lead',attributes={'WebsiteID':site.id,'CreatedAt':websites._now()}))
    result=report(site.id,7)
    assert result['pageviews']==1 and result['bot_events']==1 and result['leads']==1
    assert result['sources']=={'Direct / unknown':1} and len(result['by_day'])==7

def test_failure_rolls_back_and_ga_validation(site,monkeypatch):
    site.attributes['status']='published'
    def fail(*_):raise OSError('synthetic failure')
    monkeypatch.setattr(websites,'save_graph',fail)
    import pytest
    with pytest.raises(OSError):collect(site.id,event())
    assert report(site.id)['pageviews']==0
    assert 'error' in websites.update_admin_settings(site.id,{'google_analytics_id':'<script>'})

def test_goals_count_persisted_inquiry_intents_and_rolling_period(site):
    from datetime import datetime,timedelta,timezone
    goals=[{'metric':'all','target':20,'enabled':True},{'metric':'test_drive','target':5,'enabled':True}]
    websites.update_admin_settings(site.id,{'conversion_goals':goals})
    for key,intent,age in [('recent','test_drive',0),('older','purchase',15),('expired','test_drive',40)]:
        websites.ledger.add_entity(Entity(id=key,entity_type='Lead',attributes={'WebsiteID':site.id,'WebsiteInquiryIntent':intent,'CreatedAt':(datetime.now(timezone.utc)-timedelta(days=age)).isoformat()}))
    result=report(site.id,7)
    assert result['conversions']=={'test_drive':1}
    assert [(g['metric'],g['actual']) for g in result['goals']]==[('all',2),('test_drive',1)]
    assert 'error' in websites.update_admin_settings(site.id,{'conversion_goals':[{'metric':'sale','target':10,'enabled':True}]})
    assert 'error' in websites.update_admin_settings(site.id,{'conversion_goals':[{'metric':'all','target':-1,'enabled':True}]})
    assert 'error' in websites.update_admin_settings(site.id,{'ai_receptionist_enabled':'yes'})
