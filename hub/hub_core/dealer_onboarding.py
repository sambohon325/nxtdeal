"""
NXTDeal Hub -- "Dealer Management" rebuild, slice 3 of 5: Onboarding Center
(the first half of the "Provisioning" menu item -- see hub_core/dealer_migration.py
for the second half, Migration Tracking).

Sam's ask: "ONBOARDING CENTER -- massive priority. Setup Wizard, track: Dealer
Created / Users Invited / Inventory Imported / CRM Imported / Website
Connected / Network Connected / Go Live."

REAL vs. HONEST-MANUAL, decided per step after checking what's actually
cheaply verifiable over HTTP without a real employee session token. Every
route in backend/api/app.py other than `/`, `/auth/login`, and
`/network/anonymous-snapshot` requires an `Authorization: Bearer <token>`
this Hub has no way to obtain for a dealer it didn't just provision with a
throwaway temp password (and even then, using that admin's own real login
credential from inside the Hub would blur the "Hub manages tenants from
outside their process" boundary this whole architecture is built on -- see
CLAUDE.md's "NXTDeal Hub / Multi-Tenant Architecture" section). So:

  - Dealer Created   -> REAL, AUTOMATIC. Trivially true the moment an
    onboarding status record exists at all, since one is only ever created
    for a dealer_id already present in hub_core/dealer_registry.py's own
    registry (see _ensure_status below) -- there is nothing to check, it's
    definitionally satisfied.

  - Network Connected -> REAL, AUTOMATIC, checked on-demand via the
    "Recheck" action (not on every GET -- see _check_network_connected
    below, a live HTTP round trip is too slow/expensive to run on every
    page load). Reuses the exact same real, already-shipped mechanism
    hub/hub_core/network_collector.py already established: a live GET to this
    specific dealer's own `{api_base_url}/network/anonymous-snapshot`,
    gated by the same DEALEROS_NETWORK_KEY shared secret. A 200 response
    carrying a real pseudonym + at least one department's worth of KPI data
    is genuine proof this dealer's backend is reachable AND its
    network-intelligence pipeline is actually wired and producing real
    data -- not a guess dressed up as a check.

    PRIVACY NOTE -- the same hard rule as everywhere else in this Hub:
    the pseudonym value in that response is read ONLY to confirm the
    response shape is well-formed. It is never stored, logged, returned by
    this module's own functions, or persisted anywhere in
    hub/storage/dealer_onboarding.json. Knowing THAT dealer X's own
    instance responded successfully just now is the same class of honest
    operational telemetry hub/hub_core/network_collector.py's own docstring
    already draws this exact boundary around ("dealers_reporting/
    dealers_unreachable... never stored alongside the anonymized snapshot
    data itself") -- this module follows the identical line. Nothing here
    ever joins a pseudonym back to a dealer_id in a persisted record.

  - Users Invited / Inventory Imported / CRM Imported / Website Connected /
    Go Live -> HONEST MANUAL. No unauthenticated tenant-side route exposes
    an aggregate employee/credential count, an inventory-import signal, a
    CRM/lead-import signal, or a "does this dealer have a published
    website" aggregate -- every one of those lives behind the tenant's own
    employee auth (confirmed by reading backend/api/app.py's route table
    before writing this module: every route but the three named above
    calls `_authenticate(authorization)` or a stricter variant of it).
    Rather than approximate any of them off an unrelated bucketed KPI (a
    fragile, misleading inference -- e.g. a real dealer could have full
    inventory and zero recent sales, or vice versa), these stay real,
    NXTDeal-staff-toggleable checklist items. That is a completely
    legitimate, real feature on its own, not a placeholder standing in for
    something better.

    "Go Live" in particular is deliberately a MANUAL, terminal confirmation
    step here -- distinct from the separate, real, RULE-BASED "Go-Live
    Tracker" status in hub_core/dealer_migration.py (Blocked / At Risk /
    Ready, computed off recorded migration-readiness percentages). Marking
    a dealer's onboarding wizard "Go Live" complete is a real business
    decision a NXTDeal staffer makes, not something to auto-derive --
    enforced below by refusing to mark it complete until every other step
    already is (a real, useful integrity rule, not fabrication).

A step marked "auto" in ONBOARDING_STEPS can only ever be set via its own
real check (recompute_auto_steps below) -- set_manual_step() explicitly
rejects an attempt to hand-toggle an auto step, so a staffer can never
silently overwrite a real, computed result with a fabricated "yes."
"""

