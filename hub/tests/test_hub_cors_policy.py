import pytest
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient
from hub_core.cors_policy import HUB_WEB_ORIGINS, LEGACY_HUB_ORIGIN_REGEX


@pytest.mark.parametrize('origin,allowed',[
    ('https://hub.nxtdeal.app',True), ('https://apps.nxtdeal.app',True),
    ('https://app.nxtdeal.app',True), ('https://hub.dealeros.xyz',False),
    ('https://apps.dealeros.xyz',False), ('http://localhost:3000',True),
    ('http://hub.nxtdeal.app',False), ('https://hub.nxtdeal.app.attacker.example',False),
    ('https://unknown.nxtdeal.app',False), ('https://admin.nxtdeal.app',False), ('null',False),
])
def test_hub_browser_preflight(origin,allowed):
    app = CORSMiddleware(Starlette(),allow_origins=HUB_WEB_ORIGINS,
        allow_origin_regex=LEGACY_HUB_ORIGIN_REGEX,allow_credentials=True,
        allow_methods=['*'],allow_headers=['*'])
    with TestClient(app) as client:
        response = client.options('/hub/public/resolve/dealer',headers={
            'Origin':origin,'Access-Control-Request-Method':'GET',
            'Access-Control-Request-Headers':'authorization,content-type'})
    assert response.status_code == (200 if allowed else 400)
    assert response.headers.get('access-control-allow-origin') == (origin if allowed else None)
