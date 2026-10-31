import pytest
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient

from core.cors_policy import DEALER_WEB_ORIGINS, LEGACY_DEALER_ORIGIN_REGEX


@pytest.mark.parametrize('origin,allowed',[
    ('https://nxtdeal.app',True),
    ('https://www.nxtdeal.app',True),
    ('https://app.nxtdeal.app',True),
    ('https://apps.nxtdeal.app',True),
    ('http://apps.nxtdeal.app',False),
    ('https://dealer1.dealeros.xyz',False),
    ('http://localhost:3000',True),
    ('https://nxtdeal.app.attacker.example',False),
    ('https://attacker-nxtdeal.app',False),
    ('http://app.nxtdeal.app',False),
    ('https://unknown.nxtdeal.app',False),
    ('https://admin.nxtdeal.app',False),
    ('null',False),
])
def test_dealer_browser_preflight(origin,allowed):
    app = CORSMiddleware(Starlette(),allow_origins=DEALER_WEB_ORIGINS,
        allow_origin_regex=LEGACY_DEALER_ORIGIN_REGEX,allow_credentials=True,
        allow_methods=['*'],allow_headers=['*'])
    with TestClient(app) as client:
        response = client.options('/auth/login',headers={
            'Origin':origin,'Access-Control-Request-Method':'POST',
            'Access-Control-Request-Headers':'authorization,content-type'})
    assert response.status_code == (200 if allowed else 400)
    assert response.headers.get('access-control-allow-origin') == (origin if allowed else None)
    if allowed:
        assert response.headers['access-control-allow-credentials'] == 'true'
