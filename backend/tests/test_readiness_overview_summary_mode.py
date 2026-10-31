"""External clients retain summary options; NXTDeal can read without an AI call."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import readiness_overview as routes
from core import readiness_overview_api as service


@pytest.mark.parametrize("query,expected", [("", True), ("?polish_summary=false", False), ("?polish_summary=true", True)])
def test_summary_mode_passes_from_http_to_composition(monkeypatch, query, expected):
    calls = []
    monkeypatch.setattr(routes, "_authenticate", lambda auth: ({"role": "ADMIN"}, None))
    def compose(role, polish_summary=True):
        calls.append((role, polish_summary))
        return {"executive_summary": {"ai_generated": polish_summary}}
    monkeypatch.setattr(service, "get_enterprise_readiness_overview", compose)
    app = FastAPI()
    app.include_router(routes.router)
    response = TestClient(app).get("/readiness-overview/overview" + query)
    assert response.status_code == 200
    assert calls == [("ADMIN", expected)]
    assert response.json()["executive_summary"]["ai_generated"] is expected


def test_summary_mode_does_not_bypass_role_gate(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unauthorized request reached composition")
    monkeypatch.setattr(service, "get_enterprise_readiness_overview", forbidden)
    assert "error" in service.get_enterprise_readiness_overview_api("NOT_A_ROLE", polish_summary=False)
