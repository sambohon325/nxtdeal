import csv

from core.entities import Entity
from core.dealeros import (
    ledger,
    registry,
    id_generator
)

from core.entity_types import (
    FINANCE_CONTRACT,
    LENDER
)

from core.relationships import Relationship

from core.relationship_types import (
    FINANCED_BY,
    FUNDED_BY,
    COVERS,
    OWNS
)


def import_finance(csv_path):

    created = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            finance_id = id_generator.generate(
                "FIN"
            )

            finance_entity = Entity(
                id=finance_id,
                entity_type=FINANCE_CONTRACT,
                attributes=dict(row)
            )

            ledger.add_entity(
                finance_entity
            )

            registry.register_finance(
                row["FinanceNumber"],
                finance_id
            )

            customer = registry.find_customer(
                row["CustomerID"]
            )

            vehicle = registry.find_vehicle(
                row["VIN"]
            )

            lender_name = row["LenderName"]

            lender = registry.find_lender(
                lender_name
            )

            if not lender:

                lender = id_generator.generate(
                    "LENDER"
                )

                ledger.add_entity(
                    Entity(
                        id=lender,
                        entity_type=LENDER,
                        attributes={
                            "Name": lender_name
                        }
                    )
                )

                registry.register_lender(
                    lender_name,
                    lender
                )

            if customer:

                ledger.add_relationship(
                    Relationship(
                        source_id=customer,
                        target_id=finance_id,
                        relationship_type=FINANCED_BY
                    )
                )

                if vehicle:

                    ledger.add_relationship(
                        Relationship(
                            source_id=customer,
                            target_id=vehicle,
                            relationship_type=OWNS
                        )
                    )

            if vehicle:

                ledger.add_relationship(
                    Relationship(
                        source_id=finance_id,
                        target_id=vehicle,
                        relationship_type=COVERS
                    )
                )

            ledger.add_relationship(
                Relationship(
                    source_id=finance_id,
                    target_id=lender,
                    relationship_type=FUNDED_BY
                )
            )

            created += 1

    return created