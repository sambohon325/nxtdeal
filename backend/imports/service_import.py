import csv

from core.entities import Entity
from core.dealeros import (
    ledger,
    registry,
    id_generator
)

from core.entity_types import SERVICE_RECORD

from core.relationships import Relationship

from core.relationship_types import (
    HAS_SERVICE_RECORD,
    AUTHORIZED
)


def import_service(csv_path):

    created = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            service_id = id_generator.generate(
                "SRV"
            )

            attributes = dict(row)

            # Resolve the CSV's business-key Technician (e.g. "E3032") to the real graph
            # Employee id (e.g. "EMP-00032") -- core/employee_value.py's
            # _real_service_value() attributes gross profit by comparing
            # ServiceRecord.Technician against a real Employee entity id, so leaving the
            # raw business key here would silently make every technician's real-value
            # attribution zero. Falls back to the raw value if the technician key isn't
            # a registered employee (keeps this importer tolerant of hand-edited CSVs).
            technician_key = attributes.get("Technician")

            if technician_key:

                technician_id = registry.find_employee(technician_key)

                if technician_id:
                    attributes["Technician"] = technician_id

            service_record = Entity(
                id=service_id,
                entity_type=SERVICE_RECORD,
                attributes=attributes
            )

            ledger.add_entity(
                service_record
            )

            customer = registry.find_customer(
                row["CustomerID"]
            )

            vehicle = registry.find_vehicle(
                row["VIN"]
            )

            if customer:

                ledger.add_relationship(
                    Relationship(
                        source_id=customer,
                        target_id=service_id,
                        relationship_type=AUTHORIZED
                    )
                )

            if vehicle:

                ledger.add_relationship(
                    Relationship(
                        source_id=vehicle,
                        target_id=service_id,
                        relationship_type=HAS_SERVICE_RECORD
                    )
                )

            created += 1

    return created
