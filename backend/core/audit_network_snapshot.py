"""
Tenant-side builder for GET /network/operational-health-snapshot -- the
narrowly-scoped, coarse-aggregate feed the NXTDeal Hub's Support Center
(hub/core/dealer_support.py, Dealer Management rebuild slice 5) uses for
Login Frequency / Usage Trend, since no other real signal for either exists
anywhere in this codebase.

Reuses the SAME safety pattern already established by
core/ai_management_network_api.py's /network/ai-management-snapshot (slice
4) and core/network_snapshot.py's /network/anonymous-snapshot (peer
benchmark): gated by the same DEALEROS_NETWORK_KEY shared secret
(core/network_snapshot_api.py's check_network_key()), and the payload is
DELIBERATELY as coarse as those two already-shipped precedents -- plain
integer counts over a fixed trailing window, no employee id, no employee
name, no individual event, no timestamp-per-event. This is judged safe for
the identical reason ai_management_network_api.py's own docstring already
gives: a count is not PII, and nothing here is any more identifying than
the call-attempt counters that endpoint already exposes.

Unlike /network/anonymous-snapshot, this fetch is deliberately
DEALER-IDENTIFIED on the Hub side (same as /network/ai-management-snapshot)
-- DEALEROS_NETWORK_KEY authenticates the Hub as a legitimate
server-to-server caller, it does not imply anonymization; anonymization is
a design choice specific to the cross-network peer-benchmark feature only.

WHAT THIS DOES NOT DO, stated plainly: it never returns which employee_id
logged in, only a plain count of distinct employee_ids seen in the window
(via a Python set()) -- the set itself is discarded, only its size is
returned. It never returns per-event timestamps, IP addresses, or any
freeform text (audit event 'summary' strings, which do contain employee_id
substrings, are read internally to build these counts but never included
in the response).

Two 30-day windows (current: last 30 days; previous: 31-60 days ago) are
computed in the same call so a Usage Trend can be derived without needing a
second stored historical snapshot anywhere.

SECURITY POSTURE (added Infrastructure & Platform Operations rebuild,
slice 4 of 4, closing) -- the NXTDeal Hub's Security menu item needed a
real, current-state, non-PII account-security signal for this tenant, and
this route -- already fetched by the Hub's own Support Center panel, same
DEALEROS_NETWORK_KEY gate -- was the natural place to add it rather than
standing up a 4th narrowly-scoped tenant route for one more small addition
(this fetch already runs the "current window vs. prior window" audit-log
scan; adding a current-state credential-store scan alongside it is a small
marginal cost). `_security_posture()` below reuses
backend/core/auth.py's real CredentialStore directly -- a real count of
currently-locked accounts (CredentialStore.get_lockout_status(), computed
live against the real clock, not a stale stored flag), a real count of
employees with a non-empty IP allowlist configured, and this dealership's
own real, structural lockout/password-policy CONSTANTS (MAX_FAILED_
ATTEMPTS, LOCKOUT_MINUTES, MIN_PASSWORD_LENGTH -- the same values
backend/core/auth.py's login()/change_password() actually enforce, not a
fabricated "compliance score"). Employee ids are used ONLY internally to
look up each record's lockout/allowlist state and are never included in
the response -- only the resulting counts.
"""

from datetime import datetime, timedelta, timezone

from core.audit import audit_log


_WINDOW_DAYS = 30

_LOGIN_SUCCESS_TYPES = ("login_success",)
_LOGIN_FAILED_TYPES = ("login_failed",)
_LOCKOUT_EVENT_TYPES = ("login_blocked_ip", "login_blocked_locked", "account_unlocked")


def _parse_timestamp(raw):
    try:
        value = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, AttributeError):
        return None


def _events_in_window(event_types, window_start, window_end):

    events = []
    for event_type in event_types:
        events.extend(audit_log.get_by_type(event_type))

    in_window = []
    for event in events:
        ts = _parse_timestamp(event.timestamp)
        if ts is None:
            continue
        if window_start <= ts < window_end:
            in_window.append(event)

    return in_window


