from imports.employee_import import (
    import_employees
)

from core.dealeros import ledger

count = import_employees(
    "data/employees/employees.csv"
)

print(
    f"Employees Imported: {count}"
)

for entity in ledger.get_all().values():

    if entity.entity_type == "Employee":

        print(entity)