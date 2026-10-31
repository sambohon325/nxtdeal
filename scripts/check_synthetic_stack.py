"""HTTP acceptance against the fixed loopback staging stack; no production URL option."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

PASSWORD = 'Synthetic-Only-2026!'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urlopen(target, timeout=15):
    # A fixed initial address alone is insufficient: redirects/proxies could send
    # fictional credentials or bearer tokens to an unintended destination.
    url = target.full_url if isinstance(target, Request) else target
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
            or parsed.port not in (3317, 8317, 9317) or parsed.username or parsed.password):
        raise ValueError('Only fixed synthetic loopback endpoints are allowed')
    return build_opener(ProxyHandler({}), NoRedirect()).open(target, timeout=timeout)


def request(port, path, body=None, token=None, method=None, expected_status=200):
    headers = {'Content-Type':'application/json'}
    if token:
        headers['Authorization'] = 'Bearer '+token
    data = None if body is None else json.dumps(body).encode()
    try:
        response = urlopen(Request(f'http://127.0.0.1:{port}{path}',data=data,headers=headers,method=method),timeout=15)
    except HTTPError as error:
        response = error
    with response:
        assert response.status == expected_status, f'Expected HTTP {expected_status}, got {response.status}'
        return json.load(response)


def check(phase, state_path):
    state_path = Path(state_path)
    # Refuse a mistaken port/tunnel destination before sending any login or write.
    for port, service in [(8317,'dealer'),(9317,'hub')]:
        assert request(port,'/synthetic/identity') == {
            'scope':'synthetic_only','service':service,'delivery_enabled':False}
    with urlopen('http://127.0.0.1:3317/apps',timeout=15) as response:
        assert response.status == 200 and b'App Suite' in response.read()
    staff = request(8317,'/auth/login',{'employee_id':'EMP-00001','password':PASSWORD})['token']
    inventory = request(8317,'/menu/data?department=Inventory&item_key=inventory',token=staff)
    assert 'Fictional' in json.dumps(inventory) and '20100' in json.dumps(inventory)
    assert request(9317,'/mysales/email/status') == {'available':False}
    request(9317,'/mysales/me',expected_status=401)
    request(9317,'/mysales/login',{'email':'missing@example.test','password':PASSWORD},expected_status=401)
    sales = request(8317,'/auth/login',{'employee_id':'EMP-00003','password':PASSWORD})['token']
    request(8317,'/dealer-bridge/system-map',token=sales,expected_status=403)
    request(8317,'/dealer-bridge/system-map',expected_status=401)
    if phase == 'create':
        if state_path.exists():
            raise ValueError('Refusing to replace acceptance state')
        email = uuid4().hex+'@example.test'
        account = request(9317,'/mysales/signup',{'name':'Synthetic Acceptance','email':email,'password':PASSWORD})
        record = request(9317,'/mysales/records/contacts',{'title':'Restart survives'},account['token'])
        task = request(9317,'/mysales/records/tasks',{'title':'Fictional follow-up','due':'2026-10-08'},account['token'])
        request(9317,'/mysales/records/tasks/'+task['id'],{'title':'Fictional follow-up','done':True},account['token'],method='PUT')
        for invalid in [{'title':'   '}, {'title':'Invalid date','due':'2026-02-30'}]:
            request(9317,'/mysales/records/tasks',invalid,account['token'],expected_status=422)
        other = request(9317,'/mysales/signup',{'name':'Other Fictional Rep','email':uuid4().hex+'@example.test','password':PASSWORD})
        assert request(9317,'/mysales/records/contacts',token=other['token'])['items'] == []
        request(9317,'/mysales/records/contacts/'+record['id'],{'title':'Forbidden change'},other['token'],method='PUT',expected_status=404)
        request(9317,'/mysales/logout',{},other['token'])
        page = request(9317,'/mysales/page',{'headline':'Fictional Rep','bio':'Published fictional snapshot'},account['token'],method='PUT')
        public = '/mysales/public/pages/'+page['slug']
        request(9317,public,expected_status=404)
        request(9317,'/mysales/page/publication',{'published':True},account['token'],method='PUT')
        assert request(9317,public)['bio'] == 'Published fictional snapshot'
        request(9317,'/mysales/page/publication',{'published':False},account['token'],method='PUT')
        request(9317,public,expected_status=404)
        request(9317,'/mysales/page/publication',{'published':True},account['token'],method='PUT')
        request(9317,'/mysales/page',{'headline':'Fictional Rep','bio':'Private unfinished draft'},account['token'],method='PUT')
        assert request(9317,public)['bio'] == 'Published fictional snapshot'
        visitor = request(8317,'/up-system/log',{'up_type':'walk_in','first_name':'Container Visitor','phone':None},staff)
        assert visitor['assigned_to'] == 'EMP-00003'
        state_path.write_text(json.dumps({'email':email,'record':record['id'],'visitor':visitor['id'],'task':task['id'],'page':page['slug']}))
        request(9317,'/mysales/logout',{},account['token'])
        request(9317,'/mysales/me',token=account['token'],expected_status=401)
        request(9317,'/mysales/records/tasks',{'title':'Revoked write'},account['token'],expected_status=401)
    else:
        state = json.loads(state_path.read_text())
        account = request(9317,'/mysales/login',{'email':state['email'],'password':PASSWORD})
        records = request(9317,'/mysales/records/contacts',token=account['token'])['items']
        assert any(r['id'] == state['record'] and r['title'] == 'Restart survives' for r in records)
        if 'task' in state:  # Original hosted acceptance state remains readable.
            tasks = request(9317,'/mysales/records/tasks',token=account['token'])['items']
            assert len(tasks) == 1 and tasks[0]['id'] == state['task'] and tasks[0]['done'] is True
            public = '/mysales/public/pages/'+state['page']
            assert request(9317,public)['bio'] == 'Published fictional snapshot'
            assert request(9317,'/mysales/page',token=account['token'])['draft']['bio'] == 'Private unfinished draft'
        visitors = request(8317,'/up-system/ups',token=staff)
        assert any(r['id'] == state['visitor'] for r in visitors)
        request(9317,'/mysales/logout',{},account['token'])
    print(json.dumps({'scope':'synthetic_containers','phase':phase,'result':'passed','production_readiness':False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['create','verify'])
    parser.add_argument('state_path')
    args = parser.parse_args()
    check(args.phase,args.state_path)
