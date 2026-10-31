import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient
from core.customer_verification_boundary import CustomerVerificationBoundary


@pytest.fixture
def guarded():
    app = FastAPI()
    calls = []
    @app.api_route("/{path:path}", methods=["GET", "POST", "OPTIONS"])
    def endpoint(path: str):
        calls.append(path)
        return {"reached": True}
    app.add_middleware(CustomerVerificationBoundary)
    app.add_middleware(CORSMiddleware, allow_origins=["https://app.nxtdeal.app"],
                       allow_methods=["*"], allow_headers=["*"])
    return TestClient(app), calls


@pytest.mark.parametrize("path", [
    "/public/verify/start", "/public/verify/legacy-token", "/public/verify/legacy-token/confirm-code",
    "/public/garage/vehicles", "/public/garage/approvals/RO1/respond",
    "/public/garage/approvals/RO1/pay", "/public/retail/deals/DEAL1",
    "/public/retail/deals/DEAL1/sign", "/public/garage/",
])
@pytest.mark.parametrize("method", ["get", "post"])
def test_legacy_token_cannot_reach_data_or_mutation(guarded, path, method):
    client, calls = guarded
    response = getattr(client, method)(path + "?token=legacy-promoted-token",
                                      headers={"Origin": "https://app.nxtdeal.app"})
    assert response.status_code == 503
    assert response.json()["reason"] == "provider_unavailable"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "https://app.nxtdeal.app"
    assert calls == []


@pytest.mark.parametrize("path", [
    "/public/personal-sites/rep", "/public/websites/site", "/public/entitlements",
    "/auth/login", "/sales/overview", "/public/garage-other", "/public/retail-other",
])
def test_unrelated_routes_are_preserved(guarded, path):
    client, calls = guarded
    assert client.get(path).json() == {"reached": True}
    assert calls == [path.lstrip("/")]


def test_preflight_remains_available(guarded):
    client, calls = guarded
    result = client.options("/public/garage/vehicles", headers={
        "Origin": "https://app.nxtdeal.app", "Access-Control-Request-Method": "GET"})
    assert result.status_code == 200
    assert calls == []


def test_real_application_blocks_every_registered_customer_route():
    """Use actual middleware, isolated conftest storage, and no lifespan workers."""
    import re
    from api.app import app as real_app
    routes = [route for route in real_app.routes
              if any(getattr(route, "path", "").startswith(root + "/")
                     for root in ("/public/verify", "/public/garage", "/public/retail"))]
    assert len(routes) >= 20, "Customer-route coverage unexpectedly disappeared"
    client = TestClient(real_app)
    for route in routes:
        path = re.sub(r"\{[^}]+\}", "legacy-fixture", route.path)
        for method in route.methods - {"OPTIONS", "HEAD"}:
            response = client.request(method, path, params={"token": "legacy-promoted-token"},
                                      headers={"Origin": "https://app.nxtdeal.app"})
            assert response.status_code == 503, (method, path, response.status_code)
            assert response.json()["reason"] == "provider_unavailable"
            assert response.headers["access-control-allow-origin"] == "https://app.nxtdeal.app"
            assert response.headers["cache-control"] == "no-store"
