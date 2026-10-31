from core.dealeros import ledger


def get_entity(entity_id):

    return ledger.get_entity(entity_id)


def get_entity_relationships(entity_id):

    return [
        relationship
        for relationship in ledger.get_relationships()
        if relationship.source_id == entity_id
        or relationship.target_id == entity_id
    ]


def get_connected_entities(entity_id):

    connected = []

    for relationship in ledger.get_relationships():

        if relationship.source_id == entity_id:

            connected.append(
                relationship.target_id
            )

        elif relationship.target_id == entity_id:

            connected.append(
                relationship.source_id
            )

    return connected


def find_entities_by_type(entity_type):

    results = []

    for entity in ledger.get_all().values():

        if entity.entity_type == entity_type:

            results.append(entity)

    return results


def get_customer_profile(customer_id):

    customer = ledger.get_entity(
        customer_id
    )

    relationships = get_entity_relationships(
        customer_id
    )

    return {
        "customer": customer,
        "relationships": relationships
    }


def get_customer_360(customer_id):

    customer = ledger.get_entity(
        customer_id
    )

    relationships = get_entity_relationships(
        customer_id
    )

    profile = {
        "customer": customer,
        "finances": [],
        "service_records": [],
        "vehicles": [],
        "lead_sources": [],
        "documents": []
    }

    for relationship in relationships:

        if relationship.relationship_type == "FINANCED_BY":

            finance = ledger.get_entity(
                relationship.target_id
            )

            profile["finances"].append(
                finance
            )

            for finance_relationship in ledger.get_relationships():

                if (
                    finance_relationship.source_id == finance.id
                    and finance_relationship.relationship_type == "COVERS"
                ):

                    vehicle = ledger.get_entity(
                        finance_relationship.target_id
                    )

                    profile["vehicles"].append(
                        vehicle
                    )

        elif relationship.relationship_type == "AUTHORIZED":

            service_record = ledger.get_entity(
                relationship.target_id
            )

            profile["service_records"].append(
                service_record
            )

        elif relationship.relationship_type == "BECAME":

            lead = ledger.get_entity(
                relationship.source_id
            )

            profile["lead_sources"].append(
                lead
            )

        elif relationship.relationship_type == "HAS_DOCUMENT":

            document = ledger.get_entity(
                relationship.target_id
            )

            profile["documents"].append(
                document
            )

    return profile


def get_vehicle_360(vehicle_id):

    vehicle = ledger.get_entity(
        vehicle_id
    )

    relationships = get_entity_relationships(
        vehicle_id
    )

    profile = {
        "vehicle": vehicle,
        "owners": [],
        "finance_contracts": [],
        "service_records": [],
        "documents": [],
        "images": []
    }

    for relationship in relationships:

        if relationship.relationship_type == "OWNS":

            owner = ledger.get_entity(
                relationship.source_id
            )

            profile["owners"].append(
                owner
            )

        elif relationship.relationship_type == "COVERS":

            finance = ledger.get_entity(
                relationship.source_id
            )

            profile["finance_contracts"].append(
                finance
            )

        elif relationship.relationship_type == "HAS_SERVICE_RECORD":

            service_record = ledger.get_entity(
                relationship.target_id
            )

            profile["service_records"].append(
                service_record
            )

        elif relationship.relationship_type == "HAS_DOCUMENT":

            document = ledger.get_entity(
                relationship.target_id
            )

            profile["documents"].append(
                document
            )

        elif relationship.relationship_type == "HAS_IMAGE":

            image = ledger.get_entity(
                relationship.target_id
            )

            profile["images"].append(
                image
            )

    return profile


def get_employee_360(employee_id):

    employee = ledger.get_entity(
        employee_id
    )

    relationships = get_entity_relationships(
        employee_id
    )

    profile = {
        "employee": employee,
        "customers": [],
        "leads": []
    }

    for relationship in relationships:

        if relationship.relationship_type == "ASSIGNED_TO":

            entity = ledger.get_entity(
                relationship.target_id
            )

            if entity:

                if entity.entity_type == "Customer":

                    profile["customers"].append(
                        entity
                    )

                elif entity.entity_type == "Lead":

                    profile["leads"].append(
                        entity
                    )

    return profile


