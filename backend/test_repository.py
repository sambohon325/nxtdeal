from core.storage import load_graph
from core.repository import repository

load_graph(
    "storage/graph.json"
)

print("Get Entity")

print(
    repository.get_entity(
        "CUST-00001"
    )
)

print()

print(
    "Entity Count:",
    len(
        repository.get_entities()
    )
)

print()

print(
    "Relationship Count:",
    len(
        repository.get_relationships()
    )
)