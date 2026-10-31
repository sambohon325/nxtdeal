"""
User / employee management (Bumper parity, 2026-07-25).

Until now the only way to add a person to NXTDeal was the CSV employee importer plus a
separate admin credential call -- there was no "create a user, give them a role, hand
them a login" flow. Bumper (and NXTDeal onboarding staff) expect exactly that: one
action that creates the Employee record AND the login, assigns a role, and returns a
temp password to relay. This module is the Employee-entity half; core/user_management_api.py
composes it with the credential store so create_user does both in one gated call.

Two systems are deliberately kept distinct (see core/auth.py + core/permissions.py): the
Employee *entity* in the graph (identity, department, title -- what dashboards read) and
the *credential* record (password + auth role -- what login reads). A NXTDeal "user" is
the pairing of the two, keyed by the same employee_id.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator, registry
from core.entities import Entity
from core.entity_types import EMPLOYEE


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_employee(first_name, last_name, email, department="", title="", created_by=None):
    """Create an Employee entity matching the CSV importer's attribute shape
    (EmployeeID/FirstName/LastName/Department/Title/Email) so every dashboard that reads
    those keys sees a hand-created employee identically to an imported one. Registers the
    business key so registry.find_employee / relationship wiring resolve it."""
    emp_id = id_generator.generate("EMP")
    attributes = {
        "EmployeeID": emp_id,
        "FirstName": first_name,
        "LastName": last_name,
        "Email": email or "",
        "Department": department or "",
        "Title": title or "",
        "CreatedBy": created_by,
        "CreatedAt": _now(),
    }
    entity = Entity(id=emp_id, entity_type=EMPLOYEE, attributes=attributes)
    ledger.add_entity(entity)
    registry.register_employee(emp_id, emp_id)
    return entity


def get_employee(employee_id):
    e = ledger.get_entity(employee_id)
    return e if e and e.entity_type == EMPLOYEE else None


def list_employees():
    return [e for e in ledger.get_all().values() if e.entity_type == EMPLOYEE]


def _display_name(entity):
    a = entity.attributes
    name = f"{a.get('FirstName', '')} {a.get('LastName', '')}".strip()
    return name or a.get("Email", "") or entity.id
