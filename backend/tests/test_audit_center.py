"""Tests for core/audit_center.py -- the real audit-log investigative
workspace (search/filter/export, per-actor activity, and the transparent
rules-based suspicious-activity engine).

Audit events are NOT graph entities (see the module's own docstring) --
this module never touches core.dealeros.ledger, only core.audit's AuditLog
singleton and core.auth's CredentialStore singleton. Both already expose a
reset() used elsewhere in this test suite, so we reuse that pattern instead
of the ledger fixture."""

import os
import sys
from datetime import datetime, timedelta, timezone, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

import core.audit_center as ac
from core.audit import audit_log, AuditEvent
from core.auth import credential_store


@pytest.fixture(autouse=True)
def fresh_audit_log():
    audit_log.reset()
    yield
    audit_log.reset()


@pytest.fixture(autouse=True)
def fresh_credential_store():
    credential_store.reset()
    yield
    credential_store.reset()


def _event(event_type, entity_id=None, actor="EMP-1", summary="", timestamp=None, details=None):
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    return AuditEvent(id=f"AUDIT-{event_type}", event_type=event_type, entity_id=entity_id, actor=actor, summary=summary, details=details or {}, timestamp=ts)


def _iso(offset_days=0):
    return (datetime.now(timezone.utc) - timedelta(days=offset_days)).isoformat()


def _all_closed_business_hours():
    return {day: "Closed" for day in ac._DAY_NAMES}


def _config(business_hours=None, default_timezone=None):
    return {"business_hours": business_hours if business_hours is not None else _all_closed_business_hours(), "default_timezone": default_timezone}


# ---------------------------------------------------------------------------
# get_event_catalog()
# ---------------------------------------------------------------------------


class TestGetEventCatalog:

    def test_covers_every_event_type(self):
        result = ac.get_event_catalog()

        assert result["total_event_types"] == len(ac.EVENT_CATEGORIES)
        all_listed = [et for types in result["categories"].values() for et in types]
        assert set(all_listed) == set(ac.EVENT_CATEGORIES.keys())

    def test_each_category_list_is_sorted(self):
        result = ac.get_event_catalog()

        for types in result["categories"].values():
            assert types == sorted(types)


# ---------------------------------------------------------------------------
# _parse_hours_range()
# ---------------------------------------------------------------------------


class TestParseHoursRange:

    def test_closed_returns_none(self):
        assert ac._parse_hours_range("Closed") is None
        assert ac._parse_hours_range("closed") is None

    def test_empty_returns_none(self):
        assert ac._parse_hours_range("") is None
        assert ac._parse_hours_range(None) is None

    def test_bad_shape_returns_none(self):
        assert ac._parse_hours_range("9:00 AM to 7:00 PM") is None

    def test_unparseable_time_returns_none(self):
        assert ac._parse_hours_range("nine - five") is None

    def test_valid_range_parses(self):
        result = ac._parse_hours_range("9:00 AM - 7:00 PM")

        assert result == (time(9, 0), time(19, 0))


# ---------------------------------------------------------------------------
# _is_off_hours()
# ---------------------------------------------------------------------------


class TestIsOffHours:

    def test_unparseable_timestamp(self):
        is_off, reason = ac._is_off_hours("not-a-timestamp", {}, None)

        assert is_off is None
        assert "unparseable timestamp" in reason

    def test_closed_day_is_off_hours(self):
        ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        day_name = ac._DAY_NAMES[ts.weekday()]
        business_hours = {day_name: "Closed"}

        is_off, reason = ac._is_off_hours(ts.isoformat(), business_hours, None)

        assert is_off is True
        assert "Closed" in reason

    def test_within_window_is_not_off_hours(self):
        ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        day_name = ac._DAY_NAMES[ts.weekday()]
        business_hours = {day_name: "9:00 AM - 7:00 PM"}

        is_off, reason = ac._is_off_hours(ts.isoformat(), business_hours, None)

        assert is_off is False
        assert "within" in reason

    def test_outside_window_is_off_hours(self):
        ts = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)
        day_name = ac._DAY_NAMES[ts.weekday()]
        business_hours = {day_name: "9:00 AM - 7:00 PM"}

        is_off, reason = ac._is_off_hours(ts.isoformat(), business_hours, None)

        assert is_off is True
        assert "outside" in reason

    def test_unparseable_business_hours_returns_none(self):
        ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        day_name = ac._DAY_NAMES[ts.weekday()]
        business_hours = {day_name: "garbage"}

        is_off, reason = ac._is_off_hours(ts.isoformat(), business_hours, None)

        assert is_off is None
        assert "unparseable business_hours" in reason


