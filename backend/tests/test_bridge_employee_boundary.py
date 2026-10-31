"""Employee directory observations cannot provision logins or import access grants."""
from copy import deepcopy
import pytest
from core import dealer_bridge as b
from core.auth import credential_store
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, isolated  # noqa: F401


@pytest.mark.parametrize("field", ["role","Role","password","email_login","permissions","workspace_id","tenant_id","mfa_enabled"])
def test_employee_mapping_cannot_include_authentication_or_access_fields(field):
    system = b.connect(A,"CSV","Synthetic employee export")["id"]
    before = deepcopy(ledger.entities)
    with pytest.raises(ValueError):
        b.propose_mapping(A,system,"Employee","employees",{field:{"source":"value","transform":"text"}})
    assert ledger.entities == before


def test_employee_import_does_not_create_or_modify_credentials_even_with_admin_department(monkeypatch):
    monkeypatch.setattr(credential_store,"credentials",{})
    credential_store.set_credential("source-admin","Synthetic-Existing-Only-2026!","SALES",must_change_password=False)
    prior = deepcopy(credential_store.credentials)
    system = b.connect(A,"CSV","Synthetic workforce export")["id"]
    mapping = b.propose_mapping(A,system,"Employee","employees",{
        "first_name":{"source":"name","transform":"text"},
        "department":{"source":"department","transform":"text"}})["id"]
    b.approve_mapping(B,mapping)
    content = "external_id,modified_at,name,department,role,password\nsource-admin,2026-10-04T12:00:00Z,Synthetic employee,ADMIN,ADMIN,synthetic-unselected-password\n"
    job = b.stage(A,mapping,content)["id"]
    assert b.validate(A,job)[0]["status"] == "ready"
    b.activate(B,job)
    employees = [e for e in ledger.get_all().values() if e.entity_type == "Employee"]
    assert len(employees) == 1
    employee = employees[0]
    assert employee.attributes["department"] == employee.attributes["Department"] == "ADMIN"
    assert employee.id != "source-admin"
    assert credential_store.get_record(employee.id) is None
    assert credential_store.credentials == prior
    assert credential_store.authenticate(employee.id,"synthetic-unselected-password") is None
    assert not {"role","Role","password","permissions"} & employee.attributes.keys()
    assert "synthetic-unselected-password" not in str(ledger.entities)
