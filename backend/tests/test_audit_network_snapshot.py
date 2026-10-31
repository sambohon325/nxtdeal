"""
Test coverage for core/audit_network_snapshot.py -- the tenant-side builder
behind GET /network/operational-health-snapshot (the NXTDeal Hub's Support
Center Login Frequency / Usage Trend signal, plus the Security posture block
added in the Infrastructure & Platform Operations rebuild's closing slice).

Covers: _parse_timestamp() (Z-suffix, tz-naive-defaults-to-UTC, already-aware,
invalid/None/empty all -> None); _events_in_window() ([start, end) boundary --
confirmed live that window_start is inclusive and window_end is exclusive, and
that an unparseable timestamp is silently skipped rather than raising or
crashing the whole scan); _window_counts() (login_success_count includes a
None-entity_id event but distinct_employees_logged_in only counts real,
non-None entity_ids via a set(); lockout_event_count sums all 3 real lockout
event types; login_failed_count is its own separate tally); _security_posture()
(real CredentialStore-backed counts -- total_accounts, locked_accounts_count
via the real live get_lockout_status() clock check, ip_allowlist_configured_
count, and the real MAX_FAILED_ATTEMPTS/LOCKOUT_MINUTES/MIN_PASSWORD_LENGTH
policy constants surfaced verbatim); and build_operational_health_snapshot()'s
real trend derivation (no_data / increasing / decreasing / stable, including
the exact >1.1x / <0.9x boundary behavior -- confirmed live that landing
exactly ON either boundary resolves to "stable", since both comparisons are
strict > / <, not >= / <=).

Every value below was live-verified against this exact module before being
written as an assertion.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

import pytest

from core.dealeros import ledger
from core.audit import audit_log, AuditEvent
from core import auth as auth_module
from core.auth import MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES, MIN_PASSWORD_LENGTH

import core.audit_network_snapshot as ans


@pytest.fixture(autouse=True)
def fresh_state():
    ledger.reset()
    audit_log.reset()
    auth_module.credential_store.reset()
    yield
    ledger.reset()
    audit_log.reset()
    auth_module.credential_store.reset()


def _add_event(event_type, entity_id, when, ts_override=None):
    audit_log.events.append(AuditEvent(
        id=f"AUDIT-TEST-{len(audit_log.events)}",
        event_type=event_type,
        entity_id=entity_id,
        actor="system",
        summary="test",
        timestamp=ts_override if ts_override is not None else when.isoformat(),
    ))


def _add_success_events(n, days_ago):
    now = datetime.now(timezone.utc)
    when = now - timedelta(days=days_ago)
    for i in range(n):
        _add_event("login_success", f"EMP-{i}", when)


class TestParseTimestamp:

    def test_z_suffix_parses_as_utc(self):
        result = ans._parse_timestamp("2026-07-01T00:00:00Z")
        assert result == datetime(2026, 7, 1, tzinfo=timezone.utc)

    def test_naive_timestamp_defaults_to_utc(self):
        result = ans._parse_timestamp("2026-07-01T00:00:00")
        assert result == datetime(2026, 7, 1, tzinfo=timezone.utc)

    def test_already_aware_timestamp_keeps_its_own_offset(self):
        result = ans._parse_timestamp("2026-07-01T00:00:00+05:00")
        assert result.utcoffset() == timedelta(hours=5)

    def test_invalid_string_returns_none(self):
        assert ans._parse_timestamp("not-a-date") is None

    def test_none_input_returns_none(self):
        assert ans._parse_timestamp(None) is None

    def test_empty_string_returns_none(self):
        assert ans._parse_timestamp("") is None


class TestEventsInWindow:

    def test_window_start_is_inclusive_window_end_is_exclusive(self):
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=10)
        window_end = now

        _add_event("login_success", "EMP-1", window_start)  # == start -> included
        _add_event("login_success", "EMP-2", window_end)  # == end -> excluded
        _add_event("login_success", "EMP-3", window_start - timedelta(seconds=1))  # before -> excluded
        _add_event("login_success", "EMP-4", window_start + timedelta(days=1))  # inside -> included

        events = ans._events_in_window(("login_success",), window_start, window_end)
        assert {e.entity_id for e in events} == {"EMP-1", "EMP-4"}

    def test_unparseable_timestamp_is_silently_skipped(self):
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=10)
        window_end = now

        _add_event("login_success", "EMP-1", now, ts_override="garbage-timestamp")

        events = ans._events_in_window(("login_success",), window_start, window_end)
        assert events == []

    def test_only_matching_event_types_are_returned(self):
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=10)
        window_end = now
        mid = window_start + timedelta(days=1)

        _add_event("login_success", "EMP-1", mid)
        _add_event("login_failed", "EMP-2", mid)

        events = ans._events_in_window(("login_success",), window_start, window_end)
        assert len(events) == 1
        assert events[0].entity_id == "EMP-1"


class TestWindowCounts:

    def test_login_success_count_includes_a_none_entity_id_event(self):
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=10)
        mid = window_start + timedelta(days=1)

        _add_event("login_success", None, mid)

        counts = ans._window_counts(window_start, now)
        assert counts["login_success_count"] == 1
        assert counts["distinct_employees_logged_in"] == 0

    def test_distinct_employees_logged_in_deduplicates_via_a_set(self):
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=10)
        mid = window_start + timedelta(days=1)

        _add_event("login_success", "EMP-1", window_start)
        _add_event("login_success", "EMP-1", mid)

        counts = ans._window_counts(window_start, now)
        assert counts["login_success_count"] == 2
        assert counts["distinct_employees_logged_in"] == 1

    def test_lockout_event_count_sums_all_three_real_lockout_event_types(self):
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=10)
        mid = window_start + timedelta(days=1)

        _add_event("login_blocked_ip", "EMP-1", mid)
        _add_event("login_blocked_locked", "EMP-2", mid)
        _add_event("account_unlocked", "EMP-3", mid)

        counts = ans._window_counts(window_start, now)
        assert counts["lockout_event_count"] == 3

    def test_login_failed_count_is_its_own_separate_tally(self):
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=10)
        mid = window_start + timedelta(days=1)

        _add_event("login_failed", "EMP-1", mid)
        _add_event("login_failed", "EMP-2", mid)

        counts = ans._window_counts(window_start, now)
        assert counts["login_failed_count"] == 2
        assert counts["login_success_count"] == 0

    def test_unrelated_event_type_is_ignored(self):
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=10)
        mid = window_start + timedelta(days=1)

        _add_event("some_other_event", "EMP-1", mid)

        counts = ans._window_counts(window_start, now)
        assert counts == {
            "login_success_count": 0,
            "login_failed_count": 0,
            "distinct_employees_logged_in": 0,
            "lockout_event_count": 0,
        }


class TestSecurityPosture:

    def test_empty_credential_store(self):
        posture = ans._security_posture()
        assert posture["total_accounts"] == 0
        assert posture["locked_accounts_count"] == 0
        assert posture["ip_allowlist_configured_count"] == 0
        assert posture["ip_allowlisting_in_use"] is False

    def test_real_policy_constants_are_surfaced_verbatim(self):
        posture = ans._security_posture()
        assert posture["lockout_policy"] == {
            "max_failed_attempts": MAX_FAILED_ATTEMPTS,
            "lockout_minutes": LOCKOUT_MINUTES,
        }
        assert posture["password_policy"]["min_length"] == MIN_PASSWORD_LENGTH

    def test_total_accounts_matches_real_credential_count(self):
        auth_module.credential_store.set_credential("EMP-1", "password123", "ADMIN")
        auth_module.credential_store.set_credential("EMP-2", "password123", "SALES")
        posture = ans._security_posture()
        assert posture["total_accounts"] == 2

    def test_locked_accounts_count_reflects_the_real_live_lockout_clock(self):
        auth_module.credential_store.set_credential("EMP-1", "password123", "SALES")
        for _ in range(MAX_FAILED_ATTEMPTS):
            auth_module.credential_store.record_failed_login("EMP-1")

        posture = ans._security_posture()
        assert posture["locked_accounts_count"] == 1

    def test_below_threshold_failed_attempts_do_not_count_as_locked(self):
        auth_module.credential_store.set_credential("EMP-1", "password123", "SALES")
        for _ in range(MAX_FAILED_ATTEMPTS - 1):
            auth_module.credential_store.record_failed_login("EMP-1")

        posture = ans._security_posture()
        assert posture["locked_accounts_count"] == 0

    def test_ip_allowlist_configured_count_and_flag(self):
        auth_module.credential_store.set_credential("EMP-1", "password123", "SALES")
        auth_module.credential_store.set_credential("EMP-2", "password123", "SALES")
        auth_module.credential_store.set_ip_allowlist("EMP-1", ["1.2.3.4"])

        posture = ans._security_posture()
        assert posture["ip_allowlist_configured_count"] == 1
        assert posture["ip_allowlisting_in_use"] is True

    def test_employee_ids_never_appear_anywhere_in_the_response(self):
        auth_module.credential_store.set_credential("EMP-SECRET-1", "password123", "SALES")
        posture = ans._security_posture()
        import json
        assert "EMP-SECRET-1" not in json.dumps(posture)


class TestBuildOperationalHealthSnapshot:

    def test_no_data_trend_when_both_windows_are_empty(self):
        snap = ans.build_operational_health_snapshot()
        assert snap["trend"] == "no_data"
        assert snap["window_days"] == 30
        assert snap["current_window"]["login_success_count"] == 0
        assert snap["previous_window"]["login_success_count"] == 0

    def test_top_level_shape(self):
        snap = ans.build_operational_health_snapshot()
        assert set(snap.keys()) == {
            "window_days", "current_window", "previous_window",
            "trend", "security_posture", "note",
        }

    def test_previous_zero_current_positive_is_increasing(self):
        _add_success_events(3, days_ago=5)
        snap = ans.build_operational_health_snapshot()
        assert snap["trend"] == "increasing"
        assert snap["current_window"]["login_success_count"] == 3
        assert snap["previous_window"]["login_success_count"] == 0

    def test_current_more_than_1_1x_previous_is_increasing(self):
        _add_success_events(4, days_ago=5)   # current: 4
        _add_success_events(3, days_ago=45)  # previous: 3 -> 4 > 3*1.1=3.3
        snap = ans.build_operational_health_snapshot()
        assert snap["trend"] == "increasing"

    def test_current_less_than_0_9x_previous_is_decreasing(self):
        _add_success_events(2, days_ago=5)   # current: 2
        _add_success_events(3, days_ago=45)  # previous: 3 -> 2 < 3*0.9=2.7
        snap = ans.build_operational_health_snapshot()
        assert snap["trend"] == "decreasing"

    def test_equal_totals_are_stable(self):
        _add_success_events(10, days_ago=5)
        _add_success_events(10, days_ago=45)
        snap = ans.build_operational_health_snapshot()
        assert snap["trend"] == "stable"

    def test_exactly_1_1x_boundary_is_stable_not_increasing(self):
        # 11 > 10 * 1.1 == 11.0 is False (strict >, not >=) -> stable
        _add_success_events(11, days_ago=5)
        _add_success_events(10, days_ago=45)
        snap = ans.build_operational_health_snapshot()
        assert snap["trend"] == "stable"

    def test_exactly_0_9x_boundary_is_stable_not_decreasing(self):
        # 9 < 10 * 0.9 == 9.0 is False (strict <, not <=) -> stable
        _add_success_events(9, days_ago=5)
        _add_success_events(10, days_ago=45)
        snap = ans.build_operational_health_snapshot()
        assert snap["trend"] == "stable"

    def test_events_outside_both_windows_are_not_counted(self):
        _add_success_events(1, days_ago=5)    # inside current
        _add_success_events(1, days_ago=90)   # outside both windows entirely
        snap = ans.build_operational_health_snapshot()
        assert snap["current_window"]["login_success_count"] == 1
        assert snap["previous_window"]["login_success_count"] == 0

    def test_security_posture_is_embedded_and_real(self):
        auth_module.credential_store.set_credential("EMP-1", "password123", "ADMIN")
        snap = ans.build_operational_health_snapshot()
        assert snap["security_posture"]["total_accounts"] == 1