def get_manager_360(manager_id):

    manager = ledger.get_entity(
        manager_id
    )

    profile = {
        "manager": manager,
        "direct_reports": []
    }

    for relationship in ledger.get_relationships():

        if (
            relationship.relationship_type == "MANAGED_BY"
            and relationship.target_id == manager_id
        ):

            employee = ledger.get_entity(
                relationship.source_id
            )

            profile["direct_reports"].append(
                employee
            )

    return profile


def get_team_360(manager_id):

    manager = ledger.get_entity(
        manager_id
    )

    profile = {
        "manager": manager,
        "direct_reports": [],
        "customers": [],
        "leads": []
    }

    for relationship in ledger.get_relationships():

        if (
            relationship.relationship_type == "MANAGED_BY"
            and relationship.target_id == manager_id
        ):

            employee = ledger.get_entity(
                relationship.source_id
            )

            profile["direct_reports"].append(
                employee
            )

            employee_relationships = (
                get_entity_relationships(
                    employee.id
                )
            )

            for employee_relationship in employee_relationships:

                if (
                    employee_relationship.relationship_type
                    == "ASSIGNED_TO"
                ):

                    entity = ledger.get_entity(
                        employee_relationship.target_id
                    )

                    if entity:

                        if entity.entity_type == "Customer":

                            profile["customers"].append(
                                entity
                            )

                        elif entity.entity_type == "Lead":

                            profile["leads"].append(
                                entity
                            )

    profile["employee_count"] = (
        len(profile["direct_reports"])
    )

    profile["customer_count"] = (
        len(profile["customers"])
    )

    profile["lead_count"] = (
        len(profile["leads"])
    )

    return profile
def get_sales_dashboard():

    dashboard = {
        "employee_count": 0,
        "customer_count": 0,
        "lead_count": 0,
        "vehicle_count": 0,
        "finance_count": 0
    }

    for entity in ledger.get_all().values():

        if entity.entity_type == "Employee":

            dashboard["employee_count"] += 1

        elif entity.entity_type == "Customer":

            dashboard["customer_count"] += 1

        elif entity.entity_type == "Lead":

            dashboard["lead_count"] += 1

        elif entity.entity_type == "Vehicle":

            dashboard["vehicle_count"] += 1

        elif entity.entity_type == "FinanceContract":

            dashboard["finance_count"] += 1

    return dashboard


def get_service_dashboard():

    dashboard = {
        "service_record_count": 0,
        "vehicle_count": 0,
        "document_count": 0,
        "image_count": 0
    }

    for entity in ledger.get_all().values():

        if entity.entity_type == "ServiceRecord":

            dashboard["service_record_count"] += 1

        elif entity.entity_type == "Vehicle":

            dashboard["vehicle_count"] += 1

        elif entity.entity_type == "Document":

            dashboard["document_count"] += 1

        elif entity.entity_type == "Image":

            dashboard["image_count"] += 1

    return dashboard


def get_finance_dashboard():

    dashboard = {
        "finance_contract_count": 0,
        "customer_count": 0,
        "vehicle_count": 0,
        "lender_count": 0
    }

    for entity in ledger.get_all().values():

        if entity.entity_type == "FinanceContract":

            dashboard["finance_contract_count"] += 1

        elif entity.entity_type == "Customer":

            dashboard["customer_count"] += 1

        elif entity.entity_type == "Vehicle":

            dashboard["vehicle_count"] += 1

        elif entity.entity_type == "Lender":

            dashboard["lender_count"] += 1

    return dashboard


def get_executive_dashboard():

    dashboard = {
        "employees": 0,
        "customers": 0,
        "leads": 0,
        "vehicles": 0,
        "finance_contracts": 0,
        "service_records": 0,
        "documents": 0,
        "images": 0,
        "lenders": 0
    }

    for entity in ledger.get_all().values():

        if entity.entity_type == "Employee":

            dashboard["employees"] += 1

        elif entity.entity_type == "Customer":

            dashboard["customers"] += 1

        elif entity.entity_type == "Lead":

            dashboard["leads"] += 1

        elif entity.entity_type == "Vehicle":

            dashboard["vehicles"] += 1

        elif entity.entity_type == "FinanceContract":

            dashboard["finance_contracts"] += 1

        elif entity.entity_type == "ServiceRecord":

            dashboard["service_records"] += 1

        elif entity.entity_type == "Document":

            dashboard["documents"] += 1

        elif entity.entity_type == "Image":

            dashboard["images"] += 1

        elif entity.entity_type == "Lender":

            dashboard["lenders"] += 1

    return dashboard


