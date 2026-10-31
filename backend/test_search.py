from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance
from imports.document_import import import_documents

from core.queries import search_graph

import_inventory(
    "data/inventory/inventory.csv"
)

import_customers(
    "data/customers/customers.csv"
)

import_finance(
    "data/finance/finance.csv"
)

import_documents(
    "data/documents/documents.csv"
)

results = search_graph(
    "john"
)

print("Results")

print()

for entity in results:

    print(entity)