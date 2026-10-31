"""End-to-end HTTP acceptance against disposable storage; no external AI calls."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
from pathlib import Path
import os
from test_lone_star import lone_star

def test_lone_star_complete_customer_and_dealer_journey(monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import app
    from core import websites, website_chat as chat
    from core.auth import credential_store
    from core.entities import Entity
    from core.dealeros import ledger
    from core.storage_paths import GRAPH_PATH
    assert Path(str(GRAPH_PATH)).resolve().is_relative_to(Path(os.environ['DEALEROS_STORAGE_DIR']).resolve())
    previous=deepcopy(credential_store.credentials);ledger.reset()
    c=TestClient(app)
    try:
        auth={}
        for employee,role in [('SYN-E2E','ADMIN'),('SYN-OTHER','SALES')]:
            credential_store.set_credential(employee,'Synthetic-password2026!',role,must_change_password=False)
            token=c.post('/auth/login',json={'employee_id':employee,'password':'Synthetic-password2026!'}).json()['token']
            auth[employee]={'Authorization':'Bearer '+token}
        owner,other=auth.values()
        site=c.post('/website-studio/sites',headers=owner,json={'name':'E2E Lone Star','theme_id':'lone-star','request_id':str(uuid4())}).json(); sid=site['id'];path='/websites/'+sid;pub='/public/websites/'+sid
        cfg={'version':1,'theme_id':'lone-star','lone_star':lone_star()}
        saved=c.put(path+'/studio',headers=owner,json={'config':cfg,'expected_revision':site['studio_revision']}).json()
        assert saved['studio_config']['lone_star']==cfg['lone_star'],saved
        assert c.get(path,headers=owner).json()['studio_config']['lone_star']==cfg['lone_star']
        assert 'error' in c.put(path+'/studio',headers=other,json={'config':cfg,'expected_revision':1}).json()
        assert 'error' in c.put(path+'/studio',headers=owner,json={'config':cfg,'expected_revision':0}).json()
        for invalid in ['https://www.example.test', 'www.example.test/path', '127.0.0.1', '*.example.test', 'bad_label.example.test', 123]:
            assert 'error' in c.post(path+'/admin-settings',headers=owner,json={'patch':{'custom_domain':invalid}}).json()
        assert 'error' not in c.post(path+'/admin-settings',headers=owner,json={'patch':{'custom_domain':' WWW.EXAMPLE.TEST '}}).json()
        assert c.get(path,headers=owner).json()['admin_settings']['custom_domain']=='www.example.test'
        assert c.get(path+'/dns-instructions',headers=owner).json()['record_host']=='www.example.test'
        assert 'error' in c.post(path+'/admin-settings',headers=other,json={'patch':{'custom_domain':'other.example.test'}}).json()
        from core import website_domains
        domain_path=path+'/domain-connection'
        assert 'error' in c.post(domain_path+'/prepare',headers=other).json()
        prepared=c.post(domain_path+'/prepare',headers=owner).json()
        assert prepared['txt_host']=='_nxtdeal.www.example.test'
        assert prepared['txt_value']==c.post(domain_path+'/prepare',headers=owner).json()['txt_value']
        monkeypatch.setattr(website_domains,'_txt_values',lambda host:[prepared['txt_value']])
        verified=c.post(domain_path+'/verify',headers=owner).json()
        assert verified['ownership_verified'] and not verified['hosting_active']
        assert 'error' in c.post(domain_path+'/activate',headers=other).json()
        assert 'Approve' in c.post(domain_path+'/activate',headers=owner).json()['error']
        monkeypatch.setattr(website_domains,'_txt_values',lambda host:['unrelated'])
        assert not c.post(domain_path+'/verify',headers=owner).json()['ownership_verified']
        c.post(path+'/admin-settings',headers=owner,json={'patch':{'custom_domain':'new.example.test'}})
        assert not c.get(domain_path,headers=owner).json()['ownership_verified']
        assert c.post(domain_path+'/prepare',headers=owner).json()['txt_value']!=prepared['txt_value']
        settings={'ai_receptionist_enabled':True,'conversion_goals':[{'metric':'all','target':20,'enabled':True},{'metric':'assistant','target':5,'enabled':True}]}
        assert 'error' not in c.post(path+'/admin-settings',headers=owner,json={'patch':settings}).json()
        assert 'error' in c.get(path+'/assistant-readiness',headers=other).json()
        assert c.post(path+'/submit',headers=owner).json()['status']=='pending_approval'
        assert c.post(path+'/approve',headers=owner,json={}).json()['status']=='published'
        assert c.get(path+'/assistant-readiness',headers=owner).json()['published_enabled'] is True
        from core import website_hosting
        proof=c.post(domain_path+'/prepare',headers=owner).json()
        monkeypatch.setattr(website_domains,'_txt_values',lambda host:[proof['txt_value']])
        connections=[]
        monkeypatch.setattr(website_hosting,'connect',lambda site_id,domain:connections.append((site_id,domain)) or {'hosting_active':False,'message':'Activating'})
        monkeypatch.setattr(website_hosting,'probe',lambda site_id,domain:{'hosting_active':True,'message':'HTTPS verified'})
        assert not c.post(domain_path+'/activate',headers=owner).json()['hosting_active']
        assert connections==[(sid,'new.example.test')]
        assert c.post(domain_path+'/check_https',headers=owner).json()['hosting_active']
        assert c.get(domain_path,headers=owner).json()['hosting_active']
        monkeypatch.setattr(website_domains,'_txt_values',lambda host:[])
        assert 'error' in c.post(domain_path+'/activate',headers=owner).json()
        assert len(connections)==1
        assert not c.get(domain_path,headers=owner).json()['hosting_active']

        for key,body,sold in [('TRUCK','Truck',False),('SUV','SUV',False),('SOLD','Truck',True)]:
            ledger.add_entity(Entity(id='SYN-'+key,entity_type='Vehicle',attributes={'Make':'Synthetic','Model':key,'Year':2024,'BodyStyle':body,'Price':25000,'DateSold':'2026-01-01' if sold else ''}))
        inventory=c.get(pub+'/inventory').json()
        assert {v['id'] for v in inventory['vehicles']}=={'SYN-TRUCK','SYN-SUV'}
        assert c.get(pub+'/inventory?q=SUV').json()['total']==1
        public=c.get(pub).json();index=next(i for i,s in enumerate(public['pages']['contact']['sections']) if s['section_key']=='contact_form')
        for intent in ['information','test_drive','purchase','financing','trade']:
            form={'page_key':'contact','section_index':index,'name':'Synthetic Shopper','email':'e2e@example.test','intent':intent,'vehicle_id':'SYN-TRUCK','request_id':str(uuid4())}
            first=c.post(pub+'/contact',json=form).json();assert 'lead_id' in first,first
            assert c.post(pub+'/contact',json=form).json()==first
            assert ledger.get_entity(first['lead_id']).attributes['WebsiteVehicleID']=='SYN-TRUCK'
        form['request_id']=str(uuid4());form['vehicle_id']='SYN-SOLD';assert 'error' in c.post(pub+'/contact',json=form).json()
        calls=[]
        def provider(**kw):
            calls.append(kw);return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"reply_text":"I can connect you with our service team. What service do you need?"}'))])
        from core import website_ai_credentials
        monkeypatch.setattr(website_ai_credentials,'completion',lambda site,**kw:chat.client.chat.completions.create(model='gpt-4o-mini',**kw))
        monkeypatch.setattr(chat,'client',SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=provider))))
        monkeypatch.setattr(chat,'is_feature_enabled',lambda _:True)
        monkeypatch.setattr(chat,'record_call_attempt',lambda *a,**k:None)
        session=c.post(pub+'/chat/start',json={'visitor_name':'Synthetic Service','visitor_email':'service@example.test','department':'service','initial_message':'I need an oil change'}).json()
        cs=session['id'];assert session['department']=='service' and len(cs)>30
        assert 'Customer-selected department: service' in calls[0]['messages'][1]['content']
        messages=c.get('/public/chat/'+cs+'/messages').json();assert [m['sender'] for m in messages]==['visitor','ai']
        assert 'error' in c.post('/websites/chat/'+cs+'/claim',headers=other).json()
        assert 'error' not in c.post('/websites/chat/'+cs+'/reply',headers=owner,json={'body':'The service team is here.'}).json()
        c.post('/public/chat/'+cs+'/messages',json={'body':'Thanks'})
        assert len(calls)==1,'AI must stop after staff handoff'
        promoted=c.post('/websites/chat/'+cs+'/promote',headers=owner,json={}).json();assert 'lead_id' in promoted,promoted
        assert 'error' in c.post('/websites/chat/'+cs+'/promote',headers=owner,json={}).json()
        assert ledger.get_entity(promoted['lead_id']).attributes['WebsiteInquiryIntent']=='assistant'
        # Missing provider path produces honest handoff, never invented inventory.
        def unavailable(**kw):raise RuntimeError('Synthetic unavailable provider')
        chat.client.chat.completions.create=unavailable
        fallback=c.post(pub+'/chat/start',json={'initial_message':'Find me a truck','department':'sales'}).json()
        assert 'team member' in c.get('/public/chat/'+fallback['id']+'/messages').json()[-1]['body']
        analytics=c.get(path+'/analytics?days=7',headers=owner).json()['traffic']
        assert analytics['leads']==6 and analytics['conversions']['assistant']==1
        assert [(g['metric'],g['actual']) for g in analytics['goals']]==[('all',6),('assistant',1)]
        draft=c.post(path+'/studio/draft',headers=owner).json();cfg['lone_star']['headline']='A saved draft only'
        c.put(path+'/studio',headers=owner,json={'config':cfg,'expected_revision':draft['studio_revision']})
        assert c.get(path,headers=owner).json()['studio_config']['lone_star']['headline']=='A saved draft only'
        assert c.get(pub).json()['studio_config']['lone_star']['headline']!='A saved draft only'
        assert 'WebsiteChatSessionID' in Path(str(GRAPH_PATH)).read_text(encoding='utf-8')
    finally:
        c.close();ledger.reset();credential_store.load_credentials(previous)
