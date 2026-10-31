"""Real HTTP checks for dealership versus NXTDeal administration."""
import pytest
from fastapi.testclient import TestClient
from api.app import app
from core.auth import credential_store, issue_token, issue_mfa_challenge_token
from core.administration_access import SYSTEM_MENU_KEYS, DEALERSHIP_MENU_KEYS, system_admin_context

@pytest.fixture
def access(monkeypatch):
    monkeypatch.setenv("NXTDEAL_SYSTEM_ADMIN_IDS", "SYN-SYSTEM,SYN-RESERVED")
    for employee, role in [("SYN-DEALER", "ADMIN"), ("SYN-SYSTEM", "ADMIN"), ("SYN-SALES", "SALES")]:
        credential_store.set_credential(employee, "Fictional-access-test2026!", role, must_change_password=False)
    return TestClient(app), {name: {"Authorization": "Bearer " + issue_token(name, role, fresh_auth=True)}
        for name, role in [("SYN-DEALER", "ADMIN"), ("SYN-SYSTEM", "ADMIN"), ("SYN-SALES", "SALES")]}


def test_session_capability_is_separate_from_dealership_role(access):
    client, headers = access
    for employee in headers:
        result = client.get("/auth/whoami", headers=headers[employee]).json()
        assert result["is_system_admin"] == (employee == "SYN-SYSTEM")
    assert not system_admin_context.get()


def test_admin_catalog_and_direct_menu_reads(access):
    client, headers = access
    for employee, expected in [("SYN-DEALER", DEALERSHIP_MENU_KEYS), ("SYN-SYSTEM", DEALERSHIP_MENU_KEYS | SYSTEM_MENU_KEYS), ("SYN-SALES", set())]:
        result = client.get("/menu/catalog?department=Administration", headers=headers[employee]).json()
        assert {item["key"] for item in result["items"]} == expected
    for key in SYSTEM_MENU_KEYS:
        assert "error" in client.get("/menu/data", params={"department": "Administration", "item_key": key}, headers=headers["SYN-DEALER"]).json()
    assert "error" not in client.get("/system-config", headers=headers["SYN-DEALER"]).json()


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/audit", None), ("GET", "/audit-center/overview", None),
    ("GET", "/success-center/dealers", None), ("GET", "/connections", None),
    ("GET", "/security/sso/config", None), ("GET", "/api-keys/all", None),
    ("GET", "/data-management/backups", None), ("GET", "/dealer-bridge", None),
    ("GET", "/bot/fleet", None), ("GET", "/ai-management/overview", None),
    ("POST", "/entitlements/module", {"module":"sales","enabled":True}),
    ("POST", "/system-config/feature-flags", {"flag":"ai_assistant_enabled","enabled":False}),
    ("POST", "/connections/email", {"provider":"synthetic"}),
    ("POST", "/data-management/backups/fake/restore", {}),
])
def test_dealer_cannot_call_system_endpoints(access, method, path, body):
    client, headers = access
    result = client.request(method, path, headers=headers["SYN-DEALER"], json=body)
    assert result.status_code == 403
    assert result.json()["code"] == "system_admin_required"


def test_system_admin_can_read_system_tools_and_scope_does_not_leak(access):
    client, headers = access
    for path in ["/audit", "/connections", "/data-management/backups", "/ai-management/overview"]:
        result = client.get(path, headers=headers["SYN-SYSTEM"])
        assert result.status_code == 200 and "error" not in result.json()
        assert client.get(path, headers=headers["SYN-DEALER"]).status_code == 403


@pytest.mark.parametrize("path,body", [
    ("/auth/admin/credentials", {"employee_id":"SYN-SYSTEM","role":"ADMIN","temp_password":"Replacement-test2026!"}),
    ("/auth/admin/credentials", {"employee_id":"SYN-RESERVED","role":"ADMIN","temp_password":"Replacement-test2026!"}),
    ("/auth/admin/reset-password", {"employee_id":"SYN-SYSTEM","temp_password":"Replacement-test2026!"}),
    ("/auth/admin/mfa/SYN-SYSTEM/disable", {}),
    ("/users/SYN-SYSTEM/role", {"new_role":"SALES"}),
])
def test_dealer_cannot_take_over_system_identity(access, path, body):
    client, headers = access
    before = dict(credential_store.get_record("SYN-SYSTEM"))
    assert "error" in client.post(path, json=body, headers=headers["SYN-DEALER"]).json()
    assert credential_store.get_record("SYN-SYSTEM") == before
    assert credential_store.get_record("SYN-RESERVED") is None