import json
import urllib.error
import urllib.request

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.secrets import get_secret


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


ONBOARDING_STEPS = [
    ("dealer_created", "Dealer Created", "auto"),
    ("users_invited", "Users Invited", "manual"),
    ("inventory_imported", "Inventory Imported", "manual"),
    ("crm_imported", "CRM Imported", "manual"),
    ("website_connected", "Website Connected", "manual"),
    ("network_connected", "Network Connected", "auto"),
    ("go_live", "Go Live", "manual"),
]

STEP_KEYS = {key for key, _, _ in ONBOARDING_STEPS}
STEP_LABELS = {key: label for key, label, _ in ONBOARDING_STEPS}
STEP_BASIS = {key: basis for key, _, basis in ONBOARDING_STEPS}

ONBOARDING_STEP_CATALOG = [
    {"key": key, "label": label, "basis": basis}
    for key, label, basis in ONBOARDING_STEPS
]

_NETWORK_KEY_ENV_VAR = "DEALEROS_NETWORK_KEY"
_DEV_FALLBACK_KEY = "dev-only-insecure-network-key-change-me"
_REQUEST_TIMEOUT_SECONDS = 5


def _empty_step_state():
    return {
        "complete": False,
        "basis": "not_started",
        "completed_at": None,
        "completed_by": None,
        "note": None,
    }


@dataclass
class DealerOnboardingStatus:
    dealer_id: str
    steps: Dict[str, dict] = field(default_factory=dict)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self):
        return {
            "dealer_id": self.dealer_id,
            "steps": self.steps,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data):
        return DealerOnboardingStatus(
            dealer_id=data["dealer_id"],
            steps=dict(data.get("steps", {})),
            updated_at=data.get("updated_at", _now_iso()),
        )


class DealerOnboardingRegistry:

    def __init__(self):
        self.statuses = {}

    def get(self, dealer_id):
        return self.statuses.get(dealer_id)

    def add(self, status: DealerOnboardingStatus):
        self.statuses[status.dealer_id] = status

    def list_all(self):
        return sorted(self.statuses.values(), key=lambda s: s.dealer_id)

    def reset(self):
        self.statuses = {}


registry = DealerOnboardingRegistry()


def _ensure_status(dealer_id):
    """A DealerOnboardingStatus only ever gets created here, for a dealer_id
    already confirmed to exist in hub_core/dealer_registry.py -- callers below
    all check dealer_registry.get(dealer_id) first. dealer_created is set
    real+true the instant a record is created, since that's definitionally
    what having a record here means."""

    status = registry.get(dealer_id)

    if not status:
        status = DealerOnboardingStatus(
            dealer_id=dealer_id,
            steps={key: _empty_step_state() for key in STEP_KEYS},
        )
        status.steps["dealer_created"] = {
            "complete": True,
            "basis": "auto",
            "completed_at": _now_iso(),
            "completed_by": "system",
            "note": "Real -- this dealer_id already exists in the Hub's own registry.",
        }
        registry.add(status)
        return status

    # Backfill: a status created before a new step key was added to
    # ONBOARDING_STEPS won't have it yet -- additive self-heal, same
    # convention backend/core/system_config.py's own _get_or_create() has
    # already established elsewhere in this codebase.
    changed = False
    for key in STEP_KEYS:
        if key not in status.steps:
            status.steps[key] = _empty_step_state()
            changed = True
    if changed:
        registry.add(status)

    return status


