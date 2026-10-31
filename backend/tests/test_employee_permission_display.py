"""Read-only permission views must not inherit an administrator viewer's role."""
from types import SimpleNamespace
import pytest
import core.administration_menu as menu
import core.permissions_registry_api as api
import core.permissions_registry as registry

@pytest.fixture
def target(monkeypatch):
    record = {"role": "SALES"}
    store = SimpleNamespace(get_record=lambda employee: record if employee == "EMP-SYN" else None,
                            get_lockout_status=lambda employee: {"locked": False})
    monkeypatch.setattr(menu, "credential_store", store)
    monkeypatch.setattr(api, "credential_store", store)
    monkeypatch.setattr(menu, "get_entity_by_id", lambda role, employee: {"id": employee, "attributes": {}})
    monkeypatch.setattr(menu, "get_related_entities", lambda *args: [])
    monkeypatch.setattr(menu, "list_api_keys_for_employee", lambda *args: [])
    monkeypatch.setattr(menu, "get_actor_timeline", lambda *args, **kwargs: {})
    monkeypatch.setattr(menu, "list_overrides_for_employee", lambda *args: [])
    monkeypatch.setattr(registry, "_active_override", lambda *args: None)
    return record

@pytest.mark.parametrize("role", ["SALES", "SERVICE", "MARKETING", "FINANCE", "OPERATIONS", "ADMIN", None])
def test_all_read_views_use_target_role(target, role):
    target["role"] = role
    expected = registry.get_effective_permissions(role, "EMP-SYN")
    assert menu.users("ADMIN", "EMP-SYN")["identity_and_access"]["effective_permissions"] == expected
    assert menu.roles_permissions("ADMIN", "EMP-SYN")["effective_permissions"] == expected
    assert api.get_effective_permissions_api("ADMIN", "EMP-VIEWER", "EMP-SYN")["permissions"] == expected
    if role != "ADMIN":
        assert any(not row["role_default"] for row in expected)

def test_override_still_belongs_to_target_and_inspection_does_not_write(target, monkeypatch):
    key = registry.get_effective_permissions("SALES", "EMP-SYN")[0]["key"]
    monkeypatch.setattr(registry, "_active_override", lambda employee, permission:
                        SimpleNamespace(attributes={"granted": False}) if employee == "EMP-SYN" and permission == key else None)
    result = api.get_effective_permissions_api("ADMIN", "EMP-VIEWER", "EMP-SYN")
    entry = next(row for row in result["permissions"] if row["key"] == key)
    assert entry["overridden"] and not entry["effective"]
    assert target == {"role": "SALES"}

def test_self_view_and_cross_employee_gate_are_preserved(target):
    assert api.get_effective_permissions_api("SALES", "EMP-SYN")["permissions"] == registry.get_effective_permissions("SALES", "EMP-SYN")
    assert "error" in api.get_effective_permissions_api("SALES", "EMP-SYN", "EMP-OTHER")
    missing = api.get_effective_permissions_api("ADMIN", "EMP-VIEWER", "EMP-MISSING")["permissions"]
    assert not any(row["role_default"] for row in missing)
