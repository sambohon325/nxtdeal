"""
Test coverage for core/operations_alerts.py + core/operations_alerts_api.py --
Operations' "Alerts" nervous system: a real, severity-ranked, cross-source
aggregation of 7 real exception signal types (compliance, ownership mismatch,
stalled deals, missing deal jackets, overdue tasks, at-risk deliveries,
critical-band aging inventory) into one feed, plus the one real mutation this
module adds -- acknowledge_alert(), which turns the two signal types with no
existing dedicated action into a real, deduped OperationsTask.

This module reuses already-independently-tested dependencies
(core/workflow_tab_data.py's inventory_lot_audit(), core/operations_tasks.py's
create_task()/list_tasks(), core/inventory_aging.py's get_aging_board(),
core/operations_scheduling.py's get_delivery_risk_board(),
core/compliance_api.py's list_alerts_api()) -- these tests focus on this
module's own real logic: severity assignment per source, the red-first sort,
get_alert_stats()'s by_type rollup, acknowledge_alert()'s three real paths, and
the ACL layer's view/mutate role split.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.relationship_types import PURCHASED

import core.operations_alerts as oa
import core.operations_alerts_api as oaapi
from core.operations_tasks import list_tasks


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


PAST = "2020-01-01T00:00:00+00:00"
FUTURE = "2099-01-01T00:00:00+00:00"


def _iso_days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _vehicle(vid, **attrs):
    ledger.add_entity(Entity(id=vid, entity_type="Vehicle", attributes=attrs))


def _customer(cid, **attrs):
    ledger.add_entity(Entity(id=cid, entity_type="Customer", attributes=attrs))


def _deal(did, **attrs):
    ledger.add_entity(Entity(id=did, entity_type="Deal", attributes=attrs))


def _document(doc_id, **attrs):
    ledger.add_entity(Entity(id=doc_id, entity_type="Document", attributes=attrs))


def _compliance_alert(aid, **attrs):
    attrs.setdefault("status", "open")
    ledger.add_entity(Entity(id=aid, entity_type="ComplianceAlert", attributes=attrs))


def _operations_task(tid, **attrs):
    attrs.setdefault("status", "open")
    attrs.setdefault("owner_bucket", "Unassigned")
    ledger.add_entity(Entity(id=tid, entity_type="OperationsTask", attributes=attrs))


def _purchased(customer_id, vehicle_id):
    ledger.add_relationship(Relationship(
        source_id=customer_id, target_id=vehicle_id, relationship_type=PURCHASED,
    ))


class TestEmptyLedgerSanity:

    def test_get_alert_feed_empty(self):
        feed = oa.get_alert_feed("ADMIN")
        assert feed == {"count": 0, "red_count": 0, "yellow_count": 0, "alerts": []}

    def test_get_alert_stats_empty(self):
        stats = oa.get_alert_stats("ADMIN")
        assert stats == {"total": 0, "red": 0, "yellow": 0, "by_type": {}}


class TestComplianceSignal:

    def test_high_severity_is_red_with_law_as_title(self):
        _compliance_alert(
            "CMPL-1", severity="high", law="TILA", description="Missing APR disclosure",
            entity_id="DEAL-1",
        )
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 1
        alert = feed["alerts"][0]
        assert alert["alert_type"] == "compliance"
        assert alert["severity"] == "red"
        assert alert["title"] == "TILA"
        assert alert["detail"] == "Missing APR disclosure"
        assert alert["source_id"] == "CMPL-1"
        assert alert["linked_entity_id"] == "DEAL-1"
        assert alert["suggested_action"] == "resolve_compliance"

    def test_non_high_severity_is_yellow(self):
        _compliance_alert("CMPL-1", severity="medium", law="GLBA")
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["severity"] == "yellow"

    def test_missing_severity_defaults_to_yellow(self):
        _compliance_alert("CMPL-1", law="ECOA")
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["severity"] == "yellow"

    def test_title_falls_back_to_category_when_no_law(self):
        _compliance_alert("CMPL-1", category="Data Privacy")
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["title"] == "Data Privacy"

    def test_title_falls_back_to_generic_when_no_law_or_category(self):
        _compliance_alert("CMPL-1")
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["title"] == "Compliance exception"

    def test_missing_description_defaults_to_empty_string(self):
        _compliance_alert("CMPL-1")
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["detail"] == ""

    def test_resolved_alerts_are_excluded(self):
        _compliance_alert("CMPL-1", status="resolved")
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0

    def test_a_role_denied_compliance_access_silently_drops_that_source(self):
        _compliance_alert("CMPL-1", severity="high")
        feed = oa.get_alert_feed("SALES")
        # list_alerts_api() rejects SALES (COMPLIANCE_ROLES is ADMIN/OPERATIONS
        # only) -- the whole feed still succeeds, just without a compliance entry.
        assert feed["count"] == 0
        assert feed["alerts"] == []


class TestOwnershipMismatchSignal:

    def test_sold_vehicle_with_no_purchased_relationship_is_flagged_red(self):
        _vehicle("VEH-1", VIN="1FTFW1ET5BFA00001", DateSold="2026-01-01")
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 1
        alert = feed["alerts"][0]
        assert alert["alert_type"] == "ownership_mismatch"
        assert alert["severity"] == "red"
        assert "1FTFW1ET5BFA00001" in alert["detail"]
        assert alert["source_id"] == "VEH-1"
        assert alert["linked_entity_id"] == "VEH-1"
        assert alert["suggested_action"] == "acknowledge"

    def test_sold_vehicle_with_a_purchased_relationship_is_excluded(self):
        _vehicle("VEH-1", VIN="1FTFW1ET5BFA00001", DateSold="2026-01-01")
        _customer("CUST-1")
        _purchased("CUST-1", "VEH-1")
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0

    def test_unsold_vehicle_is_never_flagged(self):
        _vehicle("VEH-1", VIN="1FTFW1ET5BFA00001")
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0


class TestStalledDealSignal:

    def test_financing_deal_stalled_7_plus_days_is_red(self):
        _deal("DEAL-1", status="financing", updated_at=_iso_days_ago(10))
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["alert_type"] == "stalled_deal"
        assert alert["severity"] == "red"
        assert "10" in alert["title"]
        assert alert["source_id"] == "DEAL-1"
        assert alert["linked_entity_id"] == "DEAL-1"
        assert alert["suggested_action"] == "acknowledge"

    def test_contract_deal_stalled_3_to_6_days_is_yellow(self):
        _deal("DEAL-1", status="contract", updated_at=_iso_days_ago(5))
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["severity"] == "yellow"

    def test_stalled_under_3_days_is_excluded(self):
        _deal("DEAL-1", status="financing", updated_at=_iso_days_ago(1))
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0

    def test_exactly_7_days_is_red_boundary(self):
        _deal("DEAL-1", status="financing", updated_at=_iso_days_ago(7))
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["severity"] == "red"

    def test_non_financing_or_contract_status_is_excluded(self):
        # "funded" is deliberately avoided here -- it would also trigger the
        # missing_deal_jacket AND at_risk_delivery signals, which isn't what
        # this test is isolating.
        _deal("DEAL-1", status="desking", updated_at=_iso_days_ago(30))
        _deal("DEAL-2", status="cancelled", updated_at=_iso_days_ago(30))
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0

    def test_missing_updated_at_is_excluded(self):
        _deal("DEAL-1", status="financing")
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0

    def test_unparseable_updated_at_is_excluded(self):
        _deal("DEAL-1", status="financing", updated_at="not-a-real-timestamp")
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0


class TestMissingDealJacketSignal:
    """NOTE: every fixture here uses status="funded"/"contract", which also
    lands the same Deal in get_delivery_risk_board()'s no_delivery_scheduled
    bucket (any contract/funded Deal with no matching open delivery
    appointment, regardless of customer_id) -- these tests filter by
    alert_type rather than asserting on the raw feed count/index, so they
    stay isolated from that real, expected cross-signal overlap."""

    def test_funded_deal_with_no_document_is_flagged_yellow(self):
        _deal("DEAL-1", status="funded")
        alerts = oa.get_alert_feed("ADMIN")["alerts"]
        jacket = [a for a in alerts if a["alert_type"] == "missing_deal_jacket"]
        assert len(jacket) == 1
        alert = jacket[0]
        assert alert["severity"] == "yellow"
        assert "DEAL-1" in alert["detail"]
        assert alert["source_id"] == "DEAL-1"
        assert alert["linked_entity_id"] == "DEAL-1"
        assert alert["suggested_action"] == "request_deal_jacket"

    def test_funded_deal_with_a_deal_jacket_document_is_excluded(self):
        _deal("DEAL-1", status="funded")
        _document("DOC-1", EntityType="Deal", EntityID="DEAL-1", DocumentType="Deal Jacket")
        alerts = oa.get_alert_feed("ADMIN")["alerts"]
        jacket = [a for a in alerts if a["alert_type"] == "missing_deal_jacket"]
        assert jacket == []

    def test_funded_deal_with_a_non_jacket_document_still_flagged(self):
        _deal("DEAL-1", status="funded")
        _document("DOC-1", EntityType="Deal", EntityID="DEAL-1", DocumentType="Title")
        alerts = oa.get_alert_feed("ADMIN")["alerts"]
        jacket = [a for a in alerts if a["alert_type"] == "missing_deal_jacket"]
        assert len(jacket) == 1

    def test_non_funded_deal_is_never_flagged(self):
        _deal("DEAL-1", status="contract")
        alerts = oa.get_alert_feed("ADMIN")["alerts"]
        jacket = [a for a in alerts if a["alert_type"] == "missing_deal_jacket"]
        assert jacket == []


class TestOverdueTaskSignal:

    def test_overdue_high_priority_task_is_flagged_red(self):
        # priority="high" -> SLA_HOURS=24; backdated 48 hours -> overdue
        _operations_task(
            "OTASK-1", task_type="custom", detail="Follow up on recall",
            priority="high", created_at=_iso_days_ago(2), linked_entity_id="VEH-9",
        )
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["alert_type"] == "overdue_task"
        assert alert["severity"] == "red"
        assert "custom" in alert["title"]
        assert alert["detail"] == "Follow up on recall"
        assert alert["source_id"] == "OTASK-1"
        assert alert["linked_entity_id"] == "VEH-9"
        assert alert["suggested_action"] == "escalate_task"

    def test_within_sla_task_is_not_flagged(self):
        # priority="normal" -> SLA_HOURS=72; only 1 hour old.
        _operations_task(
            "OTASK-1", task_type="custom", priority="normal",
            created_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        )
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0

    def test_closed_task_is_never_flagged_even_if_old(self):
        _operations_task(
            "OTASK-1", task_type="custom", priority="urgent",
            created_at=_iso_days_ago(30), status="closed",
        )
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0


class TestAtRiskDeliverySignal:

    def test_overdue_delivery_appointment_is_flagged_red(self):
        from core.appointments import create_appointment
        _customer("CUST-1", FirstName="Joe", LastName="King")
        _deal("DEAL-1", status="funded", customer_id="CUST-1", vehicle_id="VEH-1")
        create_appointment(
            department="Sales", appointment_type="delivery", scheduled_start=PAST,
            created_by="EMP-1", customer_id="CUST-1", vehicle_id="VEH-1",
        )
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["alert_type"] == "at_risk_delivery"
        assert alert["severity"] == "red"
        assert alert["title"] == "Delivery overdue"
        assert alert["source_id"] == "DEAL-1"
        assert alert["linked_entity_id"] == "DEAL-1"
        assert alert["suggested_action"] == "schedule_delivery"

    def test_no_delivery_scheduled_is_flagged_yellow(self):
        _customer("CUST-1", FirstName="Joe", LastName="King")
        _deal("DEAL-1", status="contract", customer_id="CUST-1", vehicle_id="VEH-1")
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["alert_type"] == "at_risk_delivery"
        assert alert["severity"] == "yellow"
        assert alert["title"] == "No delivery scheduled"
        assert alert["suggested_action"] == "schedule_delivery"

    def test_on_track_delivery_is_never_flagged(self):
        from core.appointments import create_appointment
        _customer("CUST-1", FirstName="Joe", LastName="King")
        _deal("DEAL-1", status="contract", customer_id="CUST-1", vehicle_id="VEH-1")
        create_appointment(
            department="Sales", appointment_type="delivery", scheduled_start=FUTURE,
            created_by="EMP-1", customer_id="CUST-1", vehicle_id="VEH-1",
        )
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0


class TestCriticalAgingSignal:

    def test_negative_margin_40k_plus_unit_is_flagged_yellow(self):
        _vehicle(
            "VEH-1", Year="2025", Make="Ford", Model="F-150",
            Price="45000", Cost="50000",
        )
        alert = oa.get_alert_feed("ADMIN")["alerts"][0]
        assert alert["alert_type"] == "critical_aging"
        assert alert["severity"] == "yellow"
        assert alert["title"] == "Negative-margin aging unit"
        assert "2025 Ford F-150" in alert["detail"]
        assert alert["source_id"] == "VEH-1"
        assert alert["linked_entity_id"] == "VEH-1"
        assert alert["suggested_action"] == "reduce_price"

    def test_positive_margin_40k_plus_unit_is_not_flagged(self):
        _vehicle(
            "VEH-1", Year="2025", Make="Ford", Model="F-150",
            Price="50000", Cost="40000",
        )
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0

    def test_negative_margin_under_40k_unit_is_not_flagged(self):
        # Below the 40k_plus band -- critical_aging only looks at that one band.
        _vehicle(
            "VEH-1", Year="2020", Make="Kia", Model="Rio",
            Price="12000", Cost="15000",
        )
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 0

    def test_sold_vehicle_is_excluded_regardless_of_margin(self):
        _vehicle(
            "VEH-1", Year="2025", Make="Ford", Model="F-150",
            Price="45000", Cost="50000", DateSold="2026-01-01",
        )
        # DateSold makes get_aging_board() skip this vehicle entirely, but it
        # WOULD still hit the ownership_mismatch check (sold, no PURCHASED rel).
        feed = oa.get_alert_feed("ADMIN")
        types = {a["alert_type"] for a in feed["alerts"]}
        assert "critical_aging" not in types
        assert "ownership_mismatch" in types


class TestSortingAndCounts:

    def test_red_alerts_sort_before_yellow(self):
        _deal("DEAL-1", status="funded")  # missing_deal_jacket -> yellow
        _vehicle("VEH-1", VIN="X", DateSold="2026-01-01")  # ownership_mismatch -> red
        feed = oa.get_alert_feed("ADMIN")
        severities = [a["severity"] for a in feed["alerts"]]
        assert severities == sorted(severities, key=lambda s: {"red": 0, "yellow": 1}[s])
        assert severities[0] == "red"

    def test_red_and_yellow_counts_match_the_alert_list(self):
        # A "funded" Deal fires BOTH missing_deal_jacket AND at_risk_delivery
        # (no_delivery_scheduled) -- 2 real yellow signals from one Deal, a
        # genuine, expected overlap, not a bug in this test.
        _deal("DEAL-1", status="funded")  # 2x yellow
        _vehicle("VEH-1", VIN="X", DateSold="2026-01-01")  # red
        feed = oa.get_alert_feed("ADMIN")
        assert feed["count"] == 3
        assert feed["red_count"] == 1
        assert feed["yellow_count"] == 2
        assert feed["red_count"] + feed["yellow_count"] == feed["count"]


class TestGetAlertStats:

    def test_stats_totals_match_the_feed(self):
        # A "funded" Deal fires both missing_deal_jacket AND at_risk_delivery.
        _deal("DEAL-1", status="funded")  # 2x yellow
        _vehicle("VEH-1", VIN="X", DateSold="2026-01-01")  # red: ownership_mismatch
        stats = oa.get_alert_stats("ADMIN")
        assert stats["total"] == 3
        assert stats["red"] == 1
        assert stats["yellow"] == 2

    def test_stats_by_type_counts_each_alert_type(self):
        _deal("DEAL-1", status="funded")
        _deal("DEAL-2", status="funded")
        _vehicle("VEH-1", VIN="X", DateSold="2026-01-01")
        stats = oa.get_alert_stats("ADMIN")
        assert stats["by_type"] == {
            "missing_deal_jacket": 2,
            "at_risk_delivery": 2,
            "ownership_mismatch": 1,
        }

    def test_stats_empty_ledger(self):
        stats = oa.get_alert_stats("ADMIN")
        assert stats == {"total": 0, "red": 0, "yellow": 0, "by_type": {}}


class TestAcknowledgeAlert:

    @pytest.mark.parametrize("alert_type", [
        "compliance", "missing_deal_jacket", "overdue_task",
        "at_risk_delivery", "critical_aging",
    ])
    def test_types_with_a_dedicated_action_reject_acknowledge(self, alert_type):
        result = oa.acknowledge_alert(alert_type, "SRC-1", "EMP-1")
        assert "error" in result
        assert "dedicated action" in result["error"]

    def test_ownership_mismatch_creates_a_real_operations_task(self):
        result = oa.acknowledge_alert("ownership_mismatch", "VEH-1", "EMP-1", notes="Confirmed on lot")
        assert isinstance(result, Entity)
        assert result.entity_type == "OperationsTask"
        assert result.attributes["task_type"] == "confirm_lot_audit"
        assert result.attributes["owner_bucket"] == "Lot Manager"
        assert result.attributes["priority"] == "high"
        assert result.attributes["created_by"] == "EMP-1"
        assert result.attributes["detail"] == "Confirmed on lot"
        assert result.attributes["linked_entity_id"] == "VEH-1"
        assert result.attributes["source_entity_id"] == "VEH-1"

    def test_stalled_deal_creates_a_real_operations_task(self):
        result = oa.acknowledge_alert("stalled_deal", "DEAL-1", "EMP-1")
        assert result.entity_type == "OperationsTask"
        assert result.attributes["task_type"] == "manager_review"
        assert result.attributes["owner_bucket"] == "Accounting"
        assert result.attributes["priority"] == "high"

    def test_default_notes_mention_the_alert_type_when_none_given(self):
        result = oa.acknowledge_alert("ownership_mismatch", "VEH-1", "EMP-1")
        assert "ownership_mismatch" in result.attributes["detail"]

    def test_acknowledging_twice_for_the_same_source_is_deduped(self):
        first = oa.acknowledge_alert("ownership_mismatch", "VEH-1", "EMP-1")
        assert isinstance(first, Entity)
        second = oa.acknowledge_alert("ownership_mismatch", "VEH-1", "EMP-1")
        assert "error" in second
        assert "already exists" in second["error"]

    def test_dedup_is_scoped_per_alert_type_not_globally(self):
        # A "VEH-1"-sourced ownership_mismatch task shouldn't block a
        # differently-typed "VEH-1"-sourced stalled_deal task (different
        # task_type -> a different _existing_source_ids() bucket).
        oa.acknowledge_alert("ownership_mismatch", "VEH-1", "EMP-1")
        second = oa.acknowledge_alert("stalled_deal", "VEH-1", "EMP-1")
        assert isinstance(second, Entity)

    def test_a_closed_prior_task_does_not_block_reacknowledging(self):
        first = oa.acknowledge_alert("ownership_mismatch", "VEH-1", "EMP-1")
        first.attributes["status"] = "closed"
        second = oa.acknowledge_alert("ownership_mismatch", "VEH-1", "EMP-1")
        assert isinstance(second, Entity)

    def test_unknown_alert_type_also_rejected(self):
        result = oa.acknowledge_alert("not_a_real_type", "SRC-1", "EMP-1")
        assert "error" in result


class TestOperationsAlertsApiRoleGating:

    ALL_ROLES = ("ADMIN", "OPERATIONS", "SALES", "SERVICE", "MARKETING", "FINANCE")

    @pytest.mark.parametrize("role", ["ADMIN", "OPERATIONS", "SALES", "SERVICE", "MARKETING", "FINANCE"])
    def test_get_alert_feed_api_allowed_for_every_view_role(self, role):
        result = oaapi.get_alert_feed_api(role)
        assert "error" not in result

    def test_get_alert_feed_api_denies_an_unknown_role(self):
        result = oaapi.get_alert_feed_api("NOT_A_ROLE")
        assert "error" in result
        assert "Alerts nervous system" in result["error"]

    @pytest.mark.parametrize("role", ["ADMIN", "OPERATIONS", "SALES", "SERVICE", "MARKETING", "FINANCE"])
    def test_get_alert_stats_api_allowed_for_every_view_role(self, role):
        result = oaapi.get_alert_stats_api(role)
        assert "error" not in result

    def test_get_alert_stats_api_denies_an_unknown_role(self):
        result = oaapi.get_alert_stats_api("NOT_A_ROLE")
        assert "error" in result

    @pytest.mark.parametrize("role", ["ADMIN", "OPERATIONS", "SERVICE"])
    def test_acknowledge_alert_api_allowed_for_mutate_roles(self, role):
        result = oaapi.acknowledge_alert_api(role, "EMP-1", "ownership_mismatch", f"VEH-{role}")
        assert isinstance(result, Entity)

    @pytest.mark.parametrize("role", ["SALES", "MARKETING", "FINANCE"])
    def test_acknowledge_alert_api_denies_non_mutate_roles(self, role):
        result = oaapi.acknowledge_alert_api(role, "EMP-1", "ownership_mismatch", "VEH-1")
        assert "error" in result
        assert "Alerts nervous system" in result["error"]

    def test_acknowledge_alert_api_passes_notes_through(self):
        result = oaapi.acknowledge_alert_api("ADMIN", "EMP-1", "ownership_mismatch", "VEH-1", notes="Verified")
        assert result.attributes["detail"] == "Verified"

    def test_acknowledge_alert_api_still_rejects_unsupported_types(self):
        result = oaapi.acknowledge_alert_api("ADMIN", "EMP-1", "compliance", "CMPL-1")
        assert "error" in result
        assert "dedicated action" in result["error"]