# ---------------------------------------------------------------------------
# search_audit_log()
# ---------------------------------------------------------------------------


class TestSearchAuditLog:

    def test_filters_by_entity_actor_event_type(self):
        audit_log.load_events([
            _event("login_success", entity_id="EMP-1", actor="EMP-1"),
            _event("login_failed", entity_id="EMP-2", actor="EMP-2"),
        ])

        result = ac.search_audit_log(event_type="login_success")

        assert result["total_matches"] == 1
        assert result["events"][0]["event_type"] == "login_success"

    def test_filters_by_category(self):
        audit_log.load_events([
            _event("login_success", actor="EMP-1"),
            _event("credential_created", actor="EMP-1"),
        ])

        result = ac.search_audit_log(category="Authentication")

        assert result["total_matches"] == 1
        assert result["events"][0]["event_type"] == "login_success"

    def test_filters_by_date_range(self):
        audit_log.load_events([
            _event("login_success", timestamp="2026-06-01T10:00:00+00:00"),
            _event("login_success", timestamp="2026-07-01T10:00:00+00:00"),
        ])

        result = ac.search_audit_log(date_from="2026-07-01T00:00:00", date_to="2026-07-31T23:59:59")

        assert result["total_matches"] == 1

    def test_query_matches_summary_entity_actor(self):
        audit_log.load_events([
            _event("login_success", entity_id="EMP-9", actor="EMP-9", summary="A special login occurred"),
            _event("login_success", entity_id="EMP-2", actor="EMP-2", summary="Nothing notable"),
        ])

        result = ac.search_audit_log(query="special")

        assert result["total_matches"] == 1
        assert result["events"][0]["entity_id"] == "EMP-9"

    def test_limit_trims_returned_but_not_total(self):
        audit_log.load_events([_event("login_success") for _ in range(3)])

        result = ac.search_audit_log(limit=1)

        assert result["total_matches"] == 3
        assert result["returned"] == 1

    def test_events_carry_category(self):
        audit_log.load_events([_event("login_success")])

        result = ac.search_audit_log()

        assert result["events"][0]["category"] == "Authentication"

    def test_unknown_event_type_falls_back_to_other(self):
        audit_log.load_events([_event("some_future_event_type")])

        result = ac.search_audit_log()

        assert result["events"][0]["category"] == "Other"


# ---------------------------------------------------------------------------
# get_actor_activity()
# ---------------------------------------------------------------------------


class TestGetActorActivity:

    def test_ranks_by_total_count_desc(self):
        audit_log.load_events([
            _event("login_success", actor="EMP-1", timestamp="2026-06-01T10:00:00+00:00"),
            _event("login_success", actor="EMP-1", timestamp="2026-06-02T10:00:00+00:00"),
            _event("login_success", actor="EMP-2", timestamp="2026-06-01T10:00:00+00:00"),
        ])

        result = ac.get_actor_activity()

        assert result["total_actors"] == 2
        assert result["actors"][0]["actor"] == "EMP-1"
        assert result["actors"][0]["total"] == 2

    def test_first_and_last_seen(self):
        audit_log.load_events([
            _event("login_success", actor="EMP-1", timestamp="2026-06-05T10:00:00+00:00"),
            _event("login_success", actor="EMP-1", timestamp="2026-06-01T10:00:00+00:00"),
            _event("login_success", actor="EMP-1", timestamp="2026-06-10T10:00:00+00:00"),
        ])

        result = ac.get_actor_activity()

        bucket = result["actors"][0]
        assert bucket["first_seen"] == "2026-06-01T10:00:00+00:00"
        assert bucket["last_seen"] == "2026-06-10T10:00:00+00:00"

    def test_by_event_type_breakdown(self):
        audit_log.load_events([
            _event("login_success", actor="EMP-1"),
            _event("login_success", actor="EMP-1"),
            _event("credential_reset", actor="EMP-1"),
        ])

        result = ac.get_actor_activity()

        assert result["actors"][0]["by_event_type"] == {"login_success": 2, "credential_reset": 1}

    def test_limit(self):
        audit_log.load_events([
            _event("login_success", actor="EMP-1"),
            _event("login_success", actor="EMP-2"),
            _event("login_success", actor="EMP-3"),
        ])

        result = ac.get_actor_activity(limit=2)

        assert result["total_actors"] == 3
        assert len(result["actors"]) == 2


