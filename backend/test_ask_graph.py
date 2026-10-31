from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance
from imports.service_import import import_service
from imports.document_import import import_documents

from core.queries import ask_graph

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

results = ask_graph(
    "john"
)

for result in results:

    print()

    print("Entity")
    print(result["entity"])

    print()

    print("Related")

    for relationship in result["graph"]["relationships"]:

        print(
            f"{relationship['relationship']}"
        )

        print(
            relationship["entity"]
        )

        print()
def ask_question(question):

    question = question.lower()

    if "finance" in question:

        results = search_graph(
            question.replace(
                "show finance for",
                ""
            ).strip()
        )

        return {
            "type": "finance",
            "results": results
        }

    if "service" in question:

        results = search_graph(
            question.replace(
                "show service records for",
                ""
            ).strip()
        )

        return {
            "type": "service",
            "results": results
        }

    return {
        "type": "search",
        "results": search_graph(
            question
        )
    }