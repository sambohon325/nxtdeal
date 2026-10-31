from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance
from imports.service_import import import_service
from imports.document_import import import_documents

from core.dealeros import ledger

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

count = import_documents(
    "data/documents/documents.csv"
)

print(
    f"Documents Imported: {count}"
)

for relationship in ledger.get_relationships():

    if relationship.relationship_type == "HAS_DOCUMENT":

        print(relationship)