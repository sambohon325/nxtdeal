import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from api.routers import personal_sites as routes
from core import personal_sites
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE

@pytest.fixture
def fixture(monkeypatch):
    ledger.reset()
    monkeypatch.setattr(personal_sites, 'save_graph', lambda *_: None)
    def auth(value):
        return ({'role': 'SALES', 'employee_id': value}, None) if value else (None, {'error': 'Sign in required'})
    monkeypatch.setattr(routes, '_authenticate', auth)
    app = FastAPI()
    app.include_router(routes.router)
    site = personal_sites.create_personal_site('OWNER', 'fixture-rep')
    vehicle = Entity(id='VEH-FIXTURE', entity_type=VEHICLE, attributes={'Year':2024, 'Make':'Test', 'Model':'Fixture', 'Price':12345, 'internal_cost':9000})
    ledger.add_entity(vehicle)
    yield TestClient(app), site, vehicle
    ledger.reset()

def test_selection_publish_and_live_sold_filter(fixture):
    client, site, vehicle = fixture
    path = '/personal-sites/' + site.id
    result = client.post(path, headers={'Authorization':'OWNER'}, json={'patch':{'featured_vehicle_ids':[vehicle.id, vehicle.id]}})
    assert result.json()['featured_vehicle_ids'] == [vehicle.id]
    assert 'error' in client.get('/public/personal-sites/fixture-rep').json()
    client.post(path+'/status', headers={'Authorization':'OWNER'}, json={'status':'active'})
    public = client.get('/public/personal-sites/fixture-rep').json()
    assert len(public['featured_vehicles']) == 1
    assert 'internal_cost' not in public['featured_vehicles'][0]
    assert 'employee_id' not in public and 'history' not in public
    vehicle.attributes['DateSold'] = '2026-10-03'
    assert client.get('/public/personal-sites/fixture-rep').json()['featured_vehicles'] == []

@pytest.mark.parametrize('actor',[None,'OTHER'])
def test_unauthorized_selection_never_mutates(fixture, actor):
    client, site, vehicle = fixture
    result = client.post('/personal-sites/'+site.id, headers={'Authorization':actor} if actor else {}, json={'patch':{'featured_vehicle_ids':[vehicle.id]}})
    assert 'error' in result.json()
    assert site.attributes['featured_vehicle_ids'] == []

def test_malformed_selection_rejects_entire_patch(fixture):
    client, site, vehicle = fixture
    before = dict(site.attributes)
    result = client.post('/personal-sites/'+site.id, headers={'Authorization':'OWNER'}, json={'patch':{'headline':'Not saved','featured_vehicle_ids':[{}]}})
    assert 'error' in result.json()
    assert site.attributes == before

def test_parent_link_and_unlink_update_public_branding(fixture):
    from core.entity_types import WEBSITE
    client, site, vehicle = fixture
    parent = Entity(id='SITE-FIXTURE', entity_type=WEBSITE, attributes={'admin_settings':{'branding_mode':'oem','oem_name':'Fixture OEM','private_key':'not-public'}})
    ledger.add_entity(parent)
    path = '/personal-sites/'+site.id
    response = client.post(path+'/parent', headers={'Authorization':'OWNER'}, json={'parent_website_id':parent.id})
    assert response.json()['parent_website_id'] == parent.id
    client.post(path+'/status', headers={'Authorization':'OWNER'}, json={'status':'active'})
    branding = client.get('/public/personal-sites/fixture-rep').json()['branding']
    assert branding['oem_name'] == 'Fixture OEM' and 'private_key' not in branding
    response = client.post(path+'/parent', headers={'Authorization':'OTHER'}, json={'parent_website_id':None})
    assert 'error' in response.json() and site.attributes['parent_website_id'] == parent.id
    client.post(path+'/parent', headers={'Authorization':'OWNER'}, json={'parent_website_id':None})
    assert client.get('/public/personal-sites/fixture-rep').json()['branding']['branding_mode'] == 'independent'

def test_invalid_parent_does_not_replace_current_link(fixture):
    client, site, vehicle = fixture
    response = client.post('/personal-sites/'+site.id+'/parent', headers={'Authorization':'OWNER'}, json={'parent_website_id':vehicle.id})
    assert 'error' in response.json()
    assert site.attributes['parent_website_id'] is None

