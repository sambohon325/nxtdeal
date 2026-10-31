from collections import defaultdict

from core.repository import repository


class RelationshipIndex:

    def __init__(self):

        self.by_source = defaultdict(
            list
        )

        self.by_target = defaultdict(
            list
        )

    def build(self):

        self.by_source.clear()
        self.by_target.clear()

        for relationship in (
            repository.get_relationships()
        ):

            self.by_source[
                relationship.source_id
            ].append(
                relationship
            )

            self.by_target[
                relationship.target_id
            ].append(
                relationship
            )

    def get_by_source(
        self,
        entity_id
    ):

        return self.by_source[
            entity_id
        ]

    def get_by_target(
        self,
        entity_id
    ):

        return self.by_target[
            entity_id
        ]


relationship_index = (
    RelationshipIndex()
)