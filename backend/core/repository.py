from core.dealeros import ledger


class GraphRepository:

    def get_entity(
        self,
        entity_id
    ):

        return ledger.get_entity(
            entity_id
        )

    def get_entities(self):

        return list(
            ledger.get_all().values()
        )

    def get_relationships(self):

        return ledger.get_relationships()


repository = GraphRepository()