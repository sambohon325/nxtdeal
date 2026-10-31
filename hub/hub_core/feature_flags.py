"""
NXTDeal Hub -- "Dealer Management" rebuild, slice 2 of 5: Feature Flags.

Sam's ask: "one of the most important things you can build early. Every
feature gets: Global / Group / Store / Dealer control. Example: AI Sales
Advisor, Enable For: Beta Dealers. Or: Website Studio 2.0, Enable For: Dealer
Group A."

Real, persisted, resolvable scoped flag overrides -- `FeatureFlagOverride`,
same dataclass + singleton-registry + *_storage.py convention as everything
else in this Hub (hub/hub_core/dealer.py's own Dealer/DealerRegistry is the direct
precedent). A flag_key is a plain freeform string (Sam's own examples are ad
hoc names like "ai_sales_advisor"/"website_studio_2") -- this module does not
restrict flag_key to a fixed catalog, since the whole point (per Sam's "no
code required" framing on the sibling Module Management feature) is that a
new flag can be introduced from the Hub UI at any time with no code change
here. Matching is case-sensitive and exact-string -- keep naming consistent
(e.g. always lowercase_snake_case) to avoid accidentally creating two records
for what was meant to be the same flag.

SCOPE DESIGN -- Store vs. Dealer, collapsed to one scope, with reasoning:
Sam names 4 scope levels (Global/Group/Store/Dealer). This codebase has no
"Store" concept distinct from "Dealer" anywhere -- a multi-rooftop dealer
(hub/hub_core/dealer.py's own `group`/`location_count` fields, added the prior
Dealer Management slice) only carries a plain location COUNT, never
individual per-location Store/Location records. "Store" scope and "Dealer"
scope would therefore resolve identically today (both would target one
`dealer_id`), so rather than build two scope levels that are indistinguishable
in this data model, SCOPES here is exactly 3: "global" / "group" / "dealer".
If a future slice ever models individual Location/Store records under a
Dealer (the natural next step once `location_count` needs real backing
data), "store" can be added as its own scope level, sitting between "group"
and "dealer" in precedence, without breaking anything built here.

RESOLUTION PRECEDENCE (most specific wins): a dealer-scoped override for this
exact dealer_id > a group-scoped override matching this dealer's own `group`
value > a global-scoped override > default (disabled -- a flag with no
override anywhere is OFF, matching how a brand-new capability should ship
dark until someone explicitly turns it on for someone).

NOT the same mechanism as backend/core/ai_management.py's tenant-side
per-feature kill switches (that module's flags live inside ONE dealer's own
running process/graph, flipped by that dealer's own ADMIN/OPERATIONS
employees, and gate real OpenAI-call attempts in real time). This is a
Hub-WIDE, cross-dealer configuration record NXTDeal staff manage from outside
any one tenant's process -- same "record, not a live switch" honesty note as
Module Management (hub/hub_core/dealer_modules.py): nothing here currently pushes
a resolved flag value into a running dealer backend. A resolution PREVIEW
(resolve_flag() below) is real and useful on its own -- it answers "would
this flag be on for dealer X today, and why" -- but no tenant process
currently reads or enforces it.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from hub_core.dealer_registry import registry as dealer_registry


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


SCOPES = ["global", "group", "dealer"]

# Sort order for resolution -- most specific first. Used both by resolve_flag()
# and by list_overrides() so the UI can show overrides ranked the same way
# they're actually evaluated.
_SCOPE_SPECIFICITY = {"dealer": 0, "group": 1, "global": 2}


@dataclass
class FeatureFlagOverride:
    override_id: str
    flag_key: str
    scope: str
    scope_target: Optional[str]
    enabled: bool
    note: Optional[str]
    created_by: str
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self):
        return {
            "override_id": self.override_id,
            "flag_key": self.flag_key,
            "scope": self.scope,
            "scope_target": self.scope_target,
            "enabled": self.enabled,
            "note": self.note,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data):
        return FeatureFlagOverride(
            override_id=data["override_id"],
            flag_key=data["flag_key"],
            scope=data["scope"],
            scope_target=data.get("scope_target"),
            enabled=bool(data.get("enabled", False)),
            note=data.get("note"),
            created_by=data.get("created_by", "nxtdeal_staff"),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )


class _FlagIDGenerator:
    """Mirrors hub/hub_core/dealer.py's DealerIDGenerator exactly -- a tiny counter,
    recovered from whatever's already on disk on load."""

    def __init__(self):
        self.counter = 0

    def generate(self):
        self.counter += 1
        return f"FFLAG-{self.counter:05}"

    def recover_from(self, overrides):
        for override in overrides:
            try:
                number = int(override.override_id.split("-")[1])
            except (IndexError, ValueError):
                continue
            if number > self.counter:
                self.counter = number


class FeatureFlagRegistry:

    def __init__(self):
        self.overrides = {}
        self.id_generator = _FlagIDGenerator()

    def add(self, override: FeatureFlagOverride):
        self.overrides[override.override_id] = override

    def get(self, override_id):
        return self.overrides.get(override_id)

    def remove(self, override_id):
        return self.overrides.pop(override_id, None)

    def list_all(self):
        return sorted(self.overrides.values(), key=lambda o: o.override_id)

    def reset(self):
        self.overrides = {}
        self.id_generator = _FlagIDGenerator()


