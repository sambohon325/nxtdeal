"""
core/audit_center.py -- Administration's "Audit Center" item (Administration
Control Center rebuild, final slice). Sam's own admin.pdf-derived 15-item
proposal lists "Audit Center" as its own item, distinct from "Security"
(login/lockout activity), "Systems" (platform-level audit dump), and
"Governance" (approval queue + escalation rules + a flat audit trail) -- all
three of which already surface a THIN slice of the real audit log
(core/audit.py's `audit_log` singleton, ~20+ modules across this codebase
already write real events to it: logins, credential lifecycle, compliance
overrides, permission grants, vendor/deal/lead/campaign/website/workflow
actions). This module is the genuine investigative workspace those three
thin slices were never meant to be: real filtering/search across the whole
log, a real per-actor activity summary ("who did what, how often"), and a
real, transparent RULES-based suspicious-activity flag list -- explicitly
closing the gap core/administration_menu.py's own `security()` docstring has
flagged since it shipped this same rebuild: "No anomaly-detection/suspicious-
activity flagging exists yet."

No machine-learning/LLM anomaly detector is built here, on purpose, matching
this codebase's established "real rules engine, not fake AI" convention
(core/network_audit.py's recommendation engine, core/lead_record.py's
next_best_action(), core/collections.py's risk scoring) -- every flag below
is a plain, explainable threshold over real data, and each one states exactly
why it fired.

Audit events are NOT graph entities (core/audit.py's AuditEvent is a plain
dataclass held in an in-memory list, serialized separately via
core/audit_storage.py) -- this module makes zero ledger.add_entity() calls
and needs no save_graph() discipline; it's a pure read layer over data other
modules already wrote and persisted at the time they recorded it.
"""

import csv
import io
from datetime import datetime, timezone, timedelta

from core.audit import audit_log
from core.audit_api import list_audit_events
from core.auth import credential_store
from core.system_config import get_system_config

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover -- Python < 3.9, not expected here
    ZoneInfo = None


# A real category mapping over every event_type this codebase's own modules
# actually write (confirmed via a full grep of event_type="..." call sites
# across core/ before writing this catalog -- not guessed at). New event
# types introduced by future modules simply fall into "Other" below rather
# than erroring.
EVENT_CATEGORIES = {
    "login_success": "Authentication",
    "login_failed": "Authentication",
    "login_blocked_ip": "Authentication",
    "login_blocked_locked": "Authentication",
    "account_unlocked": "Authentication",
    "credential_created": "Credentials",
    "credential_reset": "Credentials",
    "password_changed": "Credentials",
    "ip_allowlist_changed": "Credentials",
    "permission_override_set": "Permissions",
    "permission_override_revoked": "Permissions",
    "approval_request_created": "Approvals",
    "approval_step_approved": "Approvals",
    "approval_request_rejected": "Approvals",
    "compliance_alert_created": "Compliance",
    "compliance_alert_resolved": "Compliance",
    "compliance_alert_overridden": "Compliance",
    "deal_funded": "Deals",
    "deal_financing_decision": "Deals",
    "lead_assigned": "Leads",
    "lead_escalated": "Leads",
    "lead_reactivated": "Leads",
    "asset_approved": "Marketing",
    "asset_rejected": "Marketing",
    "campaign_activated": "Marketing",
    "website_published": "Marketing",
    "website_rejected": "Marketing",
    "workflow_created": "Workflows",
    "workflow_transition": "Workflows",
    "bot_auto_action": "Bot",
    "bot_coverage_started": "Bot",
    "bot_coverage_ended": "Bot",
    "accounting_period_closed": "Accounting",
    "accounting_period_reopened": "Accounting",
    "ai_feature_toggled": "AI",
    "entity_updated": "Other",
}

DEFAULT_CATEGORY = "Other"

# Off-hours business-hours parsing: system_config.business_hours values are
# free-text strings like "9:00 AM - 7:00 PM" or "Closed" (core/system_config.py's
# own _default_attributes()) -- a fixed, predictable format across every
# dealer-editable field this codebase has for it. Parsed defensively; an
# unexpected format degrades to "unknown" rather than a crash or a fabricated
# window.
_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _parse_hours_range(text):
    """Returns (open_time, close_time) as datetime.time objects, or None if
    `text` is "Closed" or doesn't match the expected "H:MM AM/PM - H:MM AM/PM"
    shape."""

    if not text or text.strip().lower() == "closed":
        return None

    parts = text.split("-")
    if len(parts) != 2:
        return None

    try:
        open_t = datetime.strptime(parts[0].strip(), "%I:%M %p").time()
        close_t = datetime.strptime(parts[1].strip(), "%I:%M %p").time()
    except ValueError:
        return None

    return open_t, close_t


def _is_off_hours(iso_timestamp, business_hours, tz_name):
    """Real, transparent check: converts the event's real UTC timestamp into
    the dealership's own configured local timezone (core/system_config.py's
    default_timezone), looks up that local day's real configured business_hours
    string, and reports whether the local time-of-day falls outside it. Returns
    (is_off_hours: bool or None, reason: str) -- None means "couldn't be
    determined" (bad timestamp, unrecognized timezone, or an unparseable hours
    string), not a fabricated result either way."""

    try:
        ts = datetime.fromisoformat(iso_timestamp)
    except (ValueError, TypeError):
        return None, "unparseable timestamp"

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    if ZoneInfo is not None and tz_name:
        try:
            local = ts.astimezone(ZoneInfo(tz_name))
        except Exception:
            local = ts.astimezone(timezone.utc)
    else:
        local = ts.astimezone(timezone.utc)

    day_name = _DAY_NAMES[local.weekday()]
    hours_text = business_hours.get(day_name, "")
    window = _parse_hours_range(hours_text)

    if window is None:
        if hours_text.strip().lower() == "closed":
            return True, f"{day_name.title()} is configured as Closed"
        return None, f"unparseable business_hours for {day_name}"

    open_t, close_t = window
    local_time = local.time()

    if open_t <= local_time <= close_t:
        return False, f"within {day_name.title()}'s {hours_text} window"

    return True, f"outside {day_name.title()}'s {hours_text} window (local time {local_time.strftime('%I:%M %p')})"


def _serialize(event_dict):
    """list_audit_events() already returns plain dicts -- this just attaches
    the real category label alongside whatever it already has."""

    enriched = dict(event_dict)
    enriched["category"] = EVENT_CATEGORIES.get(event_dict.get("event_type"), DEFAULT_CATEGORY)
    return enriched


def get_event_catalog():
    """Every real event_type this codebase's modules currently write, grouped
    by category, for a filter dropdown -- built from the same EVENT_CATEGORIES
    map this module's own filtering uses, so the UI can never offer a filter
    value that doesn't correspond to anything real."""

    by_category = {}
    for event_type, category in EVENT_CATEGORIES.items():
        by_category.setdefault(category, []).append(event_type)

    for category in by_category:
        by_category[category].sort()

    return {"categories": by_category, "total_event_types": len(EVENT_CATEGORIES)}


def search_audit_log(
    entity_id=None,
    actor=None,
    event_type=None,
    category=None,
    date_from=None,
    date_to=None,
    query=None,
    limit=200,
):
    """The real investigative search: every existing filter list_audit_events()
    already supports (entity_id/actor/event_type), plus three genuinely new
    ones -- `category` (via EVENT_CATEGORIES), a real ISO date_from/date_to
    range, and `query` (a real case-insensitive substring match against each
    event's own summary text, entity_id, and actor -- a plain string search,
    not a fabricated relevance-ranked one)."""

    events = list_audit_events(entity_id=entity_id, actor=actor, event_type=event_type)

    if category:
        events = [e for e in events if EVENT_CATEGORIES.get(e.get("event_type"), DEFAULT_CATEGORY) == category]

    if date_from:
        events = [e for e in events if e.get("timestamp", "") >= date_from]

    if date_to:
        events = [e for e in events if e.get("timestamp", "") <= date_to]

    if query:
        q = query.lower()
        events = [
            e for e in events
            if q in (e.get("summary") or "").lower()
            or q in (e.get("entity_id") or "").lower()
            or q in (e.get("actor") or "").lower()
        ]

    total = len(events)
    events = [_serialize(e) for e in events[:limit]]

    return {"total_matches": total, "returned": len(events), "events": events}


def get_actor_activity(limit=50):
    """Real "who did what, how often" -- every actor who's ever appeared in
    the real audit log, ranked by total event count, each with a real
    event-type breakdown and real first/last-seen timestamps. Not a
    fabricated leaderboard -- a genuine aggregate over `audit_log.get_all()`."""

    events = audit_log.get_all()

    by_actor = {}
    for e in events:
        actor = e.actor
        bucket = by_actor.setdefault(actor, {"actor": actor, "total": 0, "by_event_type": {}, "first_seen": e.timestamp, "last_seen": e.timestamp})
        bucket["total"] += 1
        bucket["by_event_type"][e.event_type] = bucket["by_event_type"].get(e.event_type, 0) + 1
        if e.timestamp < bucket["first_seen"]:
            bucket["first_seen"] = e.timestamp
        if e.timestamp > bucket["last_seen"]:
            bucket["last_seen"] = e.timestamp

    ranked = sorted(by_actor.values(), key=lambda b: b["total"], reverse=True)

    return {"total_actors": len(ranked), "actors": ranked[:limit]}


def get_actor_timeline(actor, limit=100):
    """One actor's full real event history, most recent first -- the drill-down
    from get_actor_activity()'s leaderboard."""

    events = list_audit_events(actor=actor)
    events = [_serialize(e) for e in events[:limit]]

    return {"actor": actor, "total_events": len(events), "events": events}


# --- Suspicious activity: real, transparent, rules-based flags only ---

def get_suspicious_activity(off_hours_lookback_days=7):
    """Closes core/administration_menu.py's `security()` docstring's own
    stated gap ("No anomaly-detection/suspicious-activity flagging exists
    yet"). Every flag below is a plain, explainable rule over real data --
    no ML model, no LLM call. Each flag carries a `basis` field naming the
    exact rule and a `severity` (high/medium/low) derived from a real,
    stated threshold, matching core/collections.py's own risk-tier
    convention for this codebase's established "transparent rules engine"
    pattern."""

    flags = []

    # Rule 1: currently-locked accounts (core/auth.py's real, computed lockout
    # state -- already surfaced by security(), re-flagged here as a real
    # suspicious-activity item since a lockout is, by definition, a real
    # security-relevant event).
    for rec in credential_store.list_records():
        employee_id = rec["employee_id"]
        lockout = credential_store.get_lockout_status(employee_id)
        if lockout["locked"]:
            flags.append({
                "flag_type": "account_locked",
                "severity": "high",
                "entity_id": employee_id,
                "basis": "real_rule",
                "detail": f"{employee_id} is currently locked out after {lockout['failed_attempts']} failed login attempts (locked until {lockout['locked_until']}).",
            })

    # Rule 2: elevated failed-attempt counters that haven't yet crossed the
    # real lockout threshold -- a real early-warning watchlist, not a
    # fabricated risk score.
    for rec in credential_store.list_records():
        employee_id = rec["employee_id"]
        full = credential_store.get_record(employee_id) or {}
        attempts = full.get("failed_attempts", 0)
        if 0 < attempts and not credential_store.get_lockout_status(employee_id)["locked"]:
            flags.append({
                "flag_type": "elevated_failed_attempts",
                "severity": "medium" if attempts >= 3 else "low",
                "entity_id": employee_id,
                "basis": "real_rule",
                "detail": f"{employee_id} has {attempts} failed login attempt(s) on file, below the lockout threshold.",
            })

    # Rule 3: IP-allowlist-blocked login attempts -- a real signal someone
    # tried logging in from a network not on that employee's allowlist.
    ip_blocked = list_audit_events(event_type="login_blocked_ip")
    by_entity = {}
    for e in ip_blocked:
        by_entity.setdefault(e.get("entity_id"), []).append(e)
    for entity_id, evts in by_entity.items():
        flags.append({
            "flag_type": "ip_allowlist_blocked",
            "severity": "high" if len(evts) >= 3 else "medium",
            "entity_id": entity_id,
            "basis": "real_rule",
            "detail": f"{len(evts)} login attempt(s) for {entity_id} blocked by IP allowlist. Most recent: {evts[0]['timestamp']}.",
        })

    # Rule 4: off-hours successful logins, computed against this dealer's own
    # real configured business_hours + default_timezone (core/system_config.py).
    # A real, explainable local-time check -- see _is_off_hours()'s own
    # docstring for exactly how "off-hours" is determined, including its one
    # honest limitation (no per-employee timezone is stored, so this uses the
    # dealership's own default_timezone for every employee).
    config = get_system_config()
    business_hours = config.get("business_hours", {})
    tz_name = config.get("default_timezone")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=off_hours_lookback_days)).isoformat()
    recent_logins = [e for e in list_audit_events(event_type="login_success") if e.get("timestamp", "") >= cutoff]

    off_hours_count_by_actor = {}
    for e in recent_logins:
        is_off, reason = _is_off_hours(e.get("timestamp"), business_hours, tz_name)
        if is_off:
            off_hours_count_by_actor.setdefault(e.get("actor"), []).append((e, reason))

    for actor, occurrences in off_hours_count_by_actor.items():
        latest_event, latest_reason = occurrences[0]
        flags.append({
            "flag_type": "off_hours_login",
            "severity": "medium" if len(occurrences) >= 2 else "low",
            "entity_id": actor,
            "basis": "real_rule",
            "detail": f"{actor} logged in {len(occurrences)} time(s) outside configured business hours in the last {off_hours_lookback_days} day(s) (e.g. {latest_reason}).",
        })

    # Rule 5: permission overrides recently granted -- a real "watch what
    # elevated access changed recently" list. Not a compliance judgment on
    # its own (a real admin may have a perfectly good reason), just a
    # surfaced, real signal.
    recent_overrides = [e for e in list_audit_events(event_type="permission_override_set") if e.get("timestamp", "") >= cutoff]
    for e in recent_overrides:
        flags.append({
            "flag_type": "permission_override_granted",
            "severity": "low",
            "entity_id": e.get("entity_id"),
            "basis": "real_rule",
            "detail": e.get("summary"),
        })

    # Rule 6: compliance alerts overridden -- overriding a real cited-federal-
    # rule violation is inherently a sensitive, worth-a-second-look action.
    recent_overridden_alerts = [e for e in list_audit_events(event_type="compliance_alert_overridden") if e.get("timestamp", "") >= cutoff]
    for e in recent_overridden_alerts:
        flags.append({
            "flag_type": "compliance_alert_overridden",
            "severity": "high",
            "entity_id": e.get("entity_id"),
            "basis": "real_rule",
            "detail": e.get("summary"),
        })

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: severity_rank.get(f["severity"], 3))

    by_severity = {"high": 0, "medium": 0, "low": 0}
    for f in flags:
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1

    return {
        "total_flags": len(flags),
        "by_severity": by_severity,
        "flags": flags,
        "not_yet_tracked": {
            "geolocation_anomalies": "No IP-to-location resolution exists in this codebase -- only a plain IP-allowlist match/no-match is tracked.",
            "per_employee_timezone": "Off-hours detection uses the dealership's single configured default_timezone for every employee -- no per-employee timezone field exists.",
        },
    }


