from core.storage import load_graph
from core.queries import search_graph

load_graph(
    "storage/graph.json"
)

results = search_graph(
    "john"
)

print("Results")

print()

for entity in results:

    print(entity)