import csv

from core.entities import Entity

from core.dealeros import (
    ledger,
    registry,
    id_generator
)

from core.entity_types import EMPLOYEE


def import_employees(csv_path):

    created = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            employee_id = id_generator.generate(
                "EMP"
            )

            employee = Entity(
                id=employee_id,
                entity_type=EMPLOYEE,
                attributes=dict(row)
            )

            ledger.add_entity(
                employee
            )

            # Register the source CSV's business key (e.g. "E2003") so other importers
            # (imports/lead_import.py's AssignedSalesperson column) can look employees up
            # by that key instead of the auto-generated graph ID — same pattern as
            # register_vehicle/register_customer/register_lead below.
            if "EmployeeID" in row:

                registry.register_employee(
                    row["EmployeeID"],
                    employee_id
                )

            created += 1

    return created