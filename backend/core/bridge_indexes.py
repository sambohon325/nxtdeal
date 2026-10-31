"""Ephemeral validation indexes; rebuilt for every preview under the Bridge lock.

No cache survives a validation call, so changes between review and activation
still invalidate the preview. Vendor-specific fields never enter this module.
"""
from core.bridge_contracts import GRAPH_ALIASES, storage_kind, timestamp


def identity_value(value):
    """One conservative candidate key shared by graph and within-batch checks."""
    return str(value).strip().casefold() if value is not None else ""


class ValidationIndex:
    def __init__(self, entities, workspace_id, kind, external_keys=()):
        self.identities = {}
        self.order = {}
        self.observations = {}
        aliases = GRAPH_ALIASES.get(kind, {})
        external_keys = set(external_keys)
        for position, entity in enumerate(entities):
            attributes = entity.attributes
            if attributes.get("workspace_id", workspace_id) != workspace_id:
                continue
            if entity.entity_type == storage_kind(kind):
                self.order[entity.id] = position
                for field in ("email", "vin"):
                    for value in (attributes.get(field), attributes.get(aliases.get(field))):
                        normalized = identity_value(value)
                        if normalized:
                            self.identities.setdefault((field, normalized), set()).add(entity.id)
            if entity.entity_type == "SourceObservation" and attributes.get("external_key") in external_keys:
                self.observations.setdefault(attributes["external_key"], []).append(attributes)

    def candidates(self, values):
        matches = set()
        for field in ("email", "vin"):
            normalized = identity_value(values.get(field))
            if normalized:
                matches.update(self.identities.get((field, normalized), ()))
        # Match the repository's stable enumeration order, including legacy aliases.
        return sorted(matches, key=self.order.__getitem__)

    def historical_values(self, external_key, source_timestamp):
        instant = timestamp(source_timestamp)
        return [event["values"] for event in self.observations.get(external_key, ())
                if timestamp(event["source_timestamp"]) == instant]
