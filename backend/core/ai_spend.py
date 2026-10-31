"""
core/ai_spend.py -- the AI Spend Governor (Freemium Platform roadmap, Phase 5, 2026-08-03).

The model, from the roadmap's Resolved Direction
------------------------------------------------
NXTDeal stays model-AGNOSTIC rather than a model provider. Each dealer admin supplies their own
API key (ChatGPT, Gemini, a home-hosted/local model, whatever), so the cost of AI consumption sits
with the dealer, not NXTDeal -- a bring-your-own-key posture. Two controls fall out of that:

  1. A per-USER consumption limit the dealer admin can set, so one user cannot burn through the
     whole key's budget.
  2. An aggregate usage view for the admin, building on the AI Management call tracking already
     live across the AI areas, so the dealer can see total consumption against whatever budget they
     arranged with their own provider.

This is a spend governor sitting ON TOP OF a BYO-key model, not a Module gate -- it belongs in
Phase 5 alongside the other in-product gating UI.

Honest scope + where usage comes from
-------------------------------------
There is no token/dollar metering anywhere in NXTDeal today (confirmed: every AI module reads one
global `OPENAI_API_KEY` and only call COUNTS are tracked, in `core/ai_management.py` +
`core/ai_audit.py`). So this governor meters **AI actions per user per month**, not tokens or
dollars. That is a real, useful budget proxy for a per-user "don't let one rep run away with the
key" control, and the design keeps a single `_period_key()` + count shape that can be swapped from
action-count to token-count later without changing the public API.

Usage is DERIVED, not separately stored. Every real AI call already writes a durable AiActionLog
entity (core/ai_audit.py, via ai_management.record_call_attempt) carrying actor + feature_key +
outcome + created_at. The governor reads those entities to compute per-user monthly consumption --
so there is zero extra write on the AI hot path (no per-call save_graph, no duplicated counter), and
the numbers can never drift from the audit log. Only genuine provider attempts count: outcome in
{succeeded, fell_back}; a 'blocked' call never reached the provider, so it costs nothing. A call
whose feature didn't thread an actor lands in an honest 'unattributed' aggregate rather than being
dropped.

The singleton this module persists (AiSpendPolicy) therefore holds CONFIG ONLY -- the BYO-key
provider posture and the per-user limits -- written only when an admin changes a setting, never on
the hot path. Same fixed-id-singleton convention as core/system_config.py's SystemConfig.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import AI_SPEND_POLICY, AI_ACTION_LOG
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


_POLICY_ID = "AISPEND-00001"

# Only genuine provider attempts are metered -- a blocked call never reached the model.
_METERED_OUTCOMES = ("succeeded", "fell_back")

# AI providers a dealer can run on. NXTDeal is model-agnostic, so most of these are just a label
# on the dealer's own key. Two are special:
#   * "dealeros" -- our own HOSTED, usage-billed inference (zero setup, no key to manage). It is a
#     PAID add-on (entitlements 'dealeros_ai') and is never available on the free model.
#   * "custom"   -- a homegrown / any-API endpoint the dealer points us at (see custom_endpoint).
PROVIDERS = ("dealeros", "openai", "gemini", "anthropic", "azure_openai", "local", "custom", "other")

# Selecting this provider requires the NXTDeal AI add-on (entitlements.is_managed_ai_available()).
MANAGED_PROVIDER = "dealeros"

# Default usage-based price for the managed provider, in dollars per metered AI action. A starting
# point the admin can change -- there is no token metering yet, so billing is per-action (see the
# module docstring on metering_basis).
DEFAULT_MANAGED_RATE = 0.03

_UNATTRIBUTED = "__unattributed__"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _period_key(when=None):
    """The bucket usage is metered into. Month granularity (YYYY-MM). One place to change if this
    ever moves to a different window."""
    dt = when or datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


def _default_attributes():
    # CONFIG ONLY -- usage is derived from the audit log, never stored here.
    return {
        # BYO-key posture. `byo_key_configured` is an admin-declared fact (has the dealer actually
        # put their own key in place at the deployment) -- we never read the secret itself here.
        "provider": "openai",
        "byo_key_configured": False,
        # Per-user monthly AI-action limit. None == unlimited (the default, so nothing is throttled
        # until an admin sets a budget). Overrides are per-user ints (or None to explicitly unlimit
        # one user).
        "per_user_monthly_limit": None,
        "user_overrides": {},  # user_id -> int | None
        # Dealer-level master AI switch. Some dealerships simply don't want AI in the product at all;
        # when this is False, all AI is off dealer-wide (server-side, via ai_kill_switch) and the AI
        # UI is hidden. Defaults True so existing behavior is unchanged.
        "ai_enabled": True,
        # Per-user opt-out. Employee ids here have turned AI off for themselves ("don't want it in my
        # face") -- their AI UI hides and their AI actions are refused, without affecting anyone else.
        "ai_off_users": [],
        # Homegrown / any-API endpoint config for the "custom" provider (no secret stored here -- the
        # key lives in the deployment/secret store; this records where + how to call it).
        "custom_endpoint": None,  # {"base_url", "model", "auth_header", "notes"} | None
        # Usage-based price per metered AI action for the managed "dealeros" provider.
        "managed_rate_per_action": DEFAULT_MANAGED_RATE,
        "updated_by": None,
        "updated_at": _now(),
    }


def _get_or_create():
    entity = ledger.get_entity(_POLICY_ID)
    if entity and entity.entity_type == AI_SPEND_POLICY:
        changed = False
        for key, value in _default_attributes().items():
            if key not in entity.attributes:
                entity.attributes[key] = value
                changed = True
        if changed:
            save_graph(GRAPH_PATH)
        return entity
    entity = Entity(id=_POLICY_ID, entity_type=AI_SPEND_POLICY, attributes=_default_attributes())
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return entity


# ---------------------------------------------------------------------------
# Policy config (admin).
# ---------------------------------------------------------------------------

def get_policy():
    e = _get_or_create()
    a = e.attributes
    return {
        "id": e.id,
        "provider": a.get("provider", "openai"),
        "byo_key_configured": bool(a.get("byo_key_configured")),
        "per_user_monthly_limit": a.get("per_user_monthly_limit"),
        "user_overrides": dict(a.get("user_overrides", {})),
        "ai_enabled": bool(a.get("ai_enabled", True)),
        "ai_off_users": list(a.get("ai_off_users", [])),
        "custom_endpoint": a.get("custom_endpoint"),
        "managed_rate_per_action": a.get("managed_rate_per_action", DEFAULT_MANAGED_RATE),
        "managed_ai_available": _managed_ai_available(),
        "updated_by": a.get("updated_by"),
        "updated_at": a.get("updated_at"),
    }


def _managed_ai_available():
    """Whether the dealer holds the NXTDeal AI add-on (the gate for the managed provider)."""
    try:
        from core import entitlements
        return entitlements.is_managed_ai_available()
    except Exception:
        return False


def set_provider(provider, updated_by, byo_key_configured=None):
    if provider not in PROVIDERS:
        return {"error": f"Unknown provider '{provider}'. Valid: {list(PROVIDERS)}"}
    # Our own hosted AI is a paid add-on -- not available on the free model. Selecting it requires
    # the NXTDeal AI entitlement; BYO-key / custom providers need no add-on.
    if provider == MANAGED_PROVIDER and not _managed_ai_available():
        return {
            "error": "NXTDeal AI is a paid add-on. Add it to your plan, or bring your own key / endpoint.",
            "reason": "add_on_required",
            "add_on": "dealeros_ai",
        }
    e = _get_or_create()
    e.attributes["provider"] = provider
    if byo_key_configured is not None:
        e.attributes["byo_key_configured"] = bool(byo_key_configured)
    e.attributes["updated_by"] = updated_by
    e.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return get_policy()


def set_custom_endpoint(config, updated_by):
    """Point the 'custom' provider at a homegrown / any-API endpoint. config is a dict (base_url,
    model, auth_header, notes) or None to clear. No secret is stored here."""
    if config is not None and not isinstance(config, dict):
        return {"error": "custom_endpoint must be an object or null."}
    e = _get_or_create()
    if config is None:
        e.attributes["custom_endpoint"] = None
    else:
        e.attributes["custom_endpoint"] = {
            "base_url": (config.get("base_url") or "").strip(),
            "model": (config.get("model") or "").strip(),
            "auth_header": (config.get("auth_header") or "Authorization").strip(),
            "notes": (config.get("notes") or "").strip(),
        }
    e.attributes["updated_by"] = updated_by
    e.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return get_policy()


def set_managed_rate(rate, updated_by):
    """Set the usage-based price per metered AI action for the managed provider."""
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        return {"error": "Rate must be a number."}
    if rate < 0:
        return {"error": "Rate cannot be negative."}
    e = _get_or_create()
    e.attributes["managed_rate_per_action"] = rate
    e.attributes["updated_by"] = updated_by
    e.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return get_policy()


# ---------------------------------------------------------------------------
# The AI on/off switches -- dealer master + per-user opt-out (some people just don't want AI).
# ---------------------------------------------------------------------------

def set_ai_enabled(enabled, updated_by):
    """Dealer-level master AI switch. When off, all AI is off dealer-wide (server-side via
    ai_kill_switch.is_ai_globally_enabled, which reads this) and the AI UI hides."""
    e = _get_or_create()
    e.attributes["ai_enabled"] = bool(enabled)
    e.attributes["updated_by"] = updated_by
    e.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return get_policy()


def dealer_ai_enabled():
    """The dealer-level master switch (does NOT consider a specific user's opt-out)."""
    return bool(_get_or_create().attributes.get("ai_enabled", True))


def set_user_ai_enabled(user_id, enabled, updated_by):
    """Per-user AI opt-out. enabled=False adds the user to the off list; True removes them."""
    if not user_id:
        return {"error": "A user_id is required."}
    e = _get_or_create()
    off = e.attributes.setdefault("ai_off_users", [])
    if enabled:
        if user_id in off:
            off.remove(user_id)
    else:
        if user_id not in off:
            off.append(user_id)
    e.attributes["updated_by"] = updated_by
    e.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return get_policy()


def is_user_ai_off(user_id):
    return bool(user_id) and user_id in _get_or_create().attributes.get("ai_off_users", [])


# IMPORTANT scope note (Sam, 2026-08-03): the PER-USER opt-out is purely EXPERIENTIAL. It governs
# only USER-FACING AI -- whether the AI chrome renders for that user, and whether AI actions THEY
# trigger run. It must NEVER gate background agent learning/recording: when a user turns AI off, the
# bot fleet keeps observing and recording their workflows (core/bot_fleet.record_workflow_step, which
# is deliberately ungated) so the agent keeps learning; the user simply won't notice AI. Recording
# paths must therefore call neither is_ai_enabled_for(user) nor enforce_user_allowance(user). If you
# ever want a dealership-wide "stop learning too", that's the dealer master switch's job, not the
# per-user opt-out -- see background_ai_enabled() below.

def is_ai_enabled_for(user_id=None):
    """USER-FACING AI resolution: the dealer master switch AND (if a user is given) that this user
    hasn't opted out. This gates what the user SEES and the AI actions they trigger -- NOT background
    learning/recording (see the scope note above). One user opting out never affects another user or
    the agent's observation of that user's workflows."""
    if not dealer_ai_enabled():
        return False
    if user_id is not None and is_user_ai_off(user_id):
        return False
    return True


def background_ai_enabled():
    """Whether passive/background AI (agent learning, workflow observation, aggregate analytics) may
    run. This is the DEALER master switch ONLY -- it deliberately ignores any per-user opt-out, since
    a user hiding AI from themselves must not blind the agent to their workflows. (Today the recording
    path in core/bot_fleet.py is ungated even by this; this helper exists so any future gating of
    background AI has one correct, per-user-agnostic thing to check.)"""
    return dealer_ai_enabled()


def get_my_ai_status(user_id):
    """What one user needs to decide whether to render AI at all: the resolved flag plus the two
    inputs, so the UI can explain 'off by your admin' vs 'off by you'."""
    return {
        "ai_enabled": is_ai_enabled_for(user_id),
        "dealer_ai_enabled": dealer_ai_enabled(),
        "user_ai_off": is_user_ai_off(user_id),
    }


def _validate_limit(value):
    if value is None:
        return None, None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None, "Limit must be an integer or null (unlimited)."
    if value < 0:
        return None, "Limit cannot be negative."
    return value, None


def set_default_limit(limit, updated_by):
    value, err = _validate_limit(limit)
    if err:
        return {"error": err}
    e = _get_or_create()
    e.attributes["per_user_monthly_limit"] = value
    e.attributes["updated_by"] = updated_by
    e.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return get_policy()


def set_user_limit(user_id, limit, updated_by):
    """Override one user's monthly limit. limit=None makes that user explicitly unlimited; pass the
    sentinel via clear_user_limit() to fall back to the default instead."""
    if not user_id:
        return {"error": "A user_id is required."}
    value, err = _validate_limit(limit)
    if err:
        return {"error": err}
    e = _get_or_create()
    e.attributes.setdefault("user_overrides", {})[user_id] = value
    e.attributes["updated_by"] = updated_by
    e.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return get_policy()


def clear_user_limit(user_id, updated_by):
    """Remove a user's override so they fall back to the default limit again."""
    e = _get_or_create()
    e.attributes.setdefault("user_overrides", {}).pop(user_id, None)
    e.attributes["updated_by"] = updated_by
    e.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return get_policy()


def user_limit(user_id):
    """The resolved monthly limit for a user: their override if set, else the default. None ==
    unlimited."""
    a = _get_or_create().attributes
    overrides = a.get("user_overrides", {})
    if user_id in overrides:
        return overrides[user_id]
    return a.get("per_user_monthly_limit")


# ---------------------------------------------------------------------------
# Usage -- DERIVED from the AiActionLog entities the AI hot path already writes.
# ---------------------------------------------------------------------------

def _usage_index(period=None):
    """{user_id -> {"count": int, "by_feature": {feature_key: int}}} for one month, computed from
    the durable AiActionLog entities (actor + feature_key + outcome + created_at). Only metered
    outcomes count; a call with no actor is bucketed under the 'unattributed' sentinel."""
    period = period or _period_key()
    index = {}
    for e in ledger.get_all().values():
        if e.entity_type != AI_ACTION_LOG:
            continue
        a = e.attributes
        if a.get("outcome") not in _METERED_OUTCOMES:
            continue
        created = a.get("created_at") or ""
        if not created.startswith(period):
            continue
        uid = a.get("actor") or _UNATTRIBUTED
        rec = index.setdefault(uid, {"count": 0, "by_feature": {}})
        rec["count"] += 1
        fk = a.get("feature_key")
        if fk:
            rec["by_feature"][fk] = rec["by_feature"].get(fk, 0) + 1
    return index


def usage_for(user_id, period=None):
    rec = _usage_index(period).get(user_id, {"count": 0, "by_feature": {}})
    return {"count": rec.get("count", 0), "by_feature": dict(rec.get("by_feature", {}))}


def check_user_allowance(user_id, period=None):
    """Where a user stands against their monthly limit. Unlimited limit == always allowed."""
    limit = user_limit(user_id)
    used = usage_for(user_id, period)["count"]
    if limit is None:
        return {"allowed": True, "limit": None, "used": used, "remaining": None}
    remaining = max(0, limit - used)
    return {
        "allowed": used < limit,
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "reason": None if used < limit else "user_limit_reached",
    }


def enforce_user_allowance(user_id):
    """Gate a USER-FACING AI action for a user (something they triggered and would see the result of).
    Returns None when allowed, else a real error dict the caller can fall back on (AI features degrade
    to their non-AI fallback rather than erroring). Refused when: AI is off (dealer master or this
    user's own opt-out), or the user hit their monthly limit. A missing user_id skips the per-user
    checks but the dealer master still applies.

    Do NOT call this on a background learning/recording path -- a user's opt-out must not stop the
    agent from observing their workflows (see is_ai_enabled_for's scope note). This is only for AI the
    user actively invokes."""
    if not dealer_ai_enabled():
        return {"error": "AI is turned off for your dealership.", "reason": "ai_off_dealer"}
    if not user_id:
        return None
    if is_user_ai_off(user_id):
        return {"error": "You've turned AI off. Re-enable it in your settings to use this.", "reason": "ai_off_user"}
    status = check_user_allowance(user_id)
    if status["allowed"]:
        return None
    return {
        "error": "You've reached your monthly AI usage limit. Ask an admin to raise it.",
        "reason": "user_limit_reached",
        "limit": status["limit"],
        "used": status["used"],
    }


# ---------------------------------------------------------------------------
# Aggregate view (admin) -- builds on ai_management's own call stats.
# ---------------------------------------------------------------------------

def get_spend_overview(period=None):
    """The dealer admin's aggregate AI-consumption view for a month: per-user used-vs-limit, the
    unattributed remainder, provider/BYO posture, and the total tying back to AI Management stats."""
    period = period or _period_key()
    a = _get_or_create().attributes
    bucket = _usage_index(period)

    users = []
    attributed_total = 0
    for uid, rec in bucket.items():
        if uid == _UNATTRIBUTED:
            continue
        count = rec.get("count", 0)
        attributed_total += count
        limit = user_limit(uid)
        users.append({
            "user_id": uid,
            "used": count,
            "limit": limit,
            "remaining": None if limit is None else max(0, limit - count),
            "over_limit": bool(limit is not None and count >= limit),
            "by_feature": dict(rec.get("by_feature", {})),
        })
    users.sort(key=lambda u: u["used"], reverse=True)

    unattributed = bucket.get(_UNATTRIBUTED, {}).get("count", 0)
    total_actions = attributed_total + unattributed

    provider = a.get("provider", "openai")
    rate = a.get("managed_rate_per_action", DEFAULT_MANAGED_RATE)
    # Usage-based billing applies ONLY when the dealer is on our hosted provider. On BYO-key/custom
    # the cost sits with the dealer's own account, so there's nothing for us to bill here.
    billing = None
    if provider == MANAGED_PROVIDER:
        billing = {
            "provider": MANAGED_PROVIDER,
            "billable_actions": total_actions,
            "rate_per_action": rate,
            "estimated_charge": round(total_actions * rate, 2),
            "note": "Estimate. Billed per AI action (no token metering yet).",
        }

    return {
        "period": period,
        "provider": provider,
        "byo_key_configured": bool(a.get("byo_key_configured")),
        "per_user_monthly_limit": a.get("per_user_monthly_limit"),
        "ai_enabled": bool(a.get("ai_enabled", True)),
        "ai_off_user_count": len(a.get("ai_off_users", [])),
        "total_ai_actions": total_actions,
        "attributed_actions": attributed_total,
        "unattributed_actions": unattributed,
        "distinct_users": len(users),
        "users": users,
        "metering_basis": "ai_actions",  # not tokens/$ -- see module docstring
        "managed_billing": billing,
    }


def build_ai_spend_network_snapshot():
    """Dealer-identified snapshot for the Hub (metering an AI Workforce Module later). Reuses the
    same overview; kept as its own function so the Hub read is an explicit, named contract."""
    overview = get_spend_overview()
    return {
        "provider": overview["provider"],
        "byo_key_configured": overview["byo_key_configured"],
        "per_user_monthly_limit": overview["per_user_monthly_limit"],
        "period": overview["period"],
        "total_ai_actions": overview["total_ai_actions"],
        "distinct_users": overview["distinct_users"],
        "users_over_limit": [u["user_id"] for u in overview["users"] if u["over_limit"]],
        "metering_basis": overview["metering_basis"],
    }
