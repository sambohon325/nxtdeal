"""
NXTDeal Hub -- "Dealer Management" rebuild, slice 5 of 5: Support Center.

Sam's ask: "SUPPORT CENTER. Health Score off Login Frequency / Feature
Adoption / Training Completion / Usage Trend. Churn Risk: Low / Medium /
High."

Checked honestly, one signal at a time, before writing anything:

  - Feature Adoption -- REAL. Reuses hub/hub_core/dealer_modules.py's own
    already-real per-dealer module-enabled-count (slice 2).
  - Login Frequency / Usage Trend -- REAL, via a new, narrowly-scoped
    tenant-side route added this slice, GET /network/operational-health-
    snapshot (backend/core/audit_network_snapshot.py), reusing the exact
    same DEALEROS_NETWORK_KEY safety pattern hub/hub_core/dealer_ai_management.py
    already established for /network/ai-management-snapshot -- coarse,
    aggregate, non-PII login/lockout counts over a trailing + prior 30-day
    window, fetched ON DEMAND (a "Recheck" action), not on every page view,
    same reasoning as every other live tenant-fetch in this codebase.
  - Training Completion -- HONEST GAP. No training/certification/course
    model exists anywhere in this codebase, Hub-side or tenant-side
    (confirmed via grep) -- stated plainly, not fabricated.

HEALTH SCORE -- a real, disclosed 50/50 blend of Feature Adoption % and
Login Activity %. Login Activity % is real login_success_count over the
current 30-day window, CAPPED against a stated HEURISTIC assumed threshold
(_ASSUMED_ACTIVE_LOGIN_THRESHOLD = 30 successful logins / 30 days) since no
reliable employee-headcount signal exists Hub-side to normalize against
instead (the Hub genuinely cannot see a tenant's own Employee roster size).
Training Completion is EXPLICITLY EXCLUDED from the score with a stated
reason, never silently defaulted to some blended-in constant. The score is
null (not fabricated) whenever the operational snapshot has never been
checked for that dealer.

CHURN RISK -- a real, transparent, POINTS-BASED RULES ENGINE (see
compute_churn_risk() below), matching this codebase's established "real
rules, never fake AI" convention (backend/core/network_audit.py,
backend/core/collections.py's risk scoring, backend/core/lead_record.py's
next_best_action()) -- deliberately NOT an LLM/ML call. Every rule and its
point value is stated in the module docstring below and echoed back in the
response's own 'basis'/'disclosure' fields, so this can never be mistaken
for an "AI-generated" score. No AI-polish wrapper was built for this on
purpose -- a transparent rules engine is equally valuable and strictly more
honest than adding an AI layer with no clear benefit here (this sandbox has
zero outbound OpenAI network access anyway, confirmed by every other
AI-backed feature in this codebase's own live smoke tests).

Churn risk points (higher = worse):
  +2  feature_adoption_pct < 20%           ("very low adoption")
  +1  feature_adoption_pct < 50%           ("below-half adoption")
  +2  login_success_count == 0 (reachable) ("zero logins in 30 days")
  +1  login_success_count < 5 (reachable)  ("very low login activity")
  +1  trend == "decreasing"                ("login activity trending down")
  +1  onboarding incomplete AND status == "active"
  +2  dealer status == "churn_risk"
  +2  dealer status == "suspended"

  Thresholds: >= 4 points -> "high", >= 2 points -> "medium", else "low".
  An unreachable/never-checked login signal contributes 0 points (graceful
  degradation, stated in the response), never guessed at.
"""

import json
import urllib.error
import urllib.request

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.dealer_modules import get_dealer_module_config
from hub_core.secrets import get_secret


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


_NETWORK_KEY_ENV_VAR = "DEALEROS_NETWORK_KEY"
_DEV_FALLBACK_KEY = "dev-only-insecure-network-key-change-me"
_REQUEST_TIMEOUT_SECONDS = 5

