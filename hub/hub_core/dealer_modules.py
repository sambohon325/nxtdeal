"""
NXTDeal Hub -- "Dealer Management" rebuild, slice 2 of 5: Module Management.

Sam's ask: "MODULE MANAGEMENT -- this is huge. Every NXTDeal module should be
toggleable. Core Modules: Operations/Inventory/Service/Sales/Marketing/Finance/
Administration/Readiness/Network. Optional Add-Ons: Websites/AI Assistants/
Collections/BHPH/Payment Processing/GPS/Starter Interrupt/Reputation/
Advertising. Enable/Disable. Example: Enable Network, Enable Website Studio,
Disable Collections, Enable Advanced Finance. No code required."

This is a real, persisted, per-dealer Hub-side CONFIGURATION RECORD --
`DealerModuleConfig`, one per dealer_id, following the exact dataclass +
singleton-registry + matching *_storage.py convention this whole codebase
uses (hub/hub_core/dealer.py's own Dealer/DealerRegistry/dealer_storage.py is the
direct precedent, right down to the atomic-write + truncated-JSON-recovery
persistence layer).

HONEST SCOPE, stated plainly here and repeated in the API layer / UI copy:
toggling a module here does NOT currently enforce anything on the tenant's
own backend process. There is no cross-process mechanism today for the Hub
to tell a running dealer instance "module X is now off" -- each dealer is
its own isolated `uvicorn` process (see CLAUDE.md's "NXTDeal Hub /
Multi-Tenant Architecture" section: "process-per-tenant, not in-process
multi-tenancy"), and nothing in `backend/` polls or subscribes to this
Hub-side record. This is still a real, useful admin record on its own --
NXTDeal staff can see and set what SHOULD be enabled for a dealer, sales/
support can reference it when scoping a deal, and it's the natural
foundation a future tenant-side enforcement pass (e.g. a boot-time fetch
from the Hub, or a per-request check) would read from -- but it is a
configuration record, not a live switch, today. Not fabricated as more than
that.

CORE_MODULES maps 1:1 onto NXTDeal's real 9 Top Menu departments
(backend/core/menu_catalog.py) -- every dealer runs the full core platform,
so every core module defaults ENABLED.

ADD_ON_MODULES is Sam's own 9-item list, each mapped (via `real_capability`
below) to the real backend module that would eventually be gated if/when
tenant-side enforcement is built:
  websites            -> backend/core/websites.py (Website Builder)
  ai_assistants       -> backend/core/ai_management.py (AI feature catalog + kill switches)
  collections         -> backend/core/collections.py (Finance Collections work queue)
  bhph                -> backend/core/loan_servicing.py + the Portfolio suite
  payment_processing  -> backend/core/payments.py (customer payment portal + auto-draft)
  gps                 -> backend/core/device_management.py (GPS location tracking)
  starter_interrupt   -> backend/core/device_management.py (starter-interrupt control)
  reputation          -> backend/core/reputation.py (Social & Reputation)
  advertising         -> backend/core/advertising.py (Meta/Google ad campaigns)

Default split for add-ons -- a judgment call, not a spec Sam gave explicitly,
flagged here for Sam to override per-module if wrong: Websites and AI
Assistants default ENABLED, since both are foundational, already-broadly-
used capabilities most current dealers already run day one (the Website
Builder and the AI Management kill-switch catalog, both deep, multi-session
builds in the tenant-side product). The remaining seven default DISABLED
-- opt-in -- since they're either vertical-specific (BHPH/Collections only
matter to a dealer actually doing in-house financing), carry real hardware/
compliance implications (GPS, Starter Interrupt -- repossession-adjacent
device control), or read as a discrete paid add-on a dealer may not have
purchased yet (Payment Processing, Reputation, Advertising).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from hub_core.dealer_registry import registry as dealer_registry


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# (key, label, real_capability, default_enabled)
CORE_MODULES = [
    ("operations", "Operations", "backend/core/operations_menu.py + Operations Top Menu", True),
    ("inventory", "Inventory", "backend/core/inventory_menu.py + Inventory Top Menu", True),
    ("service", "Service", "backend/core/service_menu.py + Service Top Menu", True),
    ("sales", "Sales", "backend/core/sales_menu.py + Sales Top Menu", True),
    ("marketing", "Marketing", "backend/core/marketing_menu.py + Marketing Top Menu", True),
    ("finance", "Finance", "backend/core/finance_menu.py + Finance Top Menu", True),
    ("administration", "Administration", "backend/core/administration_menu.py + Administration Top Menu", True),
    ("readiness", "Readiness", "backend/core/readiness_menu.py + Readiness Top Menu", True),
    ("network", "Dealership Lab", "Simulation and learning program; explicit policy sync applies the tenant switch", True),
]

ADD_ON_MODULES = [
    ("websites", "Websites", "backend/core/websites.py -- the Website Builder", True),
    ("ai_assistants", "AI Assistants", "backend/core/ai_management.py -- AI feature catalog + kill switches", True),
    ("collections", "Collections", "backend/core/collections.py -- Finance Collections work queue", False),
    ("bhph", "BHPH", "backend/core/loan_servicing.py + the Portfolio suite -- in-house Buy Here Pay Here financing", False),
    ("payment_processing", "Payment Processing", "backend/core/payments.py -- customer payment portal + auto-draft", False),
    ("gps", "GPS", "backend/core/device_management.py -- GPS location tracking on financed vehicles", False),
    ("starter_interrupt", "Starter Interrupt", "backend/core/device_management.py -- starter-interrupt device control", False),
    ("reputation", "Reputation", "backend/core/reputation.py -- Social & Reputation review management", False),
    ("advertising", "Advertising", "backend/core/advertising.py -- Meta/Google ad campaign management", False),
]

MODULE_CATALOG = [
    {
        "key": key,
        "label": label,
        "category": "core",
        "real_capability": real_capability,
        "default_enabled": default_enabled,
    }
    for key, label, real_capability, default_enabled in CORE_MODULES
] + [
    {
        "key": key,
        "label": label,
        "category": "add_on",
        "real_capability": real_capability,
        "default_enabled": default_enabled,
    }
    for key, label, real_capability, default_enabled in ADD_ON_MODULES
]

MODULE_KEYS = {entry["key"] for entry in MODULE_CATALOG}
MODULE_DEFAULTS = {entry["key"]: entry["default_enabled"] for entry in MODULE_CATALOG}


@dataclass
class DealerModuleConfig:
    dealer_id: str
    modules: Dict[str, bool] = field(default_factory=dict)
    updated_by: Optional[str] = None
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self):
        return {
            "dealer_id": self.dealer_id,
            "modules": self.modules,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data):
        return DealerModuleConfig(
            dealer_id=data["dealer_id"],
            modules=dict(data.get("modules", {})),
            updated_by=data.get("updated_by"),
            updated_at=data.get("updated_at", _now_iso()),
        )


class DealerModuleRegistry:
    """One DealerModuleConfig per dealer_id that has ever had a module explicitly
    toggled. A dealer with no record here is not "unconfigured" -- it just means
    every module is still at its MODULE_DEFAULTS value; see _effective_modules()
    below, which merges a stored record's overrides on top of the real defaults
    rather than requiring a record to exist for every dealer up front."""

    def __init__(self):
        self.configs = {}

    def get(self, dealer_id):
        return self.configs.get(dealer_id)

    def add(self, config: DealerModuleConfig):
        self.configs[config.dealer_id] = config

    def list_all(self):
        return sorted(self.configs.values(), key=lambda c: c.dealer_id)

    def reset(self):
        self.configs = {}


registry = DealerModuleRegistry()


def _effective_modules(dealer_id):
    """Real defaults, with whatever this dealer's own stored record overrides on
    top -- a dealer with no record at all still gets a full, correct 18-entry
    view, it's just every value at MODULE_DEFAULTS."""

    stored = registry.get(dealer_id)
    stored_modules = stored.modules if stored else {}

    effective = []
    for entry in MODULE_CATALOG:
        key = entry["key"]
        enabled = stored_modules[key] if key in stored_modules else entry["default_enabled"]
        effective.append({
            "key": key,
            "label": entry["label"],
            "category": entry["category"],
            "real_capability": entry["real_capability"],
            "default_enabled": entry["default_enabled"],
            "enabled": bool(enabled),
            "is_override": key in stored_modules and stored_modules[key] != entry["default_enabled"],
        })

    return effective


def get_dealer_module_config(dealer_id):

    stored = registry.get(dealer_id)

    return {
        "dealer_id": dealer_id,
        "modules": _effective_modules(dealer_id),
        "updated_by": stored.updated_by if stored else None,
        "updated_at": stored.updated_at if stored else None,
        "enforcement_note": (
            "Hub-side configuration record only. Tenant-side enforcement -- "
            "actually gating this dealer's own backend process on these values "
            "-- is not built yet; see this module's own docstring."
        ),
    }


def set_module_enabled(dealer_id, module_key, enabled, updated_by="nxtdeal_staff"):

    if not dealer_registry.get(dealer_id):
        return None, f"no dealer with id '{dealer_id}'"

    if module_key not in MODULE_KEYS:
        return None, f"unknown module_key '{module_key}' -- must be one of {sorted(MODULE_KEYS)}"

    stored = registry.get(dealer_id)
    if not stored:
        stored = DealerModuleConfig(dealer_id=dealer_id, modules=dict(MODULE_DEFAULTS))
        registry.add(stored)

    stored.modules[module_key] = bool(enabled)
    stored.updated_by = updated_by
    stored.updated_at = _now_iso()

    registry.add(stored)

    return get_dealer_module_config(dealer_id), None
