"""Legacy persistence entry points over the canonical ledger facade."""

import re

from core.dealeros import ledger, id_generator
from core.json_graph_repository import demo_persistence_disabled


def save_graph(filepath):
    # Retain the public patch point and demo guard used by existing callers.
    if demo_persistence_disabled():
        return
    ledger.save(filepath)


def load_graph(filepath):
    if ledger.load(filepath):
        _recover_id_counters()


# IDGenerator.counters starts every one of its prefixes at 0 on process start
# (core/id_generator.py) -- it has no idea graph.json already has, say, 500 VEH-xxxxx
# entities in it. Without this, the first live-created Vehicle/Deal/Lead/etc. after any
# server restart would generate "VEH-00001" again and DealerLedger.add_entity() (a
# plain `self.entities[entity.id] = entity` dict write, no collision check) would
# silently overwrite the real, already-imported VEH-00001 entity -- a real bug found
# while wiring up the quick-entry intake endpoints below (session 47), which are the
# first live-create paths for prefixes (VEH/LEAD/SRV) that already have hundreds of
# pre-existing seeded rows. Fixed generically for every prefix, not just the new ones,
# by scanning every loaded entity's id ("PREFIX-00123") and bumping that prefix's
# counter to at least the highest number seen.
_ID_PATTERN = re.compile(r"^([A-Z]+)-(\d+)$")


def _recover_id_counters():

    for entity in ledger.get_all().values():

        match = _ID_PATTERN.match(entity.id)

        if not match:
            continue

        prefix, number = match.group(1), int(match.group(2))

        id_generator.reserve_at_least(prefix, number)
