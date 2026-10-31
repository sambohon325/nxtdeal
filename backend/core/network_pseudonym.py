"""
Per-install network pseudonym (2026-07-16, Cowork, interactive) -- the honest half of
Sam's "encrypted so not even we can tell who's actual data it is" ask for the NXTDeal
Hub's cross-network intelligence layer.

The design constraint that makes this a real anonymization mechanism, not just a label:
this pseudonym is generated ONCE, locally, on THIS dealer's own backend instance the
first time it's needed, using a random value that never leaves this process except as
the opaque pseudonym itself. It is never derived from `dealer_id`, `Dealer.name`, or
anything else the NXTDeal Hub's own `hub/storage/dealers.json` registry already knows
about this dealer -- so even a NXTDeal engineer with full read access to BOTH the Hub's
dealer registry AND this pseudonym has no mathematical way to link the two back
together. That is a meaningfully different (and stronger) posture than a keyed hash of
`dealer_id`: a keyed hash is deterministic and reversible-by-brute-force the moment
someone (even accidentally) also holds the key and the candidate `dealer_id` list, which
the Hub always will. A locally-generated random token has no such weakness -- there is
no key or formula anywhere that maps it back to a real dealer.

Trade-off, stated plainly: this means the pseudonym is NOT stable across a dealer
reprovisioning their storage directory from scratch (a fresh `network_identity.json` =
a fresh pseudonym = the Hub sees what looks like a "new" anonymous dealer in its
aggregate stats). That's an accepted cost of genuine unlinkability, not an oversight.

Persisted to this tenant's own storage directory (via core/storage_paths.py, so a
provisioned tenant's pseudonym lives in ITS OWN storage/tenants/{id}/ directory, never
shared across tenants) as network_identity.json -- a new, deliberately separate file
from graph.json/audit.json/credentials.json, since this is identity infrastructure for
the network layer, not a graph entity or a credential.

See core/network_snapshot_api.py for what this pseudonym gets attached to, and
hub/core/network_collector.py + hub/core/network_snapshot_storage.py for the Hub side
that stores snapshots keyed ONLY by this pseudonym.
"""

import json
import os
import secrets

from core.storage_paths import storage_path

_FILENAME = "network_identity.json"


def _identity_path():
    # Read fresh every call (not cached at import time), matching
    # core/storage_paths.py's own storage_dir()/storage_path() convention -- so tests
    # can monkeypatch DEALEROS_STORAGE_DIR and this still resolves to the right tenant.
    return storage_path(_FILENAME)


def get_or_create_pseudonym():
    """Returns this dealer instance's opaque network pseudonym, generating and
    persisting one on first use if none exists yet. 32 random bytes (256 bits) of
    entropy, hex-encoded -- effectively impossible to guess or brute-force, and
    completely unrelated to dealer_id/name/any other identifying value."""

    # A demo tenant must NEVER write to disk — mirror every other saver's guard. Hand back an
    # ephemeral pseudonym so any caller (e.g. a network snapshot triggered in a demo) still works.
    from core.storage import demo_persistence_disabled
    if demo_persistence_disabled():
        return secrets.token_hex(32)

    path = _identity_path()

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            pseudonym = data.get("pseudonym")
            if pseudonym:
                return pseudonym

    pseudonym = secrets.token_hex(32)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            {
                "pseudonym": pseudonym,
                "note": (
                    "Randomly generated once, locally, on this dealer's own instance. "
                    "Never derived from dealer_id or any identifying value -- see "
                    "core/network_pseudonym.py's module docstring for why that matters. "
                    "Do not copy this file between tenants."
                ),
            },
            file,
            indent=4,
        )

    return pseudonym
