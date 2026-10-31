"""Loyalty / VIP Rewards Engine -- graph-native points/tier/visit/referral/
reward tracking across every customer-facing department (Sales, Service,
Parts, Accessories).

GRAPH-NATIVE, single source of truth: loyalty state is stored DIRECTLY as
attributes on the existing Customer entity, exactly the way
core/customer_journey.py stores journey state on a Customer and
core/pipeline_state.py stores pipeline state on a Lead -- NOT a separate JSON
store, not a new entity type. The attributes written per member are:

    loyalty_enrolled_at    - ISO timestamp of first touch (auto-enroll marker)
    loyalty_points_balance - current, spendable points balance (int)
    loyalty_lifetime_points- cumulative points ever EARNED (int); this is what
                             drives tier -- redemptions spend `balance` but never
                             lower `lifetime`, so a member never loses a tier they
                             earned by redeeming a reward
    loyalty_tier           - current tier name, recomputed from lifetime points
    loyalty_visits         - lifetime recorded visit count (int)
    loyalty_referrals      - lifetime recorded referral count (int)
    loyalty_ledger         - ordered list of LedgerEntry dicts, one appended on
                             every points/visit/referral/redeem mutation
    loyalty_redemptions    - ordered list of RedemptionRecord dicts

Tiers are computed purely from lifetime points thresholds (TIER_THRESHOLDS
below): Bronze (0), Silver (2,500), Gold (7,500), Platinum (20,000) -- sensible,
documented, monotonically increasing thresholds; the current tier is the
highest threshold a member's lifetime points have reached.

Follows the per-mutation save_graph() convention core/customer_journey.py/
core/communications_hub.py already established for low/moderate-frequency,
human-driven mutations -- awarding points / logging a visit / redeeming a
reward is a single human action, not a bulk job, so a direct save on every
mutating call is the right, safe choice.

This module is deliberately AI-free -- loyalty accounting is deterministic
arithmetic, not a generative task, so there is no OpenAI call anywhere here.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import CUSTOMER
from core.id_generator import IDGenerator
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

id_generator = IDGenerator()
# Defensive: these prefixes are new to this module. setdefault keeps this
# module standalone-green even before the shared core/id_generator.py counter
# dict is updated to carry them (see this session's handoff report).
id_generator.counters.setdefault("LLED", 0)
id_generator.counters.setdefault("LRDM", 0)


# ---------------------------------------------------------------------------
# Tiers -- computed purely from lifetime points. Order is load-bearing:
# _compute_tier walks these from highest threshold down.
# ---------------------------------------------------------------------------
BRONZE = "Bronze"
SILVER = "Silver"
GOLD = "Gold"
PLATINUM = "Platinum"

# (tier_name, minimum lifetime points to hold that tier), ascending.
TIER_THRESHOLDS = [
    (BRONZE, 0),
    (SILVER, 2500),
    (GOLD, 7500),
    (PLATINUM, 20000),
]

TIERS = [name for name, _ in TIER_THRESHOLDS]

# Ledger entry kinds.
EARN = "earn"
VISIT = "visit"
REFERRAL = "referral"
REDEEM = "redeem"


# ---------------------------------------------------------------------------
# Records -- dataclasses, serialized to plain dicts (asdict) when stored on the
# graph-native Customer entity so the ledger stays JSON-able.
# ---------------------------------------------------------------------------
@dataclass
class RewardCatalogItem:
    """A redeemable reward in the loyalty catalog."""

    reward_id: str
    name: str
    description: str
    point_cost: int
    department: str


@dataclass
class LedgerEntry:
    """One immutable line in a member's loyalty ledger. `points` is signed --
    positive for earning, negative for a redemption, zero for a visit/referral
    that only advances a counter."""

    entry_id: str
    entry_type: str
    points: int
    reason: str
    department: str
    timestamp: str
    balance_after: int


@dataclass
class RedemptionRecord:
    """One reward a member has redeemed."""

    redemption_id: str
    reward_id: str
    reward_name: str
    point_cost: int
    department: str
    timestamp: str


# The redeemable rewards catalog -- static, department-tagged, documented point
# costs spanning Service, Parts, Accessories, and Sales.
REWARDS_CATALOG = [
    RewardCatalogItem(
        reward_id="RWD-CARWASH",
        name="Complimentary Car Wash",
        description="One free full-service car wash.",
        point_cost=500,
        department="Service",
    ),
    RewardCatalogItem(
        reward_id="RWD-PARTS-CREDIT",
        name="$50 Parts Credit",
        description="$50 credit toward any parts purchase.",
        point_cost=1000,
        department="Parts",
    ),
    RewardCatalogItem(
        reward_id="RWD-OILCHANGE",
        name="Free Oil Change",
        description="One complimentary standard oil-and-filter change.",
        point_cost=1500,
        department="Service",
    ),
    RewardCatalogItem(
        reward_id="RWD-ACCESSORY-CREDIT",
        name="$100 Accessories Credit",
        description="$100 credit toward accessories.",
        point_cost=2000,
        department="Accessories",
    ),
    RewardCatalogItem(
        reward_id="RWD-DETAIL",
        name="Full Interior & Exterior Detail",
        description="One complete professional detail.",
        point_cost=3000,
        department="Service",
    ),
    RewardCatalogItem(
        reward_id="RWD-VIP-EVENT",
        name="VIP Event Invitation",
        description="Invitation for two to an exclusive VIP dealership event.",
        point_cost=5000,
        department="Sales",
    ),
    RewardCatalogItem(
        reward_id="RWD-DOWN-CREDIT",
        name="$500 Down Payment Credit",
        description="$500 credit toward the down payment on your next vehicle.",
        point_cost=10000,
        department="Sales",
    ),
]

_REWARDS_BY_ID = {r.reward_id: r for r in REWARDS_CATALOG}


def _now():

    return datetime.now(timezone.utc).isoformat()


def _get_customer_or_raise(customer_id):

    entity = ledger.get_entity(customer_id)

    if not entity or entity.entity_type != CUSTOMER:
        raise ValueError(f"No customer found with id {customer_id}.")

    return entity


def _customer_name(customer):

    attrs = customer.attributes

    name = attrs.get("Name")
    if name:
        return name

    first = attrs.get("FirstName") or ""
    last = attrs.get("LastName") or ""
    full = f"{first} {last}".strip()

    return full or None


def _compute_tier(lifetime_points):
    """The highest tier whose minimum-lifetime-points threshold the member has
    reached. Walks TIER_THRESHOLDS from the top down."""

    tier = TIER_THRESHOLDS[0][0]
    for name, threshold in TIER_THRESHOLDS:
        if lifetime_points >= threshold:
            tier = name
    return tier


def _is_enrolled(customer):

    return customer.attributes.get("loyalty_enrolled_at") is not None


def _ensure_member(customer):
    """Auto-enroll / initialize loyalty state on a customer's first touch. Idempotent
    -- an already-enrolled customer is left untouched. Returns the customer entity."""

    if not _is_enrolled(customer):
        attrs = customer.attributes
        attrs["loyalty_enrolled_at"] = _now()
        attrs["loyalty_points_balance"] = 0
        attrs["loyalty_lifetime_points"] = 0
        attrs["loyalty_tier"] = TIER_THRESHOLDS[0][0]
        attrs["loyalty_visits"] = 0
        attrs["loyalty_referrals"] = 0
        attrs["loyalty_ledger"] = []
        attrs["loyalty_redemptions"] = []

    return customer


def _append_ledger_entry(customer, entry_type, points, reason, department):
    """Appends a real LedgerEntry (as a dict) to the member's ledger and returns it.
    Does not persist -- the calling mutation saves once at the end."""

    entry = LedgerEntry(
        entry_id=id_generator.generate("LLED"),
        entry_type=entry_type,
        points=points,
        reason=reason or "",
        department=department or "",
        timestamp=_now(),
        balance_after=customer.attributes.get("loyalty_points_balance", 0),
    )

    ledger_list = customer.attributes.get("loyalty_ledger") or []
    ledger_list.append(asdict(entry))
    customer.attributes["loyalty_ledger"] = ledger_list

    return entry


def _member_brief(customer):

    from core.loyalty_program import legacy_member
    current = legacy_member(customer.id)
    if current is not None:
        return current
    attrs = customer.attributes

    return {
        "customer_id": customer.id,
        "name": _customer_name(customer),
        "enrolled": _is_enrolled(customer),
        "enrolled_at": attrs.get("loyalty_enrolled_at"),
        "points_balance": attrs.get("loyalty_points_balance", 0),
        "lifetime_points": attrs.get("loyalty_lifetime_points", 0),
        "tier": attrs.get("loyalty_tier"),
        "visits": attrs.get("loyalty_visits", 0),
        "referrals": attrs.get("loyalty_referrals", 0),
        "ledger": list(attrs.get("loyalty_ledger") or []),
        "redemptions": list(attrs.get("loyalty_redemptions") or []),
    }


def get_member(customer_id):
    """The real loyalty record for one customer -- points balance, tier, visits,
    referrals, and full ledger/redemption history. Auto-enrolls (initializes
    loyalty state) on first touch and persists that enrollment. Raises ValueError
    on an unknown customer / non-customer id."""

    customer = _get_customer_or_raise(customer_id)

    from core.loyalty_program import configured
    if configured():
        return _member_brief(customer)

    newly_enrolled = not _is_enrolled(customer)
    _ensure_member(customer)

    if newly_enrolled:
        save_graph(GRAPH_PATH)

    return _member_brief(customer)


def award_points(customer_id, points, reason, department):
    """Awards `points` to a member: records an EARN ledger entry, increases both
    the spendable balance and lifetime points, and recomputes the tier. Auto-enrolls
    on first touch. Raises ValueError on an unknown customer or a non-positive
    points amount."""

    from core.loyalty_program import guard_legacy_write
    guard_legacy_write()

    customer = _get_customer_or_raise(customer_id)

    try:
        points = int(points)
    except (TypeError, ValueError):
        raise ValueError("Points to award must be a positive whole number.")

    if points <= 0:
        raise ValueError("Points to award must be a positive whole number.")

    _ensure_member(customer)
    attrs = customer.attributes

    attrs["loyalty_points_balance"] = attrs.get("loyalty_points_balance", 0) + points
    attrs["loyalty_lifetime_points"] = attrs.get("loyalty_lifetime_points", 0) + points
    attrs["loyalty_tier"] = _compute_tier(attrs["loyalty_lifetime_points"])

    _append_ledger_entry(customer, EARN, points, reason, department)

    save_graph(GRAPH_PATH)

    return _member_brief(customer)


def record_visit(customer_id, department):
    """Records a real dealership visit for a member -- increments the visit counter
    and appends a VISIT ledger entry (0 points; visits are a counter, not an
    earning event -- award points separately via award_points). Auto-enrolls on
    first touch. Raises ValueError on an unknown customer."""

    from core.loyalty_program import guard_legacy_write
    guard_legacy_write()

    customer = _get_customer_or_raise(customer_id)

    _ensure_member(customer)
    attrs = customer.attributes

    attrs["loyalty_visits"] = attrs.get("loyalty_visits", 0) + 1

    _append_ledger_entry(
        customer, VISIT, 0, f"Visit recorded ({department})", department
    )

    save_graph(GRAPH_PATH)

    return _member_brief(customer)


def record_referral(customer_id, referred_name):
    """Records a real referral a member made -- increments the referral counter and
    appends a REFERRAL ledger entry (0 points; award any referral bonus separately
    via award_points). Auto-enrolls on first touch. Raises ValueError on an unknown
    customer."""

    from core.loyalty_program import guard_legacy_write
    guard_legacy_write()

    customer = _get_customer_or_raise(customer_id)

    if not referred_name or not str(referred_name).strip():
        raise ValueError("A referral must name the person referred.")

    _ensure_member(customer)
    attrs = customer.attributes

    attrs["loyalty_referrals"] = attrs.get("loyalty_referrals", 0) + 1

    _append_ledger_entry(
        customer, REFERRAL, 0, f"Referred {referred_name}", ""
    )

    save_graph(GRAPH_PATH)

    return _member_brief(customer)


def list_rewards_catalog():
    """The real, static catalog of redeemable rewards, as plain dicts (each a
    serialized RewardCatalogItem) with point costs, spanning Service/Parts/
    Accessories/Sales."""

    return [asdict(reward) for reward in REWARDS_CATALOG]


def redeem_reward(customer_id, reward_id):
    """Redeems a catalog reward for a member: checks the reward exists and the
    member has enough spendable points, deducts the cost from the BALANCE (never
    from lifetime points, so tier is never lost by redeeming), records a
    RedemptionRecord plus a REDEEM ledger entry, and persists. Auto-enrolls on first
    touch. Raises ValueError on an unknown customer, an unknown reward, or
    insufficient points."""

    from core.loyalty_program import guard_legacy_write
    guard_legacy_write()

    customer = _get_customer_or_raise(customer_id)

    reward = _REWARDS_BY_ID.get(reward_id)
    if reward is None:
        raise ValueError(f"No reward found with id {reward_id}.")

    _ensure_member(customer)
    attrs = customer.attributes

    balance = attrs.get("loyalty_points_balance", 0)
    if balance < reward.point_cost:
        raise ValueError(
            f"Insufficient points to redeem '{reward.name}': need "
            f"{reward.point_cost}, have {balance}."
        )

    attrs["loyalty_points_balance"] = balance - reward.point_cost

    redemption = RedemptionRecord(
        redemption_id=id_generator.generate("LRDM"),
        reward_id=reward.reward_id,
        reward_name=reward.name,
        point_cost=reward.point_cost,
        department=reward.department,
        timestamp=_now(),
    )
    redemptions = attrs.get("loyalty_redemptions") or []
    redemptions.append(asdict(redemption))
    attrs["loyalty_redemptions"] = redemptions

    _append_ledger_entry(
        customer,
        REDEEM,
        -reward.point_cost,
        f"Redeemed {reward.name}",
        reward.department,
    )

    save_graph(GRAPH_PATH)

    return _member_brief(customer)


def get_loyalty_overview():
    """Real, live-computed program rollup -- enrolled member count, total
    outstanding (spendable) points across all members, tier distribution (seeded to
    0 for every real tier even when empty, same convention
    core/customer_journey.py's counts_by_stage already established), and the total
    number of reward redemptions."""

    by_tier = {tier: 0 for tier in TIERS}
    member_count = 0
    total_outstanding_points = 0
    total_redemptions = 0

    for entity in ledger.get_all().values():
        if entity.entity_type != CUSTOMER:
            continue
        brief = _member_brief(entity)
        if not brief["enrolled"]:
            continue

        member_count += 1
        total_outstanding_points += brief["points_balance"]

        tier = brief.get("tier")
        if tier in by_tier:
            by_tier[tier] += 1

        total_redemptions += len(brief.get("redemptions") or [])

    return {
        "tiers": list(TIERS),
        "member_count": member_count,
        "total_outstanding_points": total_outstanding_points,
        "tier_distribution": by_tier,
        "total_redemptions": total_redemptions,
    }