registry = FeatureFlagRegistry()


def _find_existing(flag_key, scope, scope_target):
    """Upsert lookup -- one override per (flag_key, scope, scope_target) triple."""

    for override in registry.overrides.values():
        if (
            override.flag_key == flag_key
            and override.scope == scope
            and override.scope_target == scope_target
        ):
            return override
    return None


def create_or_update_override(
    flag_key,
    scope,
    enabled,
    scope_target=None,
    note=None,
    created_by="nxtdeal_staff"
):

    flag_key = (flag_key or "").strip()
    if not flag_key:
        return None, "flag_key cannot be blank"

    if scope not in SCOPES:
        return None, f"scope must be one of {SCOPES}"

    if scope == "global":
        scope_target = None
    else:
        scope_target = (scope_target or "").strip()
        if not scope_target:
            return None, f"scope_target is required for scope='{scope}'"

        if scope == "dealer" and not dealer_registry.get(scope_target):
            return None, f"no dealer with id '{scope_target}'"

        # scope == "group": no separate Group entity exists anywhere in this
        # codebase (a "group" is just a free-text string on a Dealer record) --
        # deliberately no validation against a real catalog of group names,
        # since none exists to validate against. A typo here (e.g. targeting a
        # group name no dealer actually has) will simply never match anything
        # at resolution time rather than being rejected up front.

    existing = _find_existing(flag_key, scope, scope_target)

    if existing:
        existing.enabled = bool(enabled)
        existing.note = note
        existing.updated_at = _now_iso()
        registry.add(existing)
        return existing.to_dict(), None

    override = FeatureFlagOverride(
        override_id=registry.id_generator.generate(),
        flag_key=flag_key,
        scope=scope,
        scope_target=scope_target,
        enabled=bool(enabled),
        note=note,
        created_by=created_by,
    )
    registry.add(override)

    return override.to_dict(), None


def delete_override(override_id):
    removed = registry.remove(override_id)
    if not removed:
        return False, f"no feature flag override with id '{override_id}'"
    return True, None


def list_overrides(flag_key=None):

    overrides = registry.list_all()

    if flag_key:
        overrides = [o for o in overrides if o.flag_key == flag_key]

    overrides = sorted(
        overrides,
        key=lambda o: (o.flag_key, _SCOPE_SPECIFICITY.get(o.scope, 9), o.override_id),
    )

    return [o.to_dict() for o in overrides]


def list_known_flag_keys():
    """Distinct flag_key values that currently have at least one override --
    just a convenience list for the UI's autocomplete, not an enforced
    catalog (see this module's own docstring: flag_key is deliberately
    freeform)."""

    return sorted({o.flag_key for o in registry.overrides.values()})


def resolve_flag(flag_key, dealer_id):
    """Answers "would this flag be enabled for this dealer right now, and
    why" -- a real, honest resolution PREVIEW. See this module's own
    docstring for why this does not currently push anything into a running
    tenant process."""

    flag_key = (flag_key or "").strip()
    if not flag_key:
        return None, "flag_key cannot be blank"

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    trail = []

    dealer_override = _find_existing(flag_key, "dealer", dealer_id)
    trail.append({
        "scope": "dealer",
        "scope_target": dealer_id,
        "matched": dealer_override is not None,
        "override": dealer_override.to_dict() if dealer_override else None,
    })
    if dealer_override:
        return {
            "flag_key": flag_key,
            "dealer_id": dealer_id,
            "dealer_name": dealer.name,
            "resolved_enabled": dealer_override.enabled,
            "source": "dealer",
            "matched_override": dealer_override.to_dict(),
            "evaluation_trail": trail,
        }, None

    if dealer.group:
        group_override = _find_existing(flag_key, "group", dealer.group)
        trail.append({
            "scope": "group",
            "scope_target": dealer.group,
            "matched": group_override is not None,
            "override": group_override.to_dict() if group_override else None,
        })
        if group_override:
            return {
                "flag_key": flag_key,
                "dealer_id": dealer_id,
                "dealer_name": dealer.name,
                "resolved_enabled": group_override.enabled,
                "source": "group",
                "matched_override": group_override.to_dict(),
                "evaluation_trail": trail,
            }, None
    else:
        trail.append({
            "scope": "group",
            "scope_target": None,
            "matched": False,
            "override": None,
            "skipped_reason": "this dealer has no `group` set",
        })

    global_override = _find_existing(flag_key, "global", None)
    trail.append({
        "scope": "global",
        "scope_target": None,
        "matched": global_override is not None,
        "override": global_override.to_dict() if global_override else None,
    })
    if global_override:
        return {
            "flag_key": flag_key,
            "dealer_id": dealer_id,
            "dealer_name": dealer.name,
            "resolved_enabled": global_override.enabled,
            "source": "global",
            "matched_override": global_override.to_dict(),
            "evaluation_trail": trail,
        }, None

    return {
        "flag_key": flag_key,
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "resolved_enabled": False,
        "source": "default",
        "matched_override": None,
        "evaluation_trail": trail,
    }, None
