from imports.employee_import import import_employees
from imports.management_import import import_management

from core.queries import get_manager_360

import_employees(
    "data/employees/employees.csv"
)

import_management(
    "data/management/management.csv"
)

profile = get_manager_360(
    "EMP-00001"
)

print("Manager")
print(profile["manager"])

print()

print("Direct Reports")

for employee in profile["direct_reports"]:
    print(employee)