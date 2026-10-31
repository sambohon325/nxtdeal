"""Explain canonical updates and legacy aliases without choosing field authority."""
from copy import deepcopy
from core.bridge_contracts import FIELDS, GRAPH_ALIASES


def snapshot(kind, attributes, fields=None):
    selected = set(FIELDS[kind]) if fields is None else set(fields) & set(FIELDS[kind])
    aliases = GRAPH_ALIASES.get(kind, {})
    values, conflicts = {}, []
    for field in sorted(selected):
        alias = aliases.get(field)
        if field in attributes:
            values[field] = deepcopy(attributes[field])
        elif alias in attributes:
            values[field] = deepcopy(attributes[alias])
        if field in attributes and alias in attributes and attributes[field] != attributes[alias]:
            conflicts.append({"field": field, "legacy_field": alias, "canonical_value": deepcopy(attributes[field]),
                              "legacy_value": deepcopy(attributes[alias])})
    return values, conflicts


def explain(kind, row, target=None):
    status = row["status"]
    effect = ("blocked" if status == "quarantined" else "none" if status == "duplicate" else
              "history_only" if status == "history" else "preserve_current" if row.get("projection") == "preserve" else
              "update" if target is not None else "create")
    proposed = row.get("values", {})
    attributes = target.attributes if target else {}
    current, conflicts = snapshot(kind, attributes, proposed)
    changes, aliases = [], GRAPH_ALIASES.get(kind, {})
    if effect in {"create", "update"}:
        for field, after in sorted(proposed.items()):
            alias = aliases.get(field)
            if (field not in current or current[field] != after or
                    alias in attributes and attributes[alias] != after):
                change = {"field": field, "before_present": field in current,
                          "before": deepcopy(current.get(field)), "after": deepcopy(after)}
                if alias in attributes and field in attributes and attributes[alias] != attributes[field]:
                    change["legacy_before"] = deepcopy(attributes[alias])
                changes.append(change)
    return {"effect": effect, "current_values": current, "legacy_conflicts": conflicts, "changes": changes}