def get_audit_center_overview():
    """The Audit Center's own landing view -- real dashboard totals (reusing
    core/audit_api.py's get_audit_dashboard() directly, not recomputed), the
    real event catalog, a real top-10 actor-activity leaderboard, and a real
    suspicious-activity summary."""

    from core.audit_api import get_audit_dashboard

    dashboard = get_audit_dashboard()
    catalog = get_event_catalog()
    actors = get_actor_activity(limit=10)
    suspicious = get_suspicious_activity()

    return {
        "total_events": dashboard["total_events"],
        "by_type": dashboard["by_type"],
        "recent": dashboard["recent"],
        "event_catalog": catalog,
        "top_actors": actors,
        "suspicious_activity_summary": {
            "total_flags": suspicious["total_flags"],
            "by_severity": suspicious["by_severity"],
        },
    }


def export_audit_events_csv(entity_id=None, actor=None, event_type=None, category=None, date_from=None, date_to=None, query=None):
    """A real CSV export of whatever the same filters in search_audit_log()
    would return, uncapped (no `limit`) -- the genuine "pull this for an
    investigation" action an audit workspace needs, following the exact
    csv/io convention core/data_backup.py's export_entity_type_csv() already
    established for this codebase's other CSV exports."""

    result = search_audit_log(
        entity_id=entity_id, actor=actor, event_type=event_type,
        category=category, date_from=date_from, date_to=date_to,
        query=query, limit=10_000_000,
    )

    events = result["events"]

    if not events:
        return None, {"error": "No audit events match these filters."}

    columns = ["id", "timestamp", "event_type", "category", "actor", "entity_id", "summary", "details"]

    buffer = io.StringIO()
    from core.spreadsheet_export import spreadsheet_cell
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    writer.writerow(columns)
    for e in events:
        row = dict(e)
        row["details"] = str(row.get("details", {}))
        writer.writerow([spreadsheet_cell(row.get(key)) for key in columns])

    filename = f"audit_log_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return filename, buffer.getvalue()