def _check_network_connected(dealer):
    """Live HTTP call to this dealer's own /network/anonymous-snapshot -- the
    exact same real endpoint + pattern hub/hub_core/network_collector.py already
    uses for real cross-network collection. Returns (complete: bool,
    note: str). See this module's own docstring's PRIVACY NOTE -- the
    pseudonym/department payload is inspected only to confirm well-formedness,
    never stored, logged, or returned by this function."""

    if not dealer.api_base_url:
        return False, "no api_base_url on file -- not yet deployed / not yet recorded"

    url = dealer.api_base_url.rstrip("/") + "/network/anonymous-snapshot"
    # Reads through hub_core/secrets.py's real chokepoint (Task #13, 2026-07-20)
    # rather than os.environ directly.
    network_key = get_secret(_NETWORK_KEY_ENV_VAR, _DEV_FALLBACK_KEY)

    try:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-NXTDeal-Network-Key": network_key,
            },
        )
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        return False, f"unreachable: {error}"
    except (json.JSONDecodeError, ValueError) as error:
        return False, f"bad response: {error}"

    if "error" in data:
        return False, data["error"]

    if not data.get("pseudonym") or not data.get("departments"):
        return False, (
            "reachable, but the response was missing a pseudonym or department "
            "data -- not treated as connected"
        )

    return True, (
        "Live-verified just now: this dealer's own /network/anonymous-snapshot "
        "responded with a real, well-formed pseudonym + department payload."
    )


def recompute_auto_steps(dealer_id):
    """Runs the real checks for every step marked "auto" and stores the
    result. Does NOT touch any manual step's state."""

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    status = _ensure_status(dealer_id)

    status.steps["dealer_created"] = {
        "complete": True,
        "basis": "auto",
        "completed_at": status.steps["dealer_created"].get("completed_at") or _now_iso(),
        "completed_by": "system",
        "note": "Real -- this dealer_id already exists in the Hub's own registry.",
    }

    connected, note = _check_network_connected(dealer)
    status.steps["network_connected"] = {
        "complete": connected,
        "basis": "auto",
        "completed_at": _now_iso() if connected else None,
        "completed_by": "system (live network check)" if connected else None,
        "note": note,
    }

    status.updated_at = _now_iso()
    registry.add(status)

    return status.to_dict(), None


def set_manual_step(dealer_id, step_key, complete, updated_by="nxtdeal_staff", note=None):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    if step_key not in STEP_KEYS:
        return None, f"unknown step_key '{step_key}' -- must be one of {sorted(STEP_KEYS)}"

    if STEP_BASIS[step_key] == "auto":
        return None, (
            f"'{step_key}' is a real, automatically-checked step -- use the "
            "Recheck action instead of manually toggling it."
        )

    status = _ensure_status(dealer_id)

    if step_key == "go_live" and complete:
        incomplete = [
            STEP_LABELS[key]
            for key, _, _ in ONBOARDING_STEPS
            if key != "go_live" and not status.steps.get(key, _empty_step_state())["complete"]
        ]
        if incomplete:
            return None, (
                "Cannot mark Go Live complete -- these steps aren't complete yet: "
                + ", ".join(incomplete)
            )

    status.steps[step_key] = {
        "complete": bool(complete),
        "basis": "manual",
        "completed_at": _now_iso() if complete else None,
        "completed_by": updated_by if complete else None,
        "note": note,
    }

    status.updated_at = _now_iso()
    registry.add(status)

    return status.to_dict(), None


def get_onboarding_status(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    status = _ensure_status(dealer_id)

    steps_out = []
    for key, label, catalog_basis in ONBOARDING_STEPS:
        state = status.steps.get(key, _empty_step_state())
        steps_out.append({
            "key": key,
            "label": label,
            "catalog_basis": catalog_basis,
            **state,
        })

    complete_count = len([s for s in steps_out if s["complete"]])

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "steps": steps_out,
        "complete_count": complete_count,
        "total_steps": len(ONBOARDING_STEPS),
        "progress_pct": round(complete_count / len(ONBOARDING_STEPS) * 100, 1),
        "updated_at": status.updated_at,
        "note": (
            "'auto' steps (Dealer Created, Network Connected) are real, checked "
            "signals -- Network Connected is only refreshed when the Recheck "
            "action is run, not on every view. Every other step is honest manual "
            "data entry by a NXTDeal staffer -- no unauthenticated tenant-side "
            "signal exists to compute them automatically. See hub_core/"
            "dealer_onboarding.py's own module docstring for the full reasoning."
        ),
    }, None


def list_all_onboarding_summaries():

    summaries = []
    for dealer in dealer_registry.list_all():
        result, _ = get_onboarding_status(dealer.dealer_id)
        summaries.append({
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "slug": dealer.slug,
            "complete_count": result["complete_count"],
            "total_steps": result["total_steps"],
            "progress_pct": result["progress_pct"],
        })

    return summaries
