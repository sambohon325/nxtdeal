from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance
from imports.service_import import import_service
from imports.document_import import import_documents

from core.queries import get_graph_view

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

graph = get_graph_view(
    "CUST-00001"
)

print("Entity")
print(graph["entity"])

print()

print("Relationships")

for relationship in graph["relationships"]:

    print(
        f"{relationship['direction']} "
        f"{relationship['relationship']}"
    )

    print(
        relationship["entity"]
    )

    print()