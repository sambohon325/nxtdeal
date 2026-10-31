"""
NXTDeal Hub -- "Dealer Management" rebuild, slice 5 of 5: Audit Center.

Sam's ask: "AUDIT CENTER: Track: Module Changes, Permission Changes, Billing
Changes, Feature Enablements."

REAL -- every mutating action across slices 1-4 of this rebuild is already a
genuine Hub-side event (a dealer's status changed, a module was toggled, a
feature flag override was created/deleted, an onboarding step was marked
complete, a migration readiness percentage was recorded, an integration was
added/updated/removed). None of that was ever logged anywhere before this
slice -- this module is a small, real, append-only Hub-side audit log,
mirroring backend/core/audit.py's own AuditEvent/AuditLog shape exactly (same
dataclass fields, same id-counter-recovery-on-load convention) rather than
inventing a second pattern.

CATEGORY MAPPING -- Sam named 4 categories (Module Changes / Permission
Changes / Billing Changes / Feature Enablements), but the real mutating event
types across slices 1-4 don't cleanly sort into only those 4. Rather than
force-fit or silently drop anything, a 5th honest "other" bucket exists for
events that don't cleanly belong to one of Sam's 4 -- every real event type
this module records is accounted for below, with the reasoning for each
non-obvious placement stated explicitly:

  module_change:        module_enabled_changed (a Module Management toggle,
                         Sam's own literal category)
  permission_change:    feature_flag_override_created,
                         feature_flag_override_deleted -- a feature-flag
                         override IS, definitionally, a scoped grant/revoke
                         of permission to use a feature for one dealer/group,
                         the closest real analog this codebase has to a
                         "permission change" at the Hub level (there is no
                         separate Hub-side RBAC/user-permission model to log
                         instead -- see the Users item's own scope note).
  billing_change:        dealer_subscription_updated (plan_tier/seat_count/
                         renewal_date -- literally billing/subscription data)
  feature_enablement:    onboarding_step_completed -- each step completion is,
                         definitionally, "this capability/milestone is now
                         enabled" for that dealer.
  other:                 dealer_status_changed, dealer_profile_updated,
                         dealer_api_base_url_updated, dealer_version_updated,
                         migration_source_set, migration_readiness_set,
                         integration_added, integration_updated,
                         integration_removed, dealer_contact_added,
                         dealer_contact_removed, network_membership_updated --
                         real, valuable events that don't cleanly fit any of
                         Sam's 4 named buckets; reported honestly as "other"
                         rather than mislabeled.

In-memory only + explicit save/load, same convention as every other Hub
sub-registry (hub/hub_core/dealer_onboarding.py, hub/hub_core/dealer_modules.py) --
NOT wired to backend/core/audit.py in any way; this is a genuinely separate,
Hub-scoped log of Hub-staff actions, not a tenant-side employee-action log.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


CATEGORY_LABELS = {
    "module_change": "Module Changes",
    "permission_change": "Permission Changes",
    "billing_change": "Billing Changes",
    "feature_enablement": "Feature Enablements",
    "other": "Other Hub Actions",
}

EVENT_TYPE_CATEGORY = {
    "module_enabled_changed": "module_change",
    "feature_flag_override_created": "permission_change",
    "feature_flag_override_deleted": "permission_change",
    "dealer_subscription_updated": "billing_change",
    "onboarding_step_completed": "feature_enablement",
    "dealer_status_changed": "other",
    "dealer_profile_updated": "other",
    "dealer_api_base_url_updated": "other",
    "dealer_version_updated": "other",
    "migration_source_set": "other",
    "migration_readiness_set": "other",
    "integration_added": "other",
    "integration_updated": "other",
    "integration_removed": "other",
    "dealer_contact_added": "other",
    "dealer_contact_removed": "other",
    "network_membership_updated": "other",
    # Infrastructure & Platform Operations rebuild, slice 2 of 4 (Backups) --
    # a real NXTDeal-staff backup confirmation isn't one of Sam's 4 named
    # categories either; honest "other," same reasoning as every event
    # type above it in this list.
    "dealer_backup_logged": "other",
    # NXTDeal Network Connect (2026-07-19) -- Hub backend foundation. See
    # hub_core/network_connect.py's own module docstring for the full privacy
    # design; these are the identified-account-side mutations only (signup,
    # connected-system tracking, tier/status changes, migration readiness,
    # conversion to a real Dealer). A tier change is real billing/
    # subscription data, same reasoning dealer_subscription_updated already
    # established -- "billing_change." Converting an account to a real
    # Dealer is, definitionally, "the full NXTDeal platform is now enabled
    # for this account," the same reasoning onboarding_step_completed
    # already established for "feature_enablement." Everything else here is
    # real and valuable but doesn't cleanly fit any of Sam's 4 named
    # buckets -- honest "other," same as every other non-obvious placement
    # above.
    "network_connect_account_created": "other",
    "network_connect_connected_system_set": "other",
    "network_connect_tier_changed": "billing_change",
    "network_connect_status_changed": "other",
    "network_connect_migration_readiness_set": "other",
    "network_connect_converted_to_dealer": "feature_enablement",
    # AI-Powered Self-Auditing Code Layer (2026-07-19) -- a code-quality
    # scan running, an auto-fix landing on its own branch, or a human
    # approving/rejecting/dismissing a finding are all real, valuable Hub
    # events but none of them are a dealer module/permission/billing/
    # feature change -- honest "other," same reasoning as every other
    # non-obvious placement above.
    "code_audit_run_completed": "other",
    "code_audit_finding_auto_fixed": "other",
    "code_audit_finding_approved": "other",
    "code_audit_finding_rejected": "other",
    "code_audit_finding_resolved": "other",
    "code_audit_finding_dismissed": "other",
    # Security-hardening pass, Task #6 (2026-07-20) -- a NXTDeal staffer
    # pushing a real emergency AI stop to a dealer's own tenant process from
    # the Hub console (hub_core/dealer_ai_kill_switch.py). Not a clean fit
    # for any of Sam's 4 named categories (it's neither a module/permission/
    # billing/feature change in the ordinary sense -- it's an emergency
    # safety action) -- honest "other," same reasoning as every other
    # non-obvious placement above.
    "ai_kill_switch_pushed": "other",
}


def category_for(event_type):
    return EVENT_TYPE_CATEGORY.get(event_type, "other")


@dataclass
class HubAuditEvent:
    id: str
    event_type: str
    dealer_id: Optional[str]
    actor: str
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "event_type": self.event_type,
            "category": category_for(self.event_type),
            "category_label": CATEGORY_LABELS[category_for(self.event_type)],
            "dealer_id": self.dealer_id,
            "actor": self.actor,
            "summary": self.summary,
            "details": self.details,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data):
        return HubAuditEvent(
            id=data["id"],
            event_type=data["event_type"],
            dealer_id=data.get("dealer_id"),
            actor=data.get("actor", "nxtdeal_staff"),
            summary=data.get("summary", ""),
            details=dict(data.get("details", {})),
            timestamp=data.get("timestamp", _now_iso()),
        )


class HubAuditLog:

    def __init__(self):
        self.events: List[HubAuditEvent] = []
        self._counter = 0

    def record(self, event_type, summary, dealer_id=None, actor="nxtdeal_staff", details=None):

        self._counter += 1

        event = HubAuditEvent(
            id=f"HAUDIT-{self._counter:05}",
            event_type=event_type,
            dealer_id=dealer_id,
            actor=actor,
            summary=summary,
            details=details or {},
        )

        self.events.append(event)

        return event

    def get_all(self):
        return list(self.events)

    def get_for_dealer(self, dealer_id):
        return [e for e in self.events if e.dealer_id == dealer_id]

    def get_by_category(self, category):
        return [e for e in self.events if category_for(e.event_type) == category]

    def reset(self):
        self.events = []
        self._counter = 0

    def load_events(self, events):
        """Replace in-memory events with a list already loaded from disk,
        preserving the counter so newly recorded events don't collide with
        restored ids -- mirrors backend/core/audit.py's AuditLog.load_events()."""

        self.events = list(events)

        highest = 0
        for event in self.events:
            try:
                suffix = int(event.id.split("-")[-1])
            except (ValueError, IndexError):
                continue
            highest = max(highest, suffix)

        self._counter = highest


hub_audit_log = HubAuditLog()
