"""
NXTDeal Hub (session 50) -- in-memory singleton registry of every Dealer, mirroring
backend/core/ledger.py's DealerLedger pattern (one singleton instance, plain dict keyed
by id, imported by the rest of the module rather than instantiated per-call).
"""

from hub_core.dealer import Dealer, DealerIDGenerator


class DealerRegistry:

    def __init__(self):
        self.dealers = {}
        self.id_generator = DealerIDGenerator()

    def add(self, dealer: Dealer):
        self.dealers[dealer.dealer_id] = dealer

    def get(self, dealer_id):
        return self.dealers.get(dealer_id)

    def get_by_email(self, contact_email):
        for dealer in self.dealers.values():
            if dealer.contact_email.lower() == contact_email.lower():
                return dealer
        return None

    def get_by_slug(self, slug):
        """slug ("dealer1") is the URL-facing lookup -- used both to reject a
        collision at creation time and, eventually, by whatever routes a request at
        dealeros.xyz/{slug} to the right dealer's backend."""

        for dealer in self.dealers.values():
            if dealer.slug.lower() == (slug or "").lower():
                return dealer
        return None

    def get_all(self):
        return self.dealers

    def list_all(self):
        return sorted(self.dealers.values(), key=lambda d: d.dealer_id)

    def reset(self):
        """Clear all dealers in place (used by tests). Does not touch disk."""
        self.dealers = {}
        self.id_generator = DealerIDGenerator()


registry = DealerRegistry()
