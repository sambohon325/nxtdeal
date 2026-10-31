"""
NXTDeal Hub -- "Dealer Management" rebuild, slice 4 of 5: AI Management
(per-dealer).

Sam's ask: "AI MANAGEMENT -- very important. Manage: Sales AI/Service AI/
Finance AI/Marketing AI/Collections AI per dealer. AI Consumption, track:
Prompts/Tokens/Costs/Actions Created."

REAL, via a new, narrowly-scoped tenant-side route (decided this session,
documented here rather than silently assumed): GET /network/ai-management-
snapshot (backend/core/ai_management.py's build_ai_management_network_
snapshot(), backend/core/ai_management_network_api.py), gated by the SAME
DEALEROS_NETWORK_KEY shared secret hub/hub_core/network_collector.py already uses
for the (anonymized) peer-benchmark snapshot. This is judged safe to build
because the underlying data is genuinely as coarse as that already-shipped
precedent: a static feature-name catalog (12 real AI-backed features across
this codebase, see backend/core/ai_management.py's AI_FEATURE_CATALOG) plus
4 plain integer call-attempt counters per feature (attempted/succeeded/
fell_back/blocked) -- no endpoint URLs, no freeform text, no customer or
employee record anywhere in the payload. See backend/core/ai_management.py's
build_ai_management_network_snapshot() docstring for the full reasoning, and
compare hub/hub_core/dealer_integrations.py's own docstring for why Integrations
Center landed on the OPPOSITE (Hub-side manual) side of this same judgment
call -- Connection.endpoint_url + no provider-name catalog made that a
meaningfully different, less clearly safe read.

Unlike hub/hub_core/network_collector.py's peer-benchmark pull (deliberately
ANONYMIZED, keyed only by an unlinkable pseudonym -- see that module's own
docstring), this fetch is deliberately DEALER-IDENTIFIED on the Hub side, the
same way hub/hub_core/server_health.py's reachability check and hub/hub_core/
dealer_onboarding.py's Network Connected check already tie a live check
directly back to one dealer_id. DEALEROS_NETWORK_KEY's job is authenticating
the Hub as a legitimate server-to-server caller; anonymization is a design
choice specific to the cross-network peer-benchmark feature, not a blanket
rule attached to the key itself.

Fetched ON DEMAND (a "Recheck" action), not on every page load -- same
reasoning dealer_onboarding.py's Network Connected check already gives: a
live HTTP round trip is too slow/expensive to run on every view. The last
fetched snapshot is persisted (DealerAiSnapshot) so the AI Management screen
has something to show without a network call on every visit.

The 5 named AI "areas" Sam asked for (Sales AI/Service AI/Finance AI/
Marketing AI/Collections AI) do NOT exist as a real grouping anywhere in the
tenant's own AI_FEATURE_CATALOG -- that catalog is organized by literal
feature (Email Wizard, Website Wizard, Social Caption Wizard, etc.), not by
department. AI_AREA_CATALOG below is this Hub's own best-judgment mapping of
those 12 real features onto Sam's 5 named areas (documented per-area, not
guessed silently) -- most real AI capability in this codebase today lives in
Marketing; there is currently ZERO real AI-backed feature anywhere in the
tenant codebase for Service or Finance, and Collections' own risk-scoring
engine (backend/core/collections.py) is DELIBERATELY a transparent rules
engine, not an AI/LLM call (that module's own "real rules, not fake AI"
convention, confirmed by reading its docstring before writing this mapping)
-- so Service AI/Finance AI/Collections AI report a real, honest zero-feature
gap rather than a fabricated capability. Cross-department features
(ai_assistant, workspace_explain, ai_business_analyst, network_advisors,
readiness_executive_summary, network_executive_summary, help_assistant) are
mostly bucketed into a 6th "other_ai" area rather than forced into one of
Sam's 5, so every one of the 12 real features is still accounted for
somewhere (ai_assistant is the one exception -- it's the main workspace
assistant used heavily on Sales screens, so it's counted toward Sales AI, with
that judgment call stated plainly here rather than hidden).

AI CONSUMPTION -- Prompts/Tokens/Costs/Actions Created: confirmed via reading
backend/core/ai_management.py in full that NO token count, dollar cost, or
"action created" tracking model exists anywhere in this codebase -- only the
4 real call-attempt counters described above. This module reports the real
'attempted' counter as the closest honest proxy for "Prompts," and states
plainly, not silently, that Tokens/Costs/Actions Created have no backing data
model anywhere -- consistent with every other honest-gap note in this
codebase (e.g. backend/core/finance_menu.py's Commissions gap, backend/core/
sales_menu.py's Appointments gap before session 96 built one).
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


# (area_key, label, [real AI_FEATURE_CATALOG keys mapped to this area]) -- see
# this module's own docstring for the reasoning behind each mapping.
AI_AREA_CATALOG = [
    (
        "sales_ai", "Sales AI",
        ["ai_assistant"],
    ),
    (
        "service_ai", "Service AI",
        [],
    ),
    (
        "finance_ai", "Finance AI",
        [],
    ),
    (
        "marketing_ai", "Marketing AI",
        [
            "email_sms_wizard", "website_wizard", "social_caption_wizard",
            "reputation_autorespond", "website_ai_receptionist", "advertising_ai",
        ],
    ),
    (
        "collections_ai", "Collections AI",
        [],
    ),
    (
        "other_ai", "Other / Cross-Department AI",
        [
            "help_assistant", "workspace_explain", "readiness_executive_summary",
            "network_executive_summary", "ai_business_analyst", "network_advisors",
        ],
    ),
]

AI_AREA_LABEL = {key: label for key, label, _ in AI_AREA_CATALOG}

_CONSUMPTION_NOTE = (
    "'Prompts (attempted)' below is the closest real proxy this codebase has "
    "for a prompt count -- it is a real, in-memory, per-process call-attempt "
    "counter (backend/core/ai_management.py), not a literal prompt log. No "
    "token count, no dollar cost, and no 'AI action created' concept is "
    "tracked anywhere in this codebase today -- an honest, confirmed gap, not "
    "a fabricated number. Counters reset to zero on every tenant process "
    "restart."
)


@dataclass
class DealerAiSnapshot:
    dealer_id: str
    fetched_at: Optional[str] = None
    reachable: bool = False
    error: Optional[str] = None
    features: List[dict] = field(default_factory=list)
    tenant_note: Optional[str] = None

    def to_dict(self):
        return {
            "dealer_id": self.dealer_id,
            "fetched_at": self.fetched_at,
            "reachable": self.reachable,
            "error": self.error,
            "features": self.features,
            "tenant_note": self.tenant_note,
        }

    @staticmethod
    def from_dict(data):
        return DealerAiSnapshot(
            dealer_id=data["dealer_id"],
            fetched_at=data.get("fetched_at"),
            reachable=data.get("reachable", False),
            error=data.get("error"),
            features=list(data.get("features", [])),
            tenant_note=data.get("tenant_note"),
        )


class DealerAiSnapshotRegistry:

    def __init__(self):
        self.snapshots: Dict[str, DealerAiSnapshot] = {}

    def get(self, dealer_id):
        return self.snapshots.get(dealer_id)

    def add(self, snapshot: DealerAiSnapshot):
        self.snapshots[snapshot.dealer_id] = snapshot

    def list_all(self):
        return sorted(self.snapshots.values(), key=lambda s: s.dealer_id)

    def reset(self):
        self.snapshots = {}


registry = DealerAiSnapshotRegistry()


def _fetch_ai_snapshot(dealer):
    """Live GET {api_base_url}/network/ai-management-snapshot for one dealer.
    Returns (data, error) -- mirrors hub/hub_core/dealer_onboarding.py's
    _check_network_connected shape exactly."""

    if not dealer.api_base_url:
        return None, "no api_base_url on file -- not yet deployed / not yet recorded"

    url = dealer.api_base_url.rstrip("/") + "/network/ai-management-snapshot"
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
        return None, f"unreachable: {error}"
    except (json.JSONDecodeError, ValueError) as error:
        return None, f"bad response: {error}"

    if "error" in data:
        return None, data["error"]

    if "features" not in data:
        return None, "reachable, but the response was missing a 'features' list -- not treated as valid"

    return data, None


def recompute_dealer_ai_snapshot(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    data, error = _fetch_ai_snapshot(dealer)

    snapshot = DealerAiSnapshot(
        dealer_id=dealer_id,
        fetched_at=_now_iso(),
        reachable=data is not None,
        error=error,
        features=data["features"] if data else [],
        tenant_note=data.get("note") if data else None,
    )

    registry.add(snapshot)

    return snapshot, None


def _areas_from_features(features):

    by_key = {f["key"]: f for f in features}

    areas = []
    for area_key, label, feature_keys in AI_AREA_CATALOG:
        mapped = [by_key[k] for k in feature_keys if k in by_key]
        areas.append({
            "key": area_key,
            "label": label,
            "feature_count": len(feature_keys),
            "mapped_feature_count": len(mapped),
            "enabled_count": len([f for f in mapped if f["enabled"]]),
            "total_attempted": sum(f["attempted"] for f in mapped),
            "total_succeeded": sum(f["succeeded"] for f in mapped),
            "total_fell_back": sum(f["fell_back"] for f in mapped),
            "total_blocked": sum(f["blocked"] for f in mapped),
            "features": mapped,
            "gap_note": (
                None if feature_keys else
                "No real AI-backed feature exists anywhere in the tenant "
                f"codebase for {label} yet -- an honest gap, not a "
                "placeholder standing in for something real."
            ),
        })

    return areas


def get_dealer_ai_management(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    snapshot = registry.get(dealer_id)

    if not snapshot:
        return {
            "dealer_id": dealer_id,
            "dealer_name": dealer.name,
            "checked": False,
            "reachable": False,
            "fetch_error": None,
            "fetched_at": None,
            "areas": _areas_from_features([]),
            "consumption_note": _CONSUMPTION_NOTE,
            "note": (
                "Never checked yet -- click Recheck to pull this dealer's "
                "real, live AI feature/call-count snapshot."
            ),
        }, None

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "checked": True,
        "reachable": snapshot.reachable,
        "fetch_error": snapshot.error,
        "fetched_at": snapshot.fetched_at,
        "areas": _areas_from_features(snapshot.features),
        "consumption_note": _CONSUMPTION_NOTE,
        "note": snapshot.tenant_note or (
            "Live-fetched just now from this dealer's own "
            "/network/ai-management-snapshot endpoint -- real per-feature "
            "enabled state + call-attempt counters."
            if snapshot.reachable else
            "Last recheck could not reach this dealer's instance -- see 'fetch_error'."
        ),
    }, None


def list_ai_area_catalog():
    return [
        {"key": key, "label": label, "feature_keys": feature_keys}
        for key, label, feature_keys in AI_AREA_CATALOG
    ]
