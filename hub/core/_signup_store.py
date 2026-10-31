"""
hub/core/_signup_store.py -- the persistence seam for self-serve signup + the inactivity lifecycle
(NXTDeal Freemium / marketing-site Free Forever funnel, 2026-08-03).

WHY THIS FILE EXISTS
--------------------
dealer_signup.py and dealer_lifecycle.py hold the real LOGIC (validation, slug generation, status
transitions, the 6-month-deactivate / 12-month-delete inactivity rules, reactivation on login). They
must operate on the Hub's dealer records, but they do NOT hard-depend on the Hub's exact storage --
they talk to a tiny `DealerStore` with five methods. That keeps the logic unit-testable in isolation
(an InMemoryDealerStore below) and makes the modules drop-in for the real Hub.

INTEGRATION (do this once, in the Hub, at startup)
--------------------------------------------------
The real Hub already persists dealers (hub/core/dealer.py -- create/list/get/update/delete over the
Hub's own graph, mirroring the Dealer shape in frontend/lib/hubApi.ts). Bind it once:

    from hub.core import dealer_signup, dealer_lifecycle
    from hub.core._signup_store import DealerStore

    class HubDealerStore:                       # adapter over your real hub/core/dealer.py
        def all(self):            return dealer.list_dealers()          # -> list[dict]
        def get(self, dealer_id): return dealer.get_dealer(dealer_id)   # -> dict | None
        def create(self, record): return dealer.create_dealer(record)   # -> dict (with dealer_id)
        def save(self, record):   return dealer.update_dealer(record["dealer_id"], record)
        def delete(self, dealer_id): return dealer.delete_dealer(dealer_id)

    dealer_signup.set_store(HubDealerStore())
    dealer_lifecycle.set_store(HubDealerStore())

A dealer "record" is a plain dict shaped like frontend/lib/hubApi.ts's `Dealer` (dealer_id, slug,
name, contact_email, status, plan_tier, active_modules, seat_count, created_at, ...) plus the
lifecycle fields this feature adds (last_activity_at, created_via, business_type, suggested_modules,
suspended_reason, deactivated_at, scheduled_deletion_at). If your dealer.py uses different field
names, translate them inside the adapter -- the logic modules only ever read/write these keys.
"""

from datetime import datetime, timezone


class DealerStore:
    """The five operations the signup + lifecycle logic needs. Implement against hub/core/dealer.py.
    (This base class documents the contract; the logic never instantiates it directly.)"""

    def all(self):
        """Return a list of all dealer records (dicts)."""
        raise NotImplementedError

    def get(self, dealer_id):
        """Return one dealer record (dict) or None."""
        raise NotImplementedError

    def create(self, record):
        """Persist a new dealer record; return it (with a dealer_id assigned if not already set)."""
        raise NotImplementedError

    def save(self, record):
        """Persist changes to an existing dealer record; return it."""
        raise NotImplementedError

    def delete(self, dealer_id):
        """Permanently remove a dealer record. Return True if something was removed."""
        raise NotImplementedError


class InMemoryDealerStore(DealerStore):
    """A real, working in-memory store -- the reference implementation used by the unit tests and a
    fine default for a dev Hub. Production binds the Hub's own dealer.py instead (see module docs)."""

    def __init__(self):
        self._dealers = {}
        self._counter = 0

    def all(self):
        return list(self._dealers.values())

    def get(self, dealer_id):
        return self._dealers.get(dealer_id)

    def create(self, record):
        if not record.get("dealer_id"):
            self._counter += 1
            record["dealer_id"] = f"DLR-{self._counter:05d}"
        self._dealers[record["dealer_id"]] = record
        return record

    def save(self, record):
        self._dealers[record["dealer_id"]] = record
        return record

    def delete(self, dealer_id):
        return self._dealers.pop(dealer_id, None) is not None


def utcnow():
    return datetime.now(timezone.utc)


def parse_iso(value):
    """Tolerant ISO-8601 parse -> aware datetime (UTC), or None. Handles a trailing 'Z'."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
