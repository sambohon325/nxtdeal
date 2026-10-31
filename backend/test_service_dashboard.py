from imports.inventory_import import import_inventory
from imports.service_import import import_service
from imports.document_import import import_documents
from imports.image_import import import_images

from core.queries import get_service_dashboard

import_inventory(
    "data/inventory/inventory.csv"
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

dashboard = get_service_dashboard()

print("Service Dashboard")

print()

print(
    f"Service Records: {dashboard['service_record_count']}"
)

print(
    f"Vehicles: {dashboard['vehicle_count']}"
)

print(
    f"Documents: {dashboard['document_count']}"
)

print(
    f"Images: {dashboard['image_count']}"
)