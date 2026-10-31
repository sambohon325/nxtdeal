"""Record-scoped rollback for the existing mutable graph, not a SQL transaction.

Only records explicitly touched by a bridge mutation are journaled. A failed
save never swaps the entire ledger or erases unrelated concurrent work. Changed
fields are restored only if their value still equals the bridge's attempted value.
Same-field conflicts are surfaced for review instead of overwriting newer data.
"""
from contextvars import ContextVar
from copy import deepcopy

from core.dealeros import ledger

_ACTIVE = ContextVar("dealer_bridge_mutation_journal", default=None)
_MISSING = object()


class PersistenceConflict(RuntimeError):
    pass


class PersistenceUnavailable(OSError):
    """A snapshot save failed; public callers must not expose OS diagnostics."""


class Journal:
    def __init__(self):
        self.before = {}

    def touch(self, record_id):
        if record_id not in self.before:
            self.before[record_id] = deepcopy(ledger.get_entity(record_id))

    def changes(self):
        return {key: deepcopy(ledger.get_entity(key)) for key, previous in self.before.items()
                if ledger.get_entity(key) != previous}

    def rollback(self, attempted):
        conflicts = []
        for key, after in attempted.items():
            before = self.before[key]
            current = ledger.get_entity(key)
            if before is None:
                if current == after:
                    ledger.entities.pop(key, None)
                elif current is not None:
                    conflicts.append(key)
                continue
            if after is None:
                if current is None:
                    ledger.add_entity(deepcopy(before))
                else:
                    conflicts.append(key)
                continue
            if current is None or current.entity_type != after.entity_type:
                conflicts.append(key)
                continue
            if before.entity_type != after.entity_type:
                if current == after:
                    current.entity_type = before.entity_type
                else:
                    conflicts.append(key)
            for field in set(before.attributes) | set(after.attributes):
                prior = before.attributes.get(field, _MISSING)
                proposed = after.attributes.get(field, _MISSING)
                if prior == proposed:
                    continue
                actual = current.attributes.get(field, _MISSING)
                if actual != proposed:
                    conflicts.append(key)
                    continue
                if prior is _MISSING:
                    current.attributes.pop(field, None)
                else:
                    current.attributes[field] = deepcopy(prior)
        return sorted(set(conflicts))


def current():
    return _ACTIVE.get()


def begin():
    journal = Journal()
    return journal, _ACTIVE.set(journal)


def end(token):
    _ACTIVE.reset(token)


def touch(record_id):
    journal = current()
    if journal is not None:
        journal.touch(record_id)


def put(entity):
    touch(entity.id)
    ledger.add_entity(entity)
