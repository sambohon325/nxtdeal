import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import pytest
from core import website_hosting as hosting


@pytest.fixture
def configured(monkeypatch):
    for key, value in {'URL':'https://hosting.example.test','TOKEN':'synthetic-token', 'RESOURCE_UUID':'isolated-resource', 'SITE_ID':'SITE-00001','ALLOWED_DOMAIN':'websites.example.test'}.items():
        monkeypatch.setenv('NXT_WEBSITE_COOLIFY_'+key if key in ('URL','TOKEN') else 'NXT_WEBSITE_'+key,value)


def test_configuration_fails_closed(configured, monkeypatch):
    assert hosting.readiness('SITE-00001')
    assert not hosting.readiness('SITE-OTHER')
    monkeypatch.setenv('NXT_WEBSITE_COOLIFY_URL','http://public.example.test')
    assert not hosting.readiness('SITE-00001')
    monkeypatch.setenv('NXT_WEBSITE_COOLIFY_URL','http://127.0.0.1:8000')
    assert hosting.readiness('SITE-00001')


def test_only_assigned_domain_and_gateway_are_modified(configured, monkeypatch):
    calls=[]
    def request(cfg,method,path,payload=None):
        calls.append((method,path,payload))
        return {'build_pack':'dockercompose','docker_compose_domains':json.dumps({'gateway':{'domain':'https://websites.example.test'}})}
    monkeypatch.setattr(hosting,'_request',request)
    with pytest.raises(ValueError):hosting.connect('SITE-00001','other.example.test')
    assert not calls
    result=hosting.connect('SITE-00001','websites.example.test')
    assert not result['hosting_active']
    assert [c[0] for c in calls]==['GET','PATCH','POST']
    assert calls[1][2]['force_domain_override'] is False
    assert calls[1][2]['docker_compose_domains']==[{'name':'gateway','domain':'https://websites.example.test:8080'}]


@pytest.mark.parametrize('mapping',[{'gateway':{'domain':'https://another.example.test'}},{'api':{'domain':'https://websites.example.test'}},[], 'invalid'])
def test_refuses_existing_other_mappings(configured,monkeypatch,mapping):
    calls=[]
    def request(cfg,method,path,payload=None):
        calls.append(method)
        return {'build_pack':'dockercompose','docker_compose_domains':mapping}
    monkeypatch.setattr(hosting,'_request',request)
    with pytest.raises(ValueError):hosting.connect('SITE-00001','websites.example.test')
    assert calls==['GET']


def test_https_requires_matching_public_site(configured,monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return b'{"id":"WRONG","studio_config":{"theme_id":"lone-star"}}'
    class Opener:
        def open(self,*args,**kwargs):return Response()
    monkeypatch.setattr(hosting.urllib.request,'build_opener',lambda *args:Opener())
    with pytest.raises(ValueError,match='HTTPS is not ready'):hosting.probe('SITE-00001','websites.example.test')
