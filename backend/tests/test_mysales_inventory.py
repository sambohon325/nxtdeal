from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.mysales_inventory import router

def test_feed_is_opt_in_and_only_returns_retail_fields(monkeypatch):
    app=FastAPI();app.include_router(router);client=TestClient(app)
    monkeypatch.delenv('NXTDEAL_MYSALES_INVENTORY_ENABLED',raising=False)
    assert client.get('/public/mysales/inventory').status_code==404
    monkeypatch.setenv('NXTDEAL_MYSALES_INVENTORY_ENABLED','true')
    monkeypatch.setenv('OPENAI_API_KEY','sk-local-test-only')
    from core import websites
    monkeypatch.setattr(websites,'get_live_inventory',lambda **kw:[{'id':'V1','year':2026,'make':'Test','cost':12000,'private_notes':'secret','customer_id':'C1'}])
    data=client.get('/public/mysales/inventory').json()
    assert data['read_only'] is True
    assert set(data['items'][0])=={'id','year','make','model','trim','price','mileage','image_url'}
    assert client.get('/public/mysales/inventory?limit=501').status_code==422
    assert client.post('/public/mysales/inventory',json={}).status_code==405
