from imports.inventory_import import import_inventory
from imports.customer_import import import_customers

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

customers = search_graph(
    "john"
)

for customer in customers:

    print(customer)

    print()

    graph = get_graph_view(
        customer.id
    )

    for relationship in graph["relationships"]:

        print(
            relationship["relationship"]
        )

        print(
            relationship["entity"]
        )

        print()