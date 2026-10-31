from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.lead_import import import_leads
from imports.finance_import import import_finance
from imports.service_import import import_service
from imports.document_import import import_documents
from imports.image_import import import_images
from imports.employee_import import import_employees

from core.queries import get_executive_dashboard

import_inventory(
    "data/inventory/inventory.csv"
)

import_customers(
    "data/customers/customers.csv"
)

import_leads(
    "data/leads/leads.csv"
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

import_employees(
    "data/employees/employees.csv"
)

dashboard = get_executive_dashboard()

print("Executive Dashboard")

print()

for key, value in dashboard.items():

    print(
        f"{key}: {value}"
    )