import pytest
from fastapi.testclient import TestClient
from api.app import app


@pytest.mark.parametrize("path", ["/network/anonymous-snapshot", "/public/garage/vehicles?token=synthetic-invalid",
    "/sso/callback?state=synthetic-invalid&code=synthetic-invalid", "/nonexistent-security-test"])
def test_api_responses_are_not_stored_without_bearer_header(path):
    response = TestClient(app).get(path)
    assert response.headers["Cache-Control"] == "no-store"