def test_challenge_api_key_and_removed_designation_fail_closed(access, monkeypatch):
    client, headers = access
    challenge = issue_mfa_challenge_token("SYN-SYSTEM", "ADMIN")
    assert client.get("/audit", headers={"Authorization":"Bearer " + challenge}).status_code == 401
    from core.api_keys import generate_api_key
    from core.dealeros import ledger
    from core.entities import Entity
    ledger.add_entity(Entity(id="SYN-SYSTEM", entity_type="Employee", attributes={}))
    key = generate_api_key("SYN-SYSTEM", "Test", "SYN-SYSTEM")
    # API keys are valid staff credentials but never inherit platform privileges.
    raw = key.get("raw_key") or key.get("key") or key.get("api_key")
    assert raw, key
    assert client.get("/audit", headers={"Authorization":"Bearer " + raw}).status_code in (401,403)
    monkeypatch.setenv("NXTDEAL_SYSTEM_ADMIN_IDS", "")
    assert client.get("/audit", headers=headers["SYN-SYSTEM"]).status_code == 403


def test_dealership_settings_and_staff_actions_still_work(access):
    client, headers = access
    result = client.post("/system-config/organization-profile", headers=headers["SYN-DEALER"], json={"dealership_name":"Synthetic permission verification"}).json()
    assert "error" not in result
    assert client.get("/system-config", headers=headers["SYN-DEALER"]).json()["dealership_name"] == "Synthetic permission verification"
    created = client.post("/users", headers=headers["SYN-DEALER"], json={"first_name":"Synthetic","last_name":"Staff","email":"synthetic-access@example.invalid","role":"SALES"}).json()
    assert "error" not in created
    assert created["role"] == "SALES" and created["must_change_password"]
    assert "error" not in client.post("/users/" + created["employee_id"] + "/role", headers=headers["SYN-DEALER"], json={"new_role":"ADMIN"}).json()
    from core.administration_access import reserved_system_admin
    assert not reserved_system_admin(created["employee_id"])


def test_control_records_cannot_bypass_system_workflows(access):
    client, headers = access
    from core.dealeros import ledger
    from core.entities import Entity
    for kind in ["MarketplaceInstall", "SystemConfig", "Entitlement", "SsoConfig", "TeamAgent", "ExecutionPolicy", "ProviderCredential"]:
        key = "SYN-CONTROL-" + kind
        ledger.add_entity(Entity(id=key, entity_type=kind, attributes={"enabled":False}))
        result = client.post("/entity/"+key+"/update", headers=headers["SYN-DEALER"], json={"patch":{"enabled":True}}).json()
        assert "error" in result
        assert ledger.get_entity(key).attributes == {"enabled":False}


def test_system_feature_flag_write_and_dealer_override_denial(access):
    client, headers = access
    body={"flag":"ai_assistant_enabled","enabled":False}
    assert "error" not in client.post("/system-config/feature-flags", headers=headers["SYN-SYSTEM"], json=body).json()
    result=client.post("/permissions/overrides", headers=headers["SYN-DEALER"], json={"employee_id":"SYN-DEALER","permission_key":"admin.view_audit","granted":True,"reason":"Test"}).json()
    assert "error" in result


def test_marketplace_browsing_and_installation_scope(access):
    client, headers=access
    for name,can_manage in [("SYN-DEALER",False),("SYN-SYSTEM",True),("SYN-SALES",False)]:
        result=client.get("/marketplace",headers=headers[name])
        assert result.status_code==200 and result.json()["can_manage"] is can_manage
    for action in ("install","uninstall"):
        assert client.post("/marketplace/listings/synthetic/"+action,headers=headers["SYN-DEALER"]).status_code==403