# ---------------------------------------------------------------------------
# get_actor_timeline()
# ---------------------------------------------------------------------------


class TestGetActorTimeline:

    def test_scopes_to_one_actor_most_recent_first(self):
        audit_log.load_events([
            _event("login_success", actor="EMP-1", timestamp="2026-06-01T10:00:00+00:00"),
            _event("login_success", actor="EMP-1", timestamp="2026-06-05T10:00:00+00:00"),
            _event("login_success", actor="EMP-2", timestamp="2026-06-03T10:00:00+00:00"),
        ])

        result = ac.get_actor_timeline("EMP-1")

        assert result["total_events"] == 2
        assert result["events"][0]["timestamp"] == "2026-06-05T10:00:00+00:00"

    def test_limit(self):
        audit_log.load_events([_event("login_success", actor="EMP-1") for _ in range(3)])

        result = ac.get_actor_timeline("EMP-1", limit=1)

        assert result["total_events"] == 1


# ---------------------------------------------------------------------------
# get_suspicious_activity()
# ---------------------------------------------------------------------------


class TestGetSuspiciousActivity:

    def test_locked_account_flags_high(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())
        credential_store.set_credential("EMP-1", "pw", "SALES")
        credential_store.credentials["EMP-1"]["failed_attempts"] = 5
        credential_store.credentials["EMP-1"]["locked_until"] = _iso(offset_days=-1)  # future

        result = ac.get_suspicious_activity()

        locked_flags = [f for f in result["flags"] if f["flag_type"] == "account_locked"]
        assert len(locked_flags) == 1
        assert locked_flags[0]["severity"] == "high"
        assert locked_flags[0]["entity_id"] == "EMP-1"

    def test_elevated_failed_attempts_below_lockout(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())
        credential_store.set_credential("EMP-1", "pw", "SALES")
        credential_store.credentials["EMP-1"]["failed_attempts"] = 2

        result = ac.get_suspicious_activity()

        flags = [f for f in result["flags"] if f["flag_type"] == "elevated_failed_attempts"]
        assert len(flags) == 1
        assert flags[0]["severity"] == "low"

    def test_elevated_failed_attempts_medium_at_three_or_more(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())
        credential_store.set_credential("EMP-1", "pw", "SALES")
        credential_store.credentials["EMP-1"]["failed_attempts"] = 3

        result = ac.get_suspicious_activity()

        flags = [f for f in result["flags"] if f["flag_type"] == "elevated_failed_attempts"]
        assert flags[0]["severity"] == "medium"

    def test_zero_failed_attempts_no_flag(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())
        credential_store.set_credential("EMP-1", "pw", "SALES")

        result = ac.get_suspicious_activity()

        flags = [f for f in result["flags"] if f["flag_type"] == "elevated_failed_attempts"]
        assert flags == []

    def test_ip_blocked_flags(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())
        audit_log.record("login_blocked_ip", "blocked", entity_id="EMP-1", actor="EMP-1")

        result = ac.get_suspicious_activity()

        flags = [f for f in result["flags"] if f["flag_type"] == "ip_allowlist_blocked"]
        assert len(flags) == 1
        assert flags[0]["severity"] == "medium"

    def test_ip_blocked_high_severity_at_three_or_more(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())
        for _ in range(3):
            audit_log.record("login_blocked_ip", "blocked", entity_id="EMP-1", actor="EMP-1")

        result = ac.get_suspicious_activity()

        flags = [f for f in result["flags"] if f["flag_type"] == "ip_allowlist_blocked"]
        assert flags[0]["severity"] == "high"

    def test_off_hours_login_flagged_when_all_days_closed(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config(business_hours=_all_closed_business_hours()))
        audit_log.record("login_success", "logged in", actor="EMP-1")

        result = ac.get_suspicious_activity()

        flags = [f for f in result["flags"] if f["flag_type"] == "off_hours_login"]
        assert len(flags) == 1
        assert flags[0]["severity"] == "low"

    def test_off_hours_medium_at_two_or_more_occurrences(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config(business_hours=_all_closed_business_hours()))
        audit_log.record("login_success", "logged in", actor="EMP-1")
        audit_log.record("login_success", "logged in again", actor="EMP-1")

        result = ac.get_suspicious_activity()

        flags = [f for f in result["flags"] if f["flag_type"] == "off_hours_login"]
        assert flags[0]["severity"] == "medium"

    def test_no_off_hours_flag_with_no_logins(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config(business_hours=_all_closed_business_hours()))

        result = ac.get_suspicious_activity()

        flags = [f for f in result["flags"] if f["flag_type"] == "off_hours_login"]
        assert flags == []

    def test_permission_override_granted_flags_low(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())
        audit_log.record("permission_override_set", "granted a permission", entity_id="EMP-1", actor="ADMIN-1")

        result = ac.get_suspicious_activity()

        flags = [f for f in result["flags"] if f["flag_type"] == "permission_override_granted"]
        assert len(flags) == 1
        assert flags[0]["severity"] == "low"

    def test_compliance_alert_overridden_flags_high(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())
        audit_log.record("compliance_alert_overridden", "overrode an alert", entity_id="ALERT-1", actor="ADMIN-1")

        result = ac.get_suspicious_activity()

        flags = [f for f in result["flags"] if f["flag_type"] == "compliance_alert_overridden"]
        assert len(flags) == 1
        assert flags[0]["severity"] == "high"

    def test_flags_sorted_by_severity(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())
        audit_log.record("permission_override_set", "low sev", entity_id="EMP-1", actor="ADMIN-1")
        audit_log.record("compliance_alert_overridden", "high sev", entity_id="ALERT-1", actor="ADMIN-1")

        result = ac.get_suspicious_activity()

        severities = [f["severity"] for f in result["flags"]]
        assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s])

    def test_by_severity_counts(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())
        audit_log.record("compliance_alert_overridden", "high sev", entity_id="ALERT-1", actor="ADMIN-1")

        result = ac.get_suspicious_activity()

        assert result["total_flags"] == sum(result["by_severity"].values())
        assert result["by_severity"]["high"] >= 1

    def test_not_yet_tracked_notes_present(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())

        result = ac.get_suspicious_activity()

        assert "geolocation_anomalies" in result["not_yet_tracked"]
        assert "per_employee_timezone" in result["not_yet_tracked"]


# ---------------------------------------------------------------------------
# get_audit_center_overview()
# ---------------------------------------------------------------------------


class TestGetAuditCenterOverview:

    def test_composes_dashboard_catalog_actors_suspicious(self, monkeypatch):
        monkeypatch.setattr(ac, "get_system_config", lambda: _config())
        audit_log.record("login_success", "logged in", actor="EMP-1")

        result = ac.get_audit_center_overview()

        assert result["total_events"] == 1
        assert "login_success" in result["by_type"]
        assert result["event_catalog"]["total_event_types"] == len(ac.EVENT_CATEGORIES)
        assert result["top_actors"]["total_actors"] == 1
        assert "total_flags" in result["suspicious_activity_summary"]
        assert "by_severity" in result["suspicious_activity_summary"]


# ---------------------------------------------------------------------------
# export_audit_events_csv()
# ---------------------------------------------------------------------------


class TestExportAuditEventsCsv:

    def test_no_matches_returns_error(self):
        filename, payload = ac.export_audit_events_csv(event_type="nonexistent_type")

        assert filename is None
        assert "error" in payload

    def test_success_returns_csv_content(self):
        audit_log.record("login_success", "A login happened", entity_id="EMP-1", actor="EMP-1")

        filename, csv_text = ac.export_audit_events_csv()

        assert filename.startswith("audit_log_export_")
        assert filename.endswith(".csv")
        assert "event_type" in csv_text
        assert "login_success" in csv_text
        assert "A login happened" in csv_text
