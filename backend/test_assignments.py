from imports.employee_import import import_employees
from imports.assignment_import import import_assignments

from core.dealeros import ledger

import_employees(
    "data/employees/employees.csv"
)

count = import_assignments(
    "data/assignments/assignments.csv"
)

print(f"Assignments Imported: {count}")

for relationship in ledger.get_relationships():

    if relationship.relationship_type == "ASSIGNED_TO":

        print(relationship)