from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance
from imports.service_import import import_service
from imports.document_import import import_documents
from imports.image_import import import_images

from core.queries import get_graph_tree

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

tree = get_graph_tree(
    "CUST-00001",
    depth=2
)


def print_tree(node, indent=0):

    if not node:

        return

    print(
        " " * indent +
        f"{node['entity'].entity_type}: "
        f"{node['entity'].id}"
    )

    for child in node["children"]:

        print(
            " " * (indent + 2) +
            f"└─ {child['relationship']}"
        )

        print_tree(
            child["node"],
            indent + 4
        )


print_tree(tree)