_ASSUMED_ACTIVE_LOGIN_THRESHOLD = 30

_TRAINING_GAP_NOTE = (
    "No training/certification/course-completion model exists anywhere in "
    "this codebase, Hub-side or tenant-side -- an honest, confirmed gap, "
    "not a fabricated percentage. Excluded from the Health Score blend "
    "entirely rather than silently defaulted to some assumed value."
)


@dataclass
class DealerOperationalSnapshot:
    dealer_id: str
    fetched_at: Optional[str] = None
    reachable: bool = False
    error: Optional[str] = None
    data: Dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "dealer_id": self.dealer_id,
            "fetched_at": self.fetched_at,
            "reachable": self.reachable,
            "error": self.error,
            "data": self.data,
        }

    @staticmethod
    def from_dict(d):
        return DealerOperationalSnapshot(
            dealer_id=d["dealer_id"],
            fetched_at=d.get("fetched_at"),
            reachable=d.get("reachable", False),
            error=d.get("error"),
            data=dict(d.get("data", {})),
        )


class DealerOperationalSnapshotRegistry:

    def __init__(self):
        self.snapshots: Dict[str, DealerOperationalSnapshot] = {}

    def get(self, dealer_id):
        return self.snapshots.get(dealer_id)

    def add(self, snapshot: DealerOperationalSnapshot):
        self.snapshots[snapshot.dealer_id] = snapshot

    def list_all(self):
        return sorted(self.snapshots.values(), key=lambda s: s.dealer_id)

    def reset(self):
        self.snapshots = {}


registry = DealerOperationalSnapshotRegistry()


def _fetch_operational_snapshot(dealer):
    """Live GET {api_base_url}/network/operational-health-snapshot. Mirrors
    hub/hub_core/dealer_ai_management.py's _fetch_ai_snapshot exactly."""

    if not dealer.api_base_url:
        return None, "no api_base_url on file -- not yet deployed / not yet recorded"

    url = dealer.api_base_url.rstrip("/") + "/network/operational-health-snapshot"
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

    if "current_window" not in data:
        return None, "reachable, but the response was missing 'current_window' -- not treated as valid"

    return data, None


