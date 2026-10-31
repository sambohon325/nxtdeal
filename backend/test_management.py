from imports.employee_import import import_employees
from imports.management_import import import_management

from core.dealeros import ledger

import_employees(
    "data/employees/employees.csv"
)

count = import_management(
    "data/management/management.csv"
)

print(
    f"Management Relationships Imported: {count}"
)

for relationship in ledger.get_relationships():

    if relationship.relationship_type == "MANAGED_BY":

        print(relationship)