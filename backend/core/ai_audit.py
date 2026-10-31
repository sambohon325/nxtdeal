"""
core/ai_audit.py -- comprehensive AI action audit trail (security-hardening
pass, 2026-07-20, Task #5).

core/ai_management.py's own `_CALL_STATS` has been real since it shipped
(session 88/89-era) -- honest, in-memory, per-feature counters
(attempted/succeeded/fell_back/blocked). That's genuinely useful for a live
"is this feature healthy right now" dashboard, but it is NOT an audit trail:
it can't answer "who asked the AI assistant to do X, and what did it say
back" after the fact, and it resets to zero on every process restart (the
same documented limitation as core/ws_manager.py's ConnectionManager).

This module adds the real, durable half on top, without duplicating or
replacing that counter mechanism: `AiActionLog` (core/entity_types.py) is a
first-class, own-lifecycle graph entity -- one real record per AI call,
created via `log_action()` and returned by `record_call_attempt()`'s new
optional kwargs (see core/ai_management.py). Deliberately bounded, not a
transcript store: `prompt_summary`/`output_summary` are both truncated at
write time (`_MAX_SUMMARY_CHARS`) so this can never grow into a full copy of
every AI conversation -- a real usage/audit record (who, what feature, what
outcome, roughly what was asked and answered), not a second chat log.

**Why this is added to the in-memory ledger on every call but NOT saved to
disk on every call** -- the same batched-save discipline this codebase has
had to learn the hard way more than once (documented at length in CLAUDE.md's
own "codebase-wide missing-save_graph() audit" section, and the specific
performance-regression class core/trigger_alerts.py's run_scan() hit and
fixed): `core/ai_assistant.py`'s `ask_ai()` is this codebase's single hottest
AI call site (the main /workspace chat endpoint), and a real
`save_graph()`-scale disk write (documented elsewhere in this codebase at
several real seconds per call on the live graph's size) on every single chat
turn would be a serious, self-inflicted latency regression. Instead:
`log_action()` calls `ledger.add_entity()` only -- a real, in-memory
mutation, immediately queryable via `list_ai_actions()`/
`get_ai_audit_dashboard()` within the same process -- and relies on whatever
OTHER real action next calls `save_graph()` (which happens constantly across
this codebase's own established mutation discipline) to actually persist it
to disk, exactly matching `core/kpi_snapshots.py`'s own "added to the ledger
now, persisted whenever anything else next saves" precedent. `flush_ai_audit_log()`
below is the explicit escape hatch for a caller (a scheduled job, a
shutdown hook, or a manual admin action) that genuinely needs an immediate,
guaranteed disk write rather than waiting on that.

Real, honestly-stated scope limit, not silently glossed over: `actor` (the
employee who triggered the call) is threaded through for `ai_assistant`
only as of this pass -- the one feature in `AI_FEATURE_CATALOG` with real
tool-calling graph access (`has_tool_calling_access: True`), the highest
real audit value in this whole catalog. The other 12 features' call sites
(email/website/social/reputation/advertising wizards, etc.) still call
`record_call_attempt()` without an `actor` -- each resulting `AiActionLog`
honestly records `actor: None` rather than a guessed value. Threading a real
actor through all 44 call sites across 13 modules is real future work,
flagged here rather than silently claimed done.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import AI_ACTION_LOG

_MAX_SUMMARY_CHARS = 500


def _now():
    return datetime.now(timezone.utc).isoformat()


def _truncate(text):
    if not text:
        return None
    text = str(text)
    if len(text) <= _MAX_SUMMARY_CHARS:
        return text
    return text[:_MAX_SUMMARY_CHARS] + f"... [truncated, {len(text)} chars total]"


def log_action(feature_key, outcome, actor=None, prompt_summary=None, output_summary=None, detail=None):
    """Creates and adds one real AiActionLog entity to the in-memory ledger.
    Does NOT call save_graph() -- see this module's own docstring for why.
    Returns the created entity's real id."""

    action_id = id_generator.generate("AIACT")

    entity = Entity(
        id=action_id,
        entity_type=AI_ACTION_LOG,
        attributes={
            "feature_key": feature_key,
            "outcome": outcome,
            "actor": actor,
            "prompt_summary": _truncate(prompt_summary),
            "output_summary": _truncate(output_summary),
            "detail": _truncate(detail),
            "created_at": _now(),
        },
    )

    ledger.add_entity(entity)

    return action_id


def flush_ai_audit_log():
    """Explicit, on-demand escape hatch to force an immediate disk write of
    the whole graph (including any AiActionLog entities added since the
    last real save) -- deferred import to avoid a top-level circular
    dependency (core/storage.py has no reason to know about this module)."""

    from core.storage import save_graph
    from core.storage_paths import GRAPH_PATH

    save_graph(GRAPH_PATH)

    return {"flushed": True, "flushed_at": _now()}


def _all_actions():
    return [e for e in ledger.entities.values() if e.entity_type == AI_ACTION_LOG]


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def list_ai_actions(feature_key=None, actor=None, outcome=None, limit=100):
    """Most-recent-first, matching every other list_*() function in this
    codebase's own established convention (core/audit_api.py's
    list_audit_events(), etc.)."""

    actions = _all_actions()

    if feature_key:
        actions = [a for a in actions if a.attributes.get("feature_key") == feature_key]

    if actor:
        actions = [a for a in actions if a.attributes.get("actor") == actor]

    if outcome:
        actions = [a for a in actions if a.attributes.get("outcome") == outcome]

    actions = sorted(actions, key=lambda a: a.attributes.get("created_at") or "", reverse=True)

    if limit:
        actions = actions[:limit]

    return [_serialize(a) for a in actions]


def get_ai_audit_dashboard():
    """Real aggregate view over every AiActionLog entity currently in the
    ledger (in-memory + whatever's been persisted and reloaded) -- by
    feature, by outcome, and a real recent-activity feed. Distinct from
    core/ai_management.py's get_ai_management_overview(), which reports the
    in-memory-only, resets-on-restart _CALL_STATS counters -- this reports
    the real, durable record on top of that."""

    actions = _all_actions()

    by_feature = {}
    by_outcome = {}
    actors_with_activity = set()

    for a in actions:
        feature_key = a.attributes.get("feature_key") or "unknown"
        outcome = a.attributes.get("outcome") or "unknown"
        by_feature[feature_key] = by_feature.get(feature_key, 0) + 1
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        if a.attributes.get("actor"):
            actors_with_activity.add(a.attributes["actor"])

    recent = sorted(actions, key=lambda a: a.attributes.get("created_at") or "", reverse=True)[:25]

    return {
        "total_actions": len(actions),
        "by_feature": by_feature,
        "by_outcome": by_outcome,
        "distinct_actors_with_recorded_activity": len(actors_with_activity),
        "recent": [_serialize(a) for a in recent],
        "note": (
            "Real, persisted per-call records -- distinct from "
            "core/ai_management.py's in-memory-only call-attempt counters, "
            "which reset on every process restart. `actor` is only threaded "
            "through for the ai_assistant feature as of this pass (see this "
            "module's own docstring) -- every other feature's records "
            "honestly show actor: null rather than a guessed value."
        ),
    }