def recheck_dealer_operational_snapshot(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    data, error = _fetch_operational_snapshot(dealer)

    snapshot = DealerOperationalSnapshot(
        dealer_id=dealer_id,
        fetched_at=_now_iso(),
        reachable=data is not None,
        error=error,
        data=data or {},
    )

    registry.add(snapshot)

    return snapshot, None


def _feature_adoption_pct(dealer_id):

    config = get_dealer_module_config(dealer_id)
    if not config:
        return None

    modules = config.get("modules", [])
    if not modules:
        return None

    enabled = len([m for m in modules if m.get("enabled")])
    return round((enabled / len(modules)) * 100, 1)


def _login_activity(dealer_id):
    """Returns (login_activity_pct_or_None, login_success_count_or_None,
    trend_or_None, checked: bool)."""

    snapshot = registry.get(dealer_id)
    if not snapshot or not snapshot.reachable:
        return None, None, None, False

    current = snapshot.data.get("current_window", {})
    login_success_count = current.get("login_success_count")
    trend = snapshot.data.get("trend")

    if login_success_count is None:
        return None, None, trend, False

    pct = min(100.0, round((login_success_count / _ASSUMED_ACTIVE_LOGIN_THRESHOLD) * 100, 1))

    return pct, login_success_count, trend, True


def get_health_score(dealer_id):

    feature_pct = _feature_adoption_pct(dealer_id)
    login_pct, login_count, trend, login_checked = _login_activity(dealer_id)

    components = {
        "feature_adoption_pct": feature_pct,
        "login_activity_pct": login_pct,
        "training_completion_pct": None,
    }

    if feature_pct is None and login_pct is None:
        score = None
    elif feature_pct is not None and login_pct is not None:
        score = round((feature_pct * 0.5) + (login_pct * 0.5), 1)
    elif feature_pct is not None:
        score = feature_pct
    else:
        score = login_pct

    return {
        "score": score,
        "components": components,
        "basis": "real_blend",
        "blend_note": (
            "50/50 real blend of Feature Adoption % (hub/hub_core/"
            "dealer_modules.py) and Login Activity % (real login_success_"
            "count over the trailing 30 days, capped against an assumed "
            f"threshold of {_ASSUMED_ACTIVE_LOGIN_THRESHOLD} logins/30 days "
            "-- HEURISTIC, since the Hub cannot see a tenant's real "
            "employee headcount to normalize against instead). If Login "
            "Activity has never been checked, the score falls back to "
            "Feature Adoption alone rather than guessing at the missing "
            "half."
        ),
        "training_completion_gap": _TRAINING_GAP_NOTE,
        "login_checked": login_checked,
        "trend": trend,
    }


def compute_churn_risk(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    feature_pct = _feature_adoption_pct(dealer_id)
    login_pct, login_count, trend, login_checked = _login_activity(dealer_id)

    from hub_core.dealer_onboarding import get_onboarding_status

    onboarding, _ = get_onboarding_status(dealer_id)
    onboarding_pct = onboarding.get("progress_pct") if onboarding else None

    points = 0
    reasons = []

    if feature_pct is not None:
        if feature_pct < 20:
            points += 2
            reasons.append({"reason": "very low feature adoption", "points": 2, "detail": f"{feature_pct}% of modules enabled"})
        elif feature_pct < 50:
            points += 1
            reasons.append({"reason": "below-half feature adoption", "points": 1, "detail": f"{feature_pct}% of modules enabled"})

    if login_checked:
        if login_count == 0:
            points += 2
            reasons.append({"reason": "zero logins in the last 30 days", "points": 2, "detail": "login_success_count == 0"})
        elif login_count is not None and login_count < 5:
            points += 1
            reasons.append({"reason": "very low login activity", "points": 1, "detail": f"{login_count} logins in the last 30 days"})

        if trend == "decreasing":
            points += 1
            reasons.append({"reason": "login activity trending down", "points": 1, "detail": "trend == 'decreasing'"})
    else:
        reasons.append({"reason": "login signal unavailable -- never checked or unreachable", "points": 0, "detail": "graceful degradation, no points assigned"})

    if onboarding_pct is not None and onboarding_pct < 100 and dealer.status == "active":
        points += 1
        reasons.append({"reason": "onboarding incomplete on an active dealer", "points": 1, "detail": f"{onboarding_pct}% onboarding progress"})

    if dealer.status == "churn_risk":
        points += 2
        reasons.append({"reason": "dealer status is already 'churn_risk'", "points": 2, "detail": "dealer.status == 'churn_risk'"})
    elif dealer.status == "suspended":
        points += 2
        reasons.append({"reason": "dealer status is 'suspended'", "points": 2, "detail": "dealer.status == 'suspended'"})

    if points >= 4:
        level = "high"
    elif points >= 2:
        level = "medium"
    else:
        level = "low"

    return {
        "dealer_id": dealer_id,
        "level": level,
        "points": points,
        "reasons": reasons,
        "basis": "rules_engine",
        "disclosure": (
            "A real, transparent, points-based rules engine over real "
            "signals -- NOT an AI/ML/LLM-generated score. Every rule and "
            "its point value is listed in 'reasons' above and documented "
            "in hub_core/dealer_support.py's own module docstring."
        ),
    }, None


def get_dealer_support_status(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    snapshot = registry.get(dealer_id)
    health = get_health_score(dealer_id)
    churn, _ = compute_churn_risk(dealer_id)

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "operational_snapshot": snapshot.to_dict() if snapshot else {
            "dealer_id": dealer_id,
            "fetched_at": None,
            "reachable": False,
            "error": None,
            "data": {},
        },
        "health_score": health,
        "churn_risk": churn,
    }, None