def get_graph_view(entity_id):

    entity = ledger.get_entity(
        entity_id
    )

    relationships = []

    for relationship in ledger.get_relationships():

        if relationship.source_id == entity_id:

            target = ledger.get_entity(
                relationship.target_id
            )

            relationships.append({
                "direction": "OUT",
                "relationship": relationship.relationship_type,
                "entity": target
            })

        elif relationship.target_id == entity_id:

            source = ledger.get_entity(
                relationship.source_id
            )

            relationships.append({
                "direction": "IN",
                "relationship": relationship.relationship_type,
                "entity": source
            })

    return {
        "entity": entity,
        "relationships": relationships
    }


def search_graph(search_text):

    results = []

    search_text = search_text.lower()

    for entity in ledger.get_all().values():

        for value in entity.attributes.values():

            if search_text in str(value).lower():

                results.append(
                    entity
                )

                break

    return results
def get_graph_tree(entity_id, depth=2):

    visited = set()

    def traverse(current_id, current_depth):

        if current_depth > depth:

            return None

        if current_id in visited:

            return None

        visited.add(
            current_id
        )

        entity = ledger.get_entity(
            current_id
        )

        if not entity:

            return None

        node = {
            "entity": entity,
            "children": []
        }

        for relationship in ledger.get_relationships():

            next_id = None

            if relationship.source_id == current_id:

                next_id = relationship.target_id

            elif relationship.target_id == current_id:

                next_id = relationship.source_id

            if next_id:

                child = traverse(
                    next_id,
                    current_depth + 1
                )

                if child:

                    node["children"].append(
                        {
                            "relationship":
                            relationship.relationship_type,
                            "node": child
                        }
                    )

        return node

    return traverse(
        entity_id,
        0
    )
def ask_graph(search_text):

    matches = search_graph(
        search_text
    )

    results = []

    for entity in matches:

        graph = get_graph_view(
            entity.id
        )

        results.append({
            "entity": entity,
            "graph": graph
        })

    return results
def ask_question(question):

    question = question.lower()

    if "finance" in question:

        search_text = (
            question.replace(
                "show finance for",
                ""
            ).strip()
        )

        customers = search_graph(
            search_text
        )

        results = []

        for customer in customers:

            graph = get_graph_view(
                customer.id
            )

            for relationship in graph["relationships"]:

                if (
                    relationship["relationship"]
                    == "FINANCED_BY"
                ):

                    results.append(
                        relationship["entity"]
                    )

        return {
            "type": "finance",
            "results": results
        }

    if "lender" in question:

        search_text = (
            question.replace(
                "show lender for",
                ""
            ).strip()
        )

        customers = search_graph(
            search_text
        )

        results = []

        for customer in customers:

            graph = get_graph_view(
                customer.id
            )

            for relationship in graph["relationships"]:

                if (
                    relationship["relationship"]
                    == "FINANCED_BY"
                ):

                    finance = relationship["entity"]

                    finance_graph = get_graph_view(
                        finance.id
                    )

                    for finance_relationship in (
                        finance_graph["relationships"]
                    ):

                        if (
                            finance_relationship[
                                "relationship"
                            ]
                            == "FUNDED_BY"
                        ):

                            results.append(
                                finance_relationship[
                                    "entity"
                                ]
                            )

        return {
            "type": "lender",
            "results": results
        }

    if "vehicle" in question:

        search_text = (
            question.replace(
                "show vehicle for",
                ""
            )
            .replace(
                "show vehicles for",
                ""
            )
            .strip()
        )

        customers = search_graph(
            search_text
        )

        results = []

        for customer in customers:

            graph = get_graph_view(
                customer.id
            )

            for relationship in graph["relationships"]:

                if (
                    relationship["relationship"]
                    == "OWNS"
                ):

                    results.append(
                        relationship["entity"]
                    )

        return {
            "type": "vehicle",
            "results": results
        }

    if "service" in question:

        search_text = (
            question.replace(
                "show service records for",
                ""
            ).strip()
        )

        customers = search_graph(
            search_text
        )

        results = []

        for customer in customers:

            graph = get_graph_view(
                customer.id
            )

            for relationship in graph["relationships"]:

                if (
                    relationship["relationship"]
                    == "AUTHORIZED"
                ):

                    results.append(
                        relationship["entity"]
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