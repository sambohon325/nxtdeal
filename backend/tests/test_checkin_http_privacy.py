"""Check private appointment responses are not reusable from HTTP caches."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from api.routers import appointments as routes

@pytest.mark.parametrize('result', [{'error':'expired'}, {'status':'confirmed','person_name':'Fixture'}])
@pytest.mark.parametrize('method', ['GET','POST'])
def test_private_checkin_responses_are_not_cached(monkeypatch, result, method):
    calls=[]
    def read(token):
        calls.append(token)
        return result
    def write(token, *args, **kwargs):
        return read(token)
    monkeypatch.setattr(routes,'get_public_checkin_view',read)
    monkeypatch.setattr(routes,'record_public_checkin',write)
    app=FastAPI()
    app.include_router(routes.router)
    client=TestClient(app)
    path='/public/checkin/fixture-token'
    response=(client.get(path) if method=='GET' else
              client.post(path+'/submit',json={'drop_off_or_wait':'wait'}))
    assert response.json()==result
    assert response.headers['cache-control']=='no-store'
    assert response.headers['referrer-policy']=='no-referrer'
    assert calls==['fixture-token']
