from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance
from imports.service_import import import_service
from imports.document_import import import_documents

from core.queries import get_customer_360

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

profile = get_customer_360(
    "CUST-00001"
)

print("Customer")
print(profile["customer"])

print()

print("Finances")

for finance in profile["finances"]:
    print(finance)

print()

print("Service Records")

for service_record in profile["service_records"]:
    print(service_record)

print()

print("Vehicles")

for vehicle in profile["vehicles"]:
    print(vehicle)

print()

print("Lead Sources")

for lead in profile["lead_sources"]:
    print(lead)

print()

print("Documents")

for document in profile["documents"]:
    print(document)