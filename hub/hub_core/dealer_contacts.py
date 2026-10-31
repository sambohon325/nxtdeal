"""
NXTDeal Hub -- "Dealer Management" rebuild, slice 5 of 5: Users.

Sam's spec didn't include a detailed Users sub-spec the way Network/Support/
Audit did -- scoped here by judgment, stated plainly rather than guessed at
silently: this is a real Hub-side roster of NAMED HUMAN CONTACTS per dealer
(the people NXTDeal staff actually call/email about that account -- GM,
billing contact, IT/integrations contact, etc.), genuinely distinct from the
tenant's own internal Employee roster, which the Hub architecturally cannot
see (each dealer is its own isolated process/graph -- see CLAUDE.md's
"NXTDeal Hub / Multi-Tenant Architecture" section).

hub/hub_core/dealer.py's Dealer already has ONE primary contact
(contact_name/contact_email/contact_phone). Judged that a real dealership
account genuinely has more than one point of contact worth tracking (a
billing contact is very often not the same person as the GM who signed up),
so this extends with a real, small, addable/removable list of ADDITIONAL
named contacts rather than just building a display view of the existing
single-contact fields -- the existing fields stay exactly as-is (still the
one "primary" contact shown everywhere else in the console), this is
additive.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from hub_core.dealer_registry import registry as dealer_registry


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


CONTACT_ROLES = [
    "general_manager",
    "billing",
    "it_integrations",
    "sales_manager",
    "service_manager",
    "marketing",
    "other",
]

CONTACT_ROLE_LABELS = {
    "general_manager": "General Manager",
    "billing": "Billing Contact",
    "it_integrations": "IT / Integrations Contact",
    "sales_manager": "Sales Manager",
    "service_manager": "Service Manager",
    "marketing": "Marketing Contact",
    "other": "Other",
}


@dataclass
class DealerContact:
    contact_id: str
    dealer_id: str
    name: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    added_by: str = "nxtdeal_staff"
    added_at: str = ""

    def to_dict(self):
        return {
            "contact_id": self.contact_id,
            "dealer_id": self.dealer_id,
            "name": self.name,
            "role": self.role,
            "role_label": CONTACT_ROLE_LABELS.get(self.role, self.role),
            "email": self.email,
            "phone": self.phone,
            "added_by": self.added_by,
            "added_at": self.added_at,
        }

    @staticmethod
    def from_dict(data):
        return DealerContact(
            contact_id=data["contact_id"],
            dealer_id=data["dealer_id"],
            name=data["name"],
            role=data.get("role", "other"),
            email=data.get("email"),
            phone=data.get("phone"),
            added_by=data.get("added_by", "nxtdeal_staff"),
            added_at=data.get("added_at", _now_iso()),
        )


class DealerContactRegistry:

    def __init__(self):
        self.contacts: Dict[str, DealerContact] = {}
        self._counter = 0

    def next_id(self):
        self._counter += 1
        return f"CONTACT-{self._counter:05}"

    def recover_counter(self):
        highest = 0
        for contact_id in self.contacts:
            try:
                suffix = int(contact_id.split("-")[-1])
            except (ValueError, IndexError):
                continue
            highest = max(highest, suffix)
        self._counter = highest

    def add(self, contact: DealerContact):
        self.contacts[contact.contact_id] = contact

    def get(self, contact_id):
        return self.contacts.get(contact_id)

    def remove(self, contact_id):
        return self.contacts.pop(contact_id, None)

    def list_for_dealer(self, dealer_id):
        return sorted(
            [c for c in self.contacts.values() if c.dealer_id == dealer_id],
            key=lambda c: c.added_at,
        )

    def reset(self):
        self.contacts = {}
        self._counter = 0


registry = DealerContactRegistry()


def add_contact(dealer_id, name, role, email=None, phone=None, added_by="nxtdeal_staff"):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    if not name or not name.strip():
        return None, "name is required"

    if role not in CONTACT_ROLES:
        return None, f"'{role}' is not a valid contact role -- must be one of {CONTACT_ROLES}"

    contact = DealerContact(
        contact_id=registry.next_id(),
        dealer_id=dealer_id,
        name=name.strip(),
        role=role,
        email=email,
        phone=phone,
        added_by=added_by,
        added_at=_now_iso(),
    )
    registry.add(contact)

    return contact, None


def remove_contact(contact_id):

    contact = registry.get(contact_id)
    if not contact:
        return None, f"no contact with id '{contact_id}'"

    registry.remove(contact_id)

    return contact, None


def get_dealer_users(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    additional = [c.to_dict() for c in registry.list_for_dealer(dealer_id)]

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "primary_contact": {
            "name": dealer.contact_name,
            "email": dealer.contact_email,
            "phone": dealer.contact_phone,
            "role": "primary",
            "role_label": "Primary Contact (Dealer record)",
        },
        "additional_contacts": additional,
        "total_contacts": 1 + len(additional),
        "scope_note": (
            "This is a Hub-side roster of named human contacts NXTDeal staff "
            "work with -- the primary contact from the Dealer record plus any "
            "additional contacts added here. It is NOT, and cannot be, the "
            "tenant's own internal Employee/user roster (backend/core/auth.py's "
            "credential store) -- each dealer runs as its own isolated process "
            "with its own graph, which the Hub architecturally cannot see."
        ),
    }, None