def test_create_accepts_explicit_independent_parent(fixture):
    client, _, _ = fixture
    response = client.post('/personal-sites', headers={'Authorization':'NEW-OWNER'}, json={'slug':'new-fixture-rep','parent_website_id':None})
    assert response.status_code == 200
    assert response.json()['parent_website_id'] is None
    assert response.json()['status'] == 'draft'

@pytest.mark.parametrize('initial,target', [('draft','active'), ('active','inactive'), ('inactive','active')])
def test_failed_publication_save_preserves_public_visibility_and_all_attributes(fixture, monkeypatch, initial, target):
    from copy import deepcopy
    client, site, _ = fixture
    personal_sites.set_personal_site_status(site.id, initial, by='OWNER')
    before = deepcopy(site.attributes)
    def fail(_):
        raise OSError('fixture persistence failure')
    monkeypatch.setattr(personal_sites, 'save_graph', fail)
    with pytest.raises(OSError):
        client.post('/personal-sites/'+site.id+'/status', headers={'Authorization':'OWNER'}, json={'status':target})
    assert site.attributes == before
    public = client.get('/public/personal-sites/fixture-rep').json()
    assert ('error' not in public) == (initial == 'active')
    # A retry after persistence recovers must apply the intended transition once.
    monkeypatch.setattr(personal_sites, 'save_graph', lambda *_: None)
    response = client.post('/personal-sites/'+site.id+'/status', headers={'Authorization':'OWNER'}, json={'status':target})
    assert response.json()['status'] == target
    public = client.get('/public/personal-sites/fixture-rep').json()
    assert ('error' not in public) == (target == 'active')

@pytest.mark.parametrize('status', ['draft', 'active'])
def test_failed_slug_save_preserves_links_and_allows_retry(fixture, monkeypatch, status):
    from copy import deepcopy
    client, site, _ = fixture
    personal_sites.set_personal_site_status(site.id, status, by='OWNER')
    before = deepcopy(site.attributes)
    def fail(_):
        raise OSError('fixture persistence failure')
    monkeypatch.setattr(personal_sites, 'save_graph', fail)
    with pytest.raises(OSError):
        client.post('/personal-sites/'+site.id+'/slug', headers={'Authorization':'OWNER'}, json={'slug':'replacement-rep'})
    assert site.attributes == before
    assert personal_sites.get_personal_site_by_slug('fixture-rep').id == site.id
    assert personal_sites.get_personal_site_by_slug('replacement-rep') is None
    assert ('error' not in client.get('/public/personal-sites/fixture-rep').json()) == (status == 'active')
    assert 'error' in client.get('/public/personal-sites/replacement-rep').json()
    monkeypatch.setattr(personal_sites, 'save_graph', lambda *_: None)
    response = client.post('/personal-sites/'+site.id+'/slug', headers={'Authorization':'OWNER'}, json={'slug':'replacement-rep'})
    assert response.json()['slug'] == 'replacement-rep'
    assert personal_sites.get_personal_site_by_slug('fixture-rep') is None
    assert personal_sites.get_personal_site_by_slug('replacement-rep').id == site.id
    assert len(site.attributes['history']) == len(before['history']) + 1

def test_owner_previews_do_not_inflate_public_view_counts(fixture):
    client, site, _ = fixture
    path = '/personal-sites/'+site.id
    for _ in range(2):
        assert 'error' not in client.get(path+'/preview', headers={'Authorization':'OWNER'}).json()
    stats = client.get(path+'/analytics', headers={'Authorization':'OWNER'}).json()
    assert stats['total_views'] == 0 and stats['by_day'] == {}
    client.post(path+'/status', headers={'Authorization':'OWNER'}, json={'status':'active'})
    client.get('/public/personal-sites/fixture-rep')
    client.get(path+'/preview', headers={'Authorization':'OWNER'})
    stats = client.get(path+'/analytics', headers={'Authorization':'OWNER'}).json()
    assert stats['total_views'] == 1 and sum(stats['by_day'].values()) == 1
    assert 'error' in client.get(path+'/analytics', headers={'Authorization':'OTHER'}).json()
