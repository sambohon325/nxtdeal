from core.storage import load_graph
from core.indexes import (
    relationship_index
)

load_graph(
    "storage/graph.json"
)

relationship_index.build()

print(
    "Customer Relationships"
)

print()

relationships = (
    relationship_index.get_by_source(
        "CUST-00001"
    )
)

for relationship in relationships:

    print(relationship)