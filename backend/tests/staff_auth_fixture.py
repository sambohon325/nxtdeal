"""Create a real fictional credential before issuing route-test sessions."""
from core.auth import credential_store, issue_token


def staff_token(employee_id, role):
    record = credential_store.get_record(employee_id)
    if not record or record.get("role") != role:
        credential_store.set_credential(employee_id, "Fictional-test-password2026!", role, must_change_password=False)
    return issue_token(employee_id, role)
