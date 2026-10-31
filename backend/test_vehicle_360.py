from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance
from imports.service_import import import_service
from imports.document_import import import_documents
from imports.image_import import import_images

from core.queries import get_vehicle_360

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

import_images(
    "data/images/images.csv"
)

profile = get_vehicle_360(
    "VEH-00001"
)

print("Vehicle")
print(profile["vehicle"])

print()

print("Owners")

for owner in profile["owners"]:
    print(owner)

print()

print("Finance Contracts")

for finance in profile["finance_contracts"]:
    print(finance)

print()

print("Service Records")

for service_record in profile["service_records"]:
    print(service_record)

print()

print("Documents")

for document in profile["documents"]:
    print(document)

print()

print("Images")

for image in profile["images"]:
    print(image)