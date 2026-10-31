"""
NXTDeal Hub -- the emergency-response half of security-hardening pass Task
#6 ("Expand AI kill switch to dealer/department/bot/workflow scope"). Lets a
NXTDeal staffer see one dealer's real, live AI Kill Switch state and, in a
genuine incident, push a real emergency stop to that dealer's own tenant
process directly from the Hub console -- without needing that dealer's own
employee credentials.

Two real tenant-side routes back this (backend/api/routers/ai_kill_switch.py,
backend/core/ai_kill_switch_network_api.py), gated by the SAME
DEALEROS_NETWORK_KEY shared secret every other Hub<->tenant server-to-server
route already uses (hub_core/dealer_ai_management.py's own
/network/ai-management-snapshot pull, hub_core/tenant_storage_metrics.py's
/network/storage-snapshot pull, hub_core/network_collector.py's anonymized
peer-benchmark pull) -- reused directly, no second shared-secret scheme.

Deliberately DEALER-IDENTIFIED, not anonymized -- same reasoning
hub_core/dealer_ai_management.py's own docstring already gives for that same
distinction: DEALEROS_NETWORK_KEY authenticates the Hub as a legitimate
server-to-server caller, anonymization is a separate design choice specific
to the cross-network peer-benchmark feature, not a blanket rule attached to
the key itself. A kill-switch push has to be dealer-identified by definition
-- it targets one specific, reachable dealer's own tenant process.

Two deliberate design differences from hub_core/dealer_ai_management.py's own
"fetch on demand, persist the last snapshot" pattern, both stated here rather
than silently copied:

  1. STATUS IS ALWAYS LIVE, NEVER CACHED. Unlike AI Management's own
     DealerAiSnapshot (persisted so the screen has something to show without
     a network call on every visit), this is an incident-response tool --
     showing a NXTDeal staffer a stale kill-switch state during a real
     incident would be actively dangerous (e.g. "already off" when it isn't).
     get_dealer_kill_switch_status() always makes a real, live HTTP call,
     accepting the extra latency as the right tradeoff.

  2. EVERY PUSH ATTEMPT IS A PERSISTED, PERMANENT RECORD -- success or
     failure. Unlike DealerAiSnapshot (one row per dealer, overwritten on
     every recheck), DealerKillSwitchAction is append-only, matching
     hub_core/dealer_backups.py's own DealerBackupLogEntry precedent for "an
     honest, permanent action log, not a single mutable row" -- a NXTDeal
     staffer reviewing an incident afterward needs to see every attempt that
     was made, including ones that failed (unreachable dealer, bad scope,
     etc.), not just the current state.

Every real push is also recorded to the Hub's own centralized audit log
(hub_core/hub_audit.py) via record_and_save(), same discipline every other
mutation in this whole Dealer Management / Infrastructure & Platform
Operations rebuild follows -- see hub_core/dealer_ai_kill_switch_api.py.

A pushed toggle always reaches the tenant tagged
updated_by="hub_emergency_push" (backend/core/ai_kill_switch_network_api.py's
HUB_PUSH_ACTOR) -- never a specific employee id, since no employee on that
tenant actually took the action. That tenant's own kill-switch state and
audit trail can always tell a Hub-initiated emergency stop apart from a
local admin's own action.
"""

import json
import urllib.error
import urllib.request

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.secrets import get_secret


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


_NETWORK_KEY_ENV_VAR = "DEALEROS_NETWORK_KEY"
_DEV_FALLBACK_KEY = "dev-only-insecure-network-key-change-me"
_REQUEST_TIMEOUT_SECONDS = 5

VALID_PUSH_SCOPES = ("dealer_wide", "department", "bot", "workflow_automation")


@dataclass
class DealerKillSwitchAction:
    action_id: str
    dealer_id: str
    pushed_by: str
    scope: str
    active: bool
    reason: Optional[str] = None
    department: Optional[str] = None
    success: bool = False
    # Deliberately NOT named "error" -- hub/app.py's routes almost universally
    # use `if "error" in result: raise HTTPException(...)` as a generic
    # single-key-failure-dict signal, and this dataclass's own serialized
    # dict has many other real keys alongside this one (a failed PUSH is
    # still a successful, real, persisted ACTION record -- see this module's
    # own docstring). Naming it "error" would collide with that convention
    # the exact same way hub_core/dealer_ai_management.py's own
    # "never checked yet" bug once did (fixed there by renaming to
    # "fetch_error") -- named "push_error" here for the same reason.
    push_error: Optional[str] = None
    resulting_state: Optional[dict] = None
    pushed_at: str = field(default_factory=_now_iso)

    def to_dict(self):
        return {
            "action_id": self.action_id,
            "dealer_id": self.dealer_id,
            "pushed_by": self.pushed_by,
            "scope": self.scope,
            "active": self.active,
            "reason": self.reason,
            "department": self.department,
            "success": self.success,
            "push_error": self.push_error,
            "resulting_state": self.resulting_state,
            "pushed_at": self.pushed_at,
        }

    @staticmethod
    def from_dict(data):
        return DealerKillSwitchAction(
            action_id=data["action_id"],
            dealer_id=data["dealer_id"],
            pushed_by=data.get("pushed_by", "nxtdeal_staff"),
            scope=data["scope"],
            active=data.get("active", False),
            reason=data.get("reason"),
            department=data.get("department"),
            success=data.get("success", False),
            push_error=data.get("push_error"),
            resulting_state=data.get("resulting_state"),
            pushed_at=data.get("pushed_at", _now_iso()),
        )


class DealerKillSwitchActionRegistry:

    def __init__(self):
        self.actions: Dict[str, DealerKillSwitchAction] = {}
        self.counter = 0

    def add(self, action: DealerKillSwitchAction):
        self.actions[action.action_id] = action

    def next_id(self):
        self.counter += 1
        return f"AIKS-{self.counter:05}"

    def list_for_dealer(self, dealer_id):
        return sorted(
            (a for a in self.actions.values() if a.dealer_id == dealer_id),
            key=lambda a: a.pushed_at,
            reverse=True,
        )

    def list_all(self):
        return sorted(self.actions.values(), key=lambda a: a.pushed_at, reverse=True)

    def recover_counter(self):
        highest = 0
        for action in self.actions.values():
            try:
                number = int(action.action_id.split("-")[1])
            except (IndexError, ValueError):
                continue
            highest = max(highest, number)
        self.counter = max(self.counter, highest)

    def reset(self):
        self.actions = {}
        self.counter = 0


registry = DealerKillSwitchActionRegistry()


def _network_key():
    # Reads through hub_core/secrets.py's real chokepoint (Task #13, 2026-07-20)
    # rather than os.environ directly.
    return get_secret(_NETWORK_KEY_ENV_VAR, _DEV_FALLBACK_KEY)


def _fetch_kill_switch_status(dealer):
    """Live GET {api_base_url}/network/ai-kill-switch-status. Returns
    (data, error), mirrors hub_core/dealer_ai_management.py's
    _fetch_ai_snapshot exactly."""

    if not dealer.api_base_url:
        return None, "no api_base_url on file -- not yet deployed / not yet recorded"

    url = dealer.api_base_url.rstrip("/") + "/network/ai-kill-switch-status"

    try:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-NXTDeal-Network-Key": _network_key(),
            },
        )
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        return None, f"unreachable: {error}"
    except (json.JSONDecodeError, ValueError) as error:
        return None, f"bad response: {error}"

    if "error" in data:
        return None, data["error"]

    return data, None


def _push_kill_switch(dealer, scope, active, reason, department):
    """Live POST {api_base_url}/network/ai-kill-switch-push. Returns
    (data, error) -- same shape as _fetch_kill_switch_status above."""

    if not dealer.api_base_url:
        return None, "no api_base_url on file -- not yet deployed / not yet recorded"

    url = dealer.api_base_url.rstrip("/") + "/network/ai-kill-switch-push"
    body = json.dumps({
        "scope": scope,
        "active": active,
        "reason": reason,
        "department": department,
    }).encode("utf-8")

    try:
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-NXTDeal-Network-Key": _network_key(),
            },
        )
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        return None, f"unreachable: {error}"
    except (json.JSONDecodeError, ValueError) as error:
        return None, f"bad response: {error}"

    if "error" in data:
        return None, data["error"]

    return data, None


def get_dealer_kill_switch_status(dealer_id):
    """Always a real, live fetch -- never a cached snapshot. See this
    module's own docstring for why status specifically is never cached here,
    unlike hub_core/dealer_ai_management.py's own recheck-and-persist
    pattern."""

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    data, error = _fetch_kill_switch_status(dealer)

    if error:
        return {
            "dealer_id": dealer_id,
            "dealer_name": dealer.name,
            "reachable": False,
            "fetch_error": error,
            "fetched_at": _now_iso(),
            "state": None,
        }, None

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "reachable": True,
        "fetch_error": None,
        "fetched_at": _now_iso(),
        "state": data,
    }, None


def push_kill_switch_to_dealer(dealer_id, pushed_by, scope, active, reason=None, department=None):
    """The real emergency-stop action. Always creates and persists a
    DealerKillSwitchAction record, whether the push actually succeeded or
    not -- an honest, permanent incident-review trail, not just a live
    status the moment nobody's looking at it. See this module's own
    docstring for why this differs from hub_core/dealer_ai_management.py's
    own single-row-overwritten snapshot."""

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    if not pushed_by or not pushed_by.strip():
        return None, "pushed_by is required"

    if scope not in VALID_PUSH_SCOPES:
        return None, f"Unknown kill-switch scope '{scope}'. Valid: {VALID_PUSH_SCOPES}"

    if scope == "department" and not department:
        return None, "A department is required when scope='department'."

    data, error = _push_kill_switch(dealer, scope, bool(active), reason, department)

    action = DealerKillSwitchAction(
        action_id=registry.next_id(),
        dealer_id=dealer_id,
        pushed_by=pushed_by.strip(),
        scope=scope,
        active=bool(active),
        reason=(reason or "").strip() or None,
        department=department,
        success=data is not None,
        push_error=error,
        resulting_state=data.get("state") if data else None,
    )
    registry.add(action)

    return action, None


def list_kill_switch_actions_for_dealer(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "actions": [a.to_dict() for a in registry.list_for_dealer(dealer_id)],
    }, None


def list_all_kill_switch_actions():

    all_actions = registry.list_all()

    dealers_by_id = {d.dealer_id: d for d in dealer_registry.list_all()}

    return {
        "actions": [
            {
                **a.to_dict(),
                "dealer_name": dealers_by_id[a.dealer_id].name if a.dealer_id in dealers_by_id else None,
            }
            for a in all_actions
        ],
        "summary": {
            "total_actions": len(all_actions),
            "successful_pushes": len([a for a in all_actions if a.success]),
            "failed_pushes": len([a for a in all_actions if not a.success]),
        },
        "note": (
            "Every real emergency-stop push attempted from this Hub, "
            "success or failure -- a permanent incident-review record, not "
            "just current state."
        ),
    }
