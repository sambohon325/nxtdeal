import json
from types import SimpleNamespace
import pytest
from hub_core import dealership_lab_policy as policy


@pytest.fixture
def configured(monkeypatch):
    dealer=SimpleNamespace(api_base_url='https://tenant.example.test')
    monkeypatch.setattr(policy.registry,'get',lambda _:dealer)
    monkeypatch.setattr(policy,'get_secret',lambda *_:'test-only-network-key-never-for-production')
    monkeypatch.setattr(policy,'get_dealer_module_config',lambda _:dict(modules=[dict(key='network',enabled=False)]))
    return dealer


def test_policy_transport_rejects_fallback_http_and_redirects(configured,monkeypatch):
    configured.api_base_url='http://tenant.example.test'
    with pytest.raises(ValueError,match='HTTPS'):policy.exchange('DLR-TEST')
    configured.api_base_url='https://tenant.example.test'
    monkeypatch.setattr(policy,'get_secret',lambda *_:'dev-only-insecure-network-key-change-me')
    with pytest.raises(ValueError,match='secure'):policy.exchange('DLR-TEST')
    assert policy.NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.test') is None


def test_policy_only_reports_matching_tenant_receipt(configured,monkeypatch):
    calls=[];audits=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,limit):return json.dumps(dict(enabled=False,revision=3)).encode()
    class Opener:
        def open(self,request,timeout):calls.append(request);return Response()
    monkeypatch.setattr(policy.urllib.request,'build_opener',lambda *_:Opener())
    monkeypatch.setattr(policy,'record_and_save',lambda **event:audits.append(event))
    response=policy.synchronize('DLR-TEST',2,'TEST-ADMIN')
    assert response['synchronized'] is True
    assert json.loads(calls[0].data)==dict(dealer_id='DLR-TEST',enabled=False,revision=2)
    assert audits[-1]['actor']=='TEST-ADMIN'
    with pytest.raises(ValueError,match='receipt'):policy.synchronize('DLR-TEST',3,'TEST-ADMIN')
    assert audits[-1]['event_type']=='lab_policy_sync_failed'