def _window_counts(window_start, window_end):

    success_events = _events_in_window(_LOGIN_SUCCESS_TYPES, window_start, window_end)
    failed_events = _events_in_window(_LOGIN_FAILED_TYPES, window_start, window_end)
    lockout_events = _events_in_window(_LOCKOUT_EVENT_TYPES, window_start, window_end)

    distinct_employees = {e.entity_id for e in success_events if e.entity_id}

    return {
        "login_success_count": len(success_events),
        "login_failed_count": len(failed_events),
        "distinct_employees_logged_in": len(distinct_employees),
        "lockout_event_count": len(lockout_events),
    }


def _security_posture():
    """Real, current-state, non-PII account-security counts off backend/
    core/auth.py's CredentialStore -- see this module's own docstring for
    the full reasoning. Never raises: if auth couldn't be imported for any
    reason, reports an honest zero-state rather than erroring the whole
    snapshot."""

    try:
        from core.auth import (
            credential_store,
            MAX_FAILED_ATTEMPTS,
            LOCKOUT_MINUTES,
            MIN_PASSWORD_LENGTH,
        )
    except Exception:
        return {
            "total_accounts": 0,
            "locked_accounts_count": 0,
            "ip_allowlist_configured_count": 0,
            "ip_allowlisting_in_use": False,
            "password_policy_enforced": None,
            "note": "Auth module could not be loaded in this process.",
        }

    records = credential_store.list_records()

    locked_count = 0
    allowlist_configured_count = 0

    for record in records:
        employee_id = record["employee_id"]

        if credential_store.get_lockout_status(employee_id)["locked"]:
            locked_count += 1

        full_record = credential_store.get_record(employee_id)
        if full_record and full_record.get("ip_allowlist"):
            allowlist_configured_count += 1

    return {
        "total_accounts": len(records),
        "locked_accounts_count": locked_count,
        "ip_allowlist_configured_count": allowlist_configured_count,
        "ip_allowlisting_in_use": allowlist_configured_count > 0,
        "password_policy_enforced": True,
        "password_policy": {
            "min_length": MIN_PASSWORD_LENGTH,
            "requires_letter_and_digit": True,
        },
        "lockout_policy": {
            "max_failed_attempts": MAX_FAILED_ATTEMPTS,
            "lockout_minutes": LOCKOUT_MINUTES,
        },
        "note": (
            "Real, current-state counts off backend/core/auth.py's "
            "CredentialStore -- 'locked_accounts_count' is computed live "
            "against the real clock (CredentialStore.get_lockout_status()), "
            "not a stale stored flag. Employee ids are used only "
            "internally to look these counts up and are never included "
            "in this response -- no employee id, name, or email anywhere."
        ),
    }


def build_operational_health_snapshot():
    """Real, coarse-aggregate operational signal over the tenant's own real
    audit log (backend/core/audit.py) -- login success/fail/lockout counts
    plus a distinct-employee count, across a current + prior 30-day window
    so a trend direction can be derived. No PII, no per-event detail."""

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=_WINDOW_DAYS)
    previous_start = now - timedelta(days=_WINDOW_DAYS * 2)

    current = _window_counts(current_start, now)
    previous = _window_counts(previous_start, current_start)

    current_total = current["login_success_count"]
    previous_total = previous["login_success_count"]

    if previous_total == 0 and current_total == 0:
        trend = "no_data"
    elif previous_total == 0:
        trend = "increasing"
    elif current_total > previous_total * 1.1:
        trend = "increasing"
    elif current_total < previous_total * 0.9:
        trend = "decreasing"
    else:
        trend = "stable"

    return {
        "window_days": _WINDOW_DAYS,
        "current_window": current,
        "previous_window": previous,
        "trend": trend,
        "security_posture": _security_posture(),
        "note": (
            "Coarse, aggregate-only counts over the tenant's own real audit "
            "log (backend/core/audit.py) for the trailing/prior 30-day "
            "windows. No employee id, name, IP address, or per-event "
            "timestamp is included -- only plain integer counts, one of "
            "which (distinct_employees_logged_in) is the SIZE of a set() "
            "computed then discarded, never the set itself."
        ),
    }
