import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from core import website_provisioning as provision


@pytest.fixture
def platform(monkeypatch, tmp_path):
    monkeypatch.setenv('DEALEROS_STORAGE_DIR', str(tmp_path))
    for key, value in {'TEMPLATE_UUID':'public-template', 'DESTINATION_UUID':'destination',
                       'TEMPLATE_COMMIT':'a'*40, 'ROUTING_IPS':'203.161.58.9'}.items():
        monkeypatch.setenv('NXT_WEBSITE_'+key, value)
    monkeypatch.setattr(provision, 'routing', lambda domain: True)
    calls = []
    def request(cfg, method, path, payload=None):
        calls.append((method, path, payload))
        if path.endswith('/storages'):
            return {'persistent_storages': [], 'file_storages': []}
        if path.endswith('/clone'):
            return {'uuid':'new-resource'}
        if path == '/applications':
            return [{'uuid':'new-resource', 'name':provision.read_registry()['SITE-1']['name']}]
        return {'build_pack':'dockercompose','docker_compose_location':'/compose.website-public.yaml',
                'git_commit_sha':'a'*40, 'settings':{'is_auto_deploy_enabled':False},
                'status':'exited', 'name':provision.read_registry().get('SITE-1',{}).get('name')}
    return calls, request


def test_clone_is_saved_and_retry_does_not_duplicate(platform):
    calls, request = platform
    result = provision.provision('SITE-1','dealer.example',{},request)
    assert result['configured']
    assert provision.read_registry()['SITE-1']['resource_uuid'] == 'new-resource'
    assert calls[2][2]['clone_volumes'] is False
    assert [c[1] for c in calls[-2:]] == ['/applications/new-resource/envs','/applications/new-resource']
    assert calls[-2][2]['value'] == 'SITE-1'
    assert calls[-1][2]['force_domain_override'] is False
    count = len(calls)
    assert provision.provision('SITE-1','dealer.example',{},request) == result
    assert len(calls) == count


def test_timeout_recovers_exact_operation(platform):
    calls, request = platform
    def timeout(cfg, method, path, payload=None):
        if path.endswith('/clone'):
            raise ValueError('timeout')
        return request(cfg,method,path,payload)
    with pytest.raises(ValueError,match='timeout'):
        provision.provision('SITE-1','dealer.example',{},timeout)
    assert provision.read_registry()['SITE-1']['clone_requested']
    assert provision.provision('SITE-1','dealer.example',{},request)['configured']
    assert not any(c[1].endswith('/clone') for c in calls)


def test_domain_conflict_and_domain_change_fail_closed(platform):
    calls, request = platform
    provision.provision('SITE-1','dealer.example',{},request)
    with pytest.raises(ValueError,match='another website'):
        provision.provision('SITE-2','dealer.example',{},request)
    with pytest.raises(ValueError,match='disconnected'):
        provision.provision('SITE-1','different.example',{},request)


@pytest.mark.parametrize('change',[
    {'build_pack':'nixpacks'}, {'docker_compose_location':'/staff.yaml'},
    {'git_commit_sha':'b'*40}, {'settings':{'is_auto_deploy_enabled':True}}])
def test_unsafe_template_never_cloned(platform,change):
    calls, request = platform
    def altered(cfg,method,path,payload=None):
        return {**request(cfg,method,path,payload),**change}
    with pytest.raises(ValueError,match='template'):
        provision.provision('SITE-1','dealer.example',{},altered)
    assert len(calls)==1
    assert not provision.read_registry()


def test_assignments_isolated_per_tenant(platform, monkeypatch,tmp_path):
    calls,request=platform
    provision.provision('SITE-1','dealer.example',{},request)
    monkeypatch.setenv('DEALEROS_STORAGE_DIR', str(tmp_path/'other'))
    assert provision.read_registry()=={}


def test_ambiguous_clone_never_repeated(platform):
    calls,request=platform
    provision.save_registry({'SITE-1':{'domain':'dealer.example','name':'unique',
        'template_uuid':'public-template','commit':'a'*40,'clone_requested':True}})
    def missing(cfg,method,path,payload=None):
        return [] if path=='/applications' else request(cfg,method,path,payload)
    with pytest.raises(ValueError,match='awaiting confirmation'):
        provision.provision('SITE-1','dealer.example',{},missing)
    assert not any(c[0]=='POST' for c in calls)
