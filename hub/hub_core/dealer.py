"""
NXTDeal Hub (session 50) -- the Dealer record.

Sam: "we need a backend program to be able to setup dealers on NXTDeal (enter their
basic information) and create as a child portal. Each portal will have its own
knowledge graph."

Design decision (mine, flagged for Sam to revisit): a Dealer is NOT a graph Entity
inside any tenant's own graph.json -- that would be circular (the Hub manages OTHER
dealers' graphs, it shouldn't need to be one itself, at least not yet). It's a plain
flat record in the Hub's own small registry (hub/storage/dealers.json), following the
same dataclass + singleton-repository + matching *_storage.py convention backend/core/
uses throughout, just without the graph/relationship machinery -- there's nothing to
relate a Dealer to yet.

A dealer_id is NOT one of backend/core/id_generator.py's prefixes (that generator is
scoped to a single tenant's own graph entities) -- the Hub has its own tiny counter,
recovered from hub/storage/dealers.json on load the same way
backend/core/storage.py's _recover_id_counters() recovers VEH/LEAD/etc counters from a
loaded graph.

`slug` added session 51 -- Sam's deployment plan (Coolify, path-based routing):
dealeros.xyz is the marketing site, dealeros.xyz/hub is the Hub, and each dealer gets
dealeros.xyz/dealer1, /dealer2, etc. `dealer_id` (DLR-00001) is the Hub's own internal
id, never exposed in a URL; `slug` ("dealer1") is the URL-facing, human-readable path
segment, derived from the same counter as dealer_id so they always agree numerically
(DLR-00001 <-> dealer1, DLR-00002 <-> dealer2, ...) without being the same string.

2026-07-19 -- "Dealer Management" rebuild (Sam's Salesforce Trust / Azure Admin
Center / HubSpot Ops Hub / Datadog / 20 Group framing). Two additive changes, both
backward compatible with the one already-persisted real record (DLR-00001) on disk:

1. VALID_STATUSES extended from 3 values to a real lifecycle funnel (Lead -> Demo ->
   Trial -> Provisioning -> Active -> Expansion -> Churn Risk, with Suspended kept as
   an off-ramp reachable from any state, not a funnel stage itself). Purely additive --
   "provisioning"/"active"/"suspended" are unchanged strings in the same list, so every
   existing dealer record (all of which use one of those three today) keeps validating
   and every existing set_dealer_status() call site keeps working unmodified. Checked
   both call sites in hub_core/provisioning.py before extending: create_dealer()/
   adopt_dealer() both hardcode status="active" directly (never read VALID_STATUSES),
   so they are unaffected either way.

2. Nine new fields (Dealer Profile: group/oem/location_count/industry_type;
   Subscription Info: active_modules/renewal_date/seat_count, alongside the existing
   plan_tier; NXTDeal Version: current_release/beta_programs). Every one has a plain
   default so an already-persisted dict missing these keys entirely (like DLR-00001's
   real record, which predates this change) still constructs a valid Dealer via
   Dealer(**data) in from_dict() below -- Python fills in the dataclass default for any
   keyword argument the caller's dict doesn't supply. Live-verified: loading the real
   hub/storage/dealers.json (pre-migration, none of these keys present) produces a
   Dealer with group=None/oem=None/location_count=1/industry_type="independent"/
   active_modules=[]/renewal_date=None/seat_count=None/current_release=None/
   beta_programs=[], no crash, no data loss.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


VALID_STATUSES = [
    "lead",
    "demo",
    "trial",
    "provisioning",
    "active",
    "expansion",
    "churn_risk",
    "suspended",
]

# The real, ordered lifecycle funnel Sam asked for on the Overview screen.
# "suspended" is deliberately excluded -- it's an off-ramp reachable from any stage
# (a dealer can be suspended while still nominally "active" or "trial"), not a forward
# step in the funnel itself, so counting it as funnel stage 8 would misrepresent churn
# as "progress."
LIFECYCLE_FUNNEL_STAGES = [
    "lead",
    "demo",
    "trial",
    "provisioning",
    "active",
    "expansion",
    "churn_risk",
]

VALID_INDUSTRY_TYPES = ["independent", "franchise", "bhph", "finance_company"]

# Infrastructure & Platform Operations rebuild, slice 2 of 4 (Clusters) --
# Sam's named regions ("US East/US Central/US West/Canada/Europe"). This
# sandbox runs exactly ONE Hub process and today's real dealer(s) as plain
# single processes with no real region-aware deployment anywhere -- adding
# this field does NOT mean a dealer is actually hosted in that region today,
# it's a real, optional, honestly-labeled grouping key for the future
# multi-region vision (see hub/hub_core/clusters.py's own module docstring).
# None/unset ("unassigned") is the correct default for every dealer that
# predates this field or hasn't been assigned one yet.
VALID_REGIONS = ["us_east", "us_central", "us_west", "canada", "europe"]


@dataclass
class Dealer:
    dealer_id: str
    slug: str
    name: str
    contact_name: Optional[str]
    contact_email: str
    contact_phone: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    plan_tier: str
    status: str
    storage_dir: str
    network_opt_in: bool
    api_base_url: Optional[str]
    created_by: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # --- Dealer Profile (added 2026-07-19, Dealer Management rebuild) ---
    group: Optional[str] = None
    oem: Optional[str] = None
    location_count: int = 1
    industry_type: str = "independent"

    # --- region (added 2026-07-19, Infrastructure & Platform Ops rebuild
    # slice 2, Clusters) -- see VALID_REGIONS above. None = unassigned. ---
    region: Optional[str] = None

    # --- Subscription Info (plan_tier already existed above; kept in place) ---
    active_modules: List[str] = field(default_factory=list)
    renewal_date: Optional[str] = None
    seat_count: Optional[int] = None

    # --- NXTDeal Version ---
    current_release: Optional[str] = None
    beta_programs: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "dealer_id": self.dealer_id,
            "slug": self.slug,
            "name": self.name,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "plan_tier": self.plan_tier,
            "status": self.status,
            "storage_dir": self.storage_dir,
            "network_opt_in": self.network_opt_in,
            "api_base_url": self.api_base_url,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "group": self.group,
            "oem": self.oem,
            "location_count": self.location_count,
            "industry_type": self.industry_type,
            "region": self.region,
            "active_modules": self.active_modules,
            "renewal_date": self.renewal_date,
            "seat_count": self.seat_count,
            "current_release": self.current_release,
            "beta_programs": self.beta_programs
        }

    @staticmethod
    def from_dict(data):
        # Backward-compat loader: an already-persisted record (e.g. the one real
        # DLR-00001 on disk, written before this 2026-07-19 field additions) has none
        # of the new keys at all. Rather than rely solely on Dealer(**data) silently
        # filling dataclass defaults for missing kwargs (which does work, but is
        # fragile to reorder/typos), explicitly default every new field via .get() so
        # this loader stays correct even if the dataclass's own default ever changes
        # independently of what an old record should mean.
        return Dealer(
            dealer_id=data["dealer_id"],
            slug=data["slug"],
            name=data["name"],
            contact_name=data.get("contact_name"),
            contact_email=data["contact_email"],
            contact_phone=data.get("contact_phone"),
            address=data.get("address"),
            city=data.get("city"),
            state=data.get("state"),
            plan_tier=data.get("plan_tier", "Standard"),
            status=data.get("status", "active"),
            storage_dir=data["storage_dir"],
            network_opt_in=data.get("network_opt_in", True),
            api_base_url=data.get("api_base_url"),
            created_by=data.get("created_by", "nxtdeal_staff"),
            created_at=data.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
            group=data.get("group"),
            oem=data.get("oem"),
            location_count=data.get("location_count", 1),
            industry_type=data.get("industry_type", "independent"),
            region=data.get("region"),
            active_modules=data.get("active_modules", []),
            renewal_date=data.get("renewal_date"),
            seat_count=data.get("seat_count"),
            current_release=data.get("current_release"),
            beta_programs=data.get("beta_programs", [])
        )


class DealerIDGenerator:
    """Mirrors backend/core/id_generator.py's IDGenerator pattern (prefix + zero-padded
    counter), scoped to just the one "DLR" prefix the Hub needs."""

    def __init__(self):
        self.counter = 0

    def generate(self):
        self.counter += 1
        return f"DLR-{self.counter:05}"

    def default_slug(self):
        """The URL-facing slug that matches the dealer_id just generate()'d -- call
        immediately after generate() so self.counter is still the one that produced it.
        f"dealer{counter}" (no zero-padding, unlike dealer_id) since it's meant to be
        typed/read in a URL, not sorted as a string."""

        return f"dealer{self.counter}"

    def recover_from(self, dealers):
        """Same idea as backend/core/storage.py's _recover_id_counters() -- bump the
        counter to at least the highest dealer_id number already on file, so a Hub
        restart never reissues an existing dealer_id."""

        for dealer in dealers:
            try:
                number = int(dealer.dealer_id.split("-")[1])
            except (IndexError, ValueError):
                continue
            if number > self.counter:
                self.counter = number
