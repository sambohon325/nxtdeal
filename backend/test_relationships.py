from core.relationships import Relationship
from core.dealeros import ledger

ledger.add_relationship(
    Relationship(
        source_id="CUST-00001",
        target_id="VEH-00001",
        relationship_type="INTERESTED_IN"
    )
)

for relationship in ledger.get_relationships():
    print(relationship)