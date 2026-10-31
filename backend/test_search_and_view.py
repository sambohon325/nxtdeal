from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance
from imports.service_import import import_service
from imports.document_import import import_documents

from core.queries import (
    search_graph,
    get_graph_view
)

import_inventory(
    "data/inventory/inventory.csv"
)

import_customers(
    "data/customers/customers.csv"
)

import_finance(
    "data/finance/finance.csv"
)

import_service(
    "data/service/service.csv"
)

import_documents(
    "data/documents/documents.csv"
)

results = search_graph(
    "john"
)

print("Search Results")
print()

for entity in results:

    print(entity)

    print()

    graph = get_graph_view(
        entity.id
    )

    print("Relationships")

    for relationship in graph["relationships"]:

        print(
            relationship["direction"],
            relationship["relationship"]
        )

        print(
            relationship["entity"]
        )

    print()
    print("-" * 40)