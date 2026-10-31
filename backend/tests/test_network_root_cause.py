"""
Tests for core/network_root_cause.py -- the real, threshold-based diagnostic
catalog behind Network's Gap Analysis "Likely Causes" feature. Added per
BUILD_QUEUE.md's standing "convert to a real pytest suite as each module gets
touched" rule (CAF-00123 missing_test_coverage work).

Every diagnostic reuses an already-built engine elsewhere in this codebase
(core.bdc, core.follow_up_dashboard, core.appointments, core.shop_control,
core.repair_orders, core.parts_desk, core.fi_products, core.collections) --
every one of those is mocked here rather than exercised for real, matching
this module's own "never a fabricated cause" discipline: these tests confirm
the THRESHOLD LOGIC (does a given real signal correctly trigger/not trigger a
finding), not the upstream engines themselves (each of which has, or will
have, its own dedicated coverage).

Two real, non-obvious import shapes this module has, both confirmed by direct
source read before writing any test:

  1. get_response_time_stats/get_untouched_queue (core.bdc),
     get_follow_up_dashboard (core.follow_up_dashboard), list_appointments
     (core.appointments), get_technician_utilization/get_stalled_ros
     (core.shop_control), and _stage_of (core.repair_orders) are all
     MODULE-LEVEL imports -- directly monkeypatchable via
     monkeypatch.setattr(nrc, "name", fake).

  2. get_inventory_recommendations (core.parts_desk),
     list_deals_needing_fi_menu (core.fi_products), and
     get_collection_queue/_broken_promises_count (core.collections) are all
     DEFERRED (in-function) imports -- must be patched via the string-target
     form (monkeypatch.setattr("core.parts_desk.get_inventory_recommendations",
     fake), etc.), per this codebase's established deferred-import testing
     convention.

`ledger` itself (from core.dealeros) is ALSO a module-level import in
network_root_cause.py, used directly by two diagnostics
(_diag_low_dvi_completion, _diag_unworked_delinquent_accounts). Rather than
build real graph entities, this file monkeypatches nrc.ledger to a tiny fake
stub exposing only the two methods those diagnostics actually call
(get_all()/get_entity()) -- no ledger/graph fixture needed at all.

Important gotcha specific to this module's get_root_causes() tests:
_ROOT_CAUSE_MAP is built ONCE, at import time, with direct references to the
real _diag_* function OBJECTS -- monkeypatching nrc._diag_slow_lead_response
(etc.) afterward has NO effect on what _ROOT_CAUSE_MAP's already-bound list
actually calls, since a dict's stored values don't follow a later module-
attribute reassignment. get_root_causes()-level tests therefore monkeypatch
_ROOT_CAUSE_MAP itself with small, controlled fake diagnostic callables,
rather than trying to patch the real diagnostics' own dependencies for every
(department, kpi_key) pair.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import core.network_root_cause as nrc
from core.network_root_cause import (
    _diag_slow_lead_response,
    _diag_untouched_leads,
    _diag_follow_up_compliance,
    _diag_low_reminder_usage_sales,
    _diag_low_sms_utilization_sales,
    _diag_low_reminder_usage_service,
    _diag_technician_overload,
    _diag_low_dvi_completion,
    _diag_stalled_ros,
    _diag_parts_understocked,
    _diag_fi_menu_not_presented,
    _diag_unworked_delinquent_accounts,
    _diag_broken_promises,
    get_root_causes,
    _NO_DIAGNOSTIC_NOTE,
    _CLEAN_CHECK_NOTE,
)
from core.entity_types import SERVICE_RECORD, FINANCE_CONTRACT


# ---------------------------------------------------------------------------
# Fake ledger stub -- covers the two diagnostics that touch nrc.ledger
# directly (_diag_low_dvi_completion, _diag_unworked_delinquent_accounts).
# ---------------------------------------------------------------------------

class _FakeEntity:
    def __init__(self, entity_id, entity_type, attributes=None):
        self.id = entity_id
        self.entity_type = entity_type
        self.attributes = attributes or {}


class _FakeLedger:
    def __init__(self, entities=None):
        self._entities = {e.id: e for e in (entities or [])}

    def get_all(self):
        return dict(self._entities)

    def get_entity(self, entity_id):
        return self._entities.get(entity_id)


# ---------------------------------------------------------------------------
# Sales diagnostics
# ---------------------------------------------------------------------------

class TestDiagSlowLeadResponse:
    def test_missing_average_returns_none(self, monkeypatch):
        monkeypatch.setattr(nrc, "get_response_time_stats", lambda: {"average_minutes": None, "sample_size": 10})
        assert _diag_slow_lead_response() is None

    def test_sample_too_small_returns_none(self, monkeypatch):
        monkeypatch.setattr(nrc, "get_response_time_stats", lambda: {"average_minutes": 90.0, "sample_size": 2, "under_target_pct": 10.0})
        assert _diag_slow_lead_response() is None

    def test_high_average_triggers(self, monkeypatch):
        monkeypatch.setattr(nrc, "get_response_time_stats", lambda: {"average_minutes": 75.0, "sample_size": 20, "under_target_pct": 60.0})
        result = _diag_slow_lead_response()
        assert result["key"] == "slow_lead_response"
        assert result["basis"] == "real"
        assert "75.0" in result["finding"]

    def test_low_under_target_pct_triggers_even_with_ok_average(self, monkeypatch):
        monkeypatch.setattr(nrc, "get_response_time_stats", lambda: {"average_minutes": 40.0, "sample_size": 20, "under_target_pct": 20.0})
        assert _diag_slow_lead_response() is not None

    def test_healthy_response_time_returns_none(self, monkeypatch):
        monkeypatch.setattr(nrc, "get_response_time_stats", lambda: {"average_minutes": 15.0, "sample_size": 20, "under_target_pct": 80.0})
        assert _diag_slow_lead_response() is None


class TestDiagUntouchedLeads:
    def test_below_threshold_returns_none(self, monkeypatch):
        monkeypatch.setattr(nrc, "get_untouched_queue", lambda: list(range(5)))
        assert _diag_untouched_leads() is None

    def test_at_threshold_triggers(self, monkeypatch):
        monkeypatch.setattr(nrc, "get_untouched_queue", lambda: list(range(10)))
        result = _diag_untouched_leads()
        assert result["key"] == "untouched_lead_backlog"
        assert result["supporting_data"]["untouched_count"] == 10


class TestDiagFollowUpCompliance:
    def test_sample_too_small_returns_none(self, monkeypatch):
        monkeypatch.setattr(nrc, "get_follow_up_dashboard", lambda: [{"days_in_state": 5}] * 5)
        assert _diag_follow_up_compliance() is None

    def test_low_stale_pct_returns_none(self, monkeypatch):
        queue = [{"days_in_state": 1} for _ in range(9)] + [{"days_in_state": 5}]
        monkeypatch.setattr(nrc, "get_follow_up_dashboard", lambda: queue)
        assert _diag_follow_up_compliance() is None

    def test_high_stale_pct_triggers(self, monkeypatch):
        queue = [{"days_in_state": 5} for _ in range(4)] + [{"days_in_state": 1} for _ in range(6)]
        monkeypatch.setattr(nrc, "get_follow_up_dashboard", lambda: queue)
        result = _diag_follow_up_compliance()
        assert result["key"] == "poor_follow_up_compliance"
        assert result["supporting_data"]["stale_count"] == 4
        assert result["supporting_data"]["total_open_leads"] == 10


# ---------------------------------------------------------------------------
# Reminder-usage diagnostics (shared by Sales close_rate/show_rate and
# Service ro_count)
# ---------------------------------------------------------------------------

def _appt(reminders=None):
    return _FakeEntity("APPT-x", "APPOINTMENT", {"reminders_sent": reminders or []})


class TestReminderUsageDiagnostics:
    def test_sample_too_small_returns_none_for_both(self, monkeypatch):
        monkeypatch.setattr(nrc, "list_appointments", lambda department=None: [_appt() for _ in range(4)])
        assert _diag_low_reminder_usage_sales() is None
        assert _diag_low_sms_utilization_sales() is None

    def test_healthy_reminder_usage_returns_none(self, monkeypatch):
        # 5 appts, 3 with any reminder (60% >= 40% threshold), 2 with sms (40% >= 25%)
        appts = [
            _appt([{"channel": "email"}]),
            _appt([{"channel": "sms"}]),
            _appt([{"channel": "sms"}]),
            _appt([]),
            _appt([]),
        ]
        monkeypatch.setattr(nrc, "list_appointments", lambda department=None: appts)
        assert _diag_low_reminder_usage_sales() is None
        assert _diag_low_sms_utilization_sales() is None

    def test_low_any_reminder_usage_triggers(self, monkeypatch):
        # 5 appts, only 1 with any reminder (20% < 40%)
        appts = [_appt([{"channel": "email"}])] + [_appt([]) for _ in range(4)]
        monkeypatch.setattr(nrc, "list_appointments", lambda department=None: appts)
        result = _diag_low_reminder_usage_sales()
        assert result["key"] == "low_appointment_reminder_usage"
        assert result["basis"] == "real_staff_action_count"
        assert result["supporting_data"]["pct_any_reminder"] == 20.0

    def test_low_sms_usage_triggers_even_when_any_reminder_usage_is_healthy(self, monkeypatch):
        # 5 appts, 3 with any reminder (60%, healthy) but 0 via sms specifically (0% < 25%)
        appts = [_appt([{"channel": "email"}]) for _ in range(3)] + [_appt([]) for _ in range(2)]
        monkeypatch.setattr(nrc, "list_appointments", lambda department=None: appts)
        assert _diag_low_reminder_usage_sales() is None
        result = _diag_low_sms_utilization_sales()
        assert result["key"] == "low_sms_utilization"
        assert result["supporting_data"]["pct_sms_reminder"] == 0.0
        assert result["supporting_data"]["pct_any_reminder"] == 60.0

    def test_department_specific_wrappers_pass_the_right_department(self, monkeypatch):
        seen = {}

        def _fake_list(department=None):
            seen["department"] = department
            return [_appt() for _ in range(5)]

        monkeypatch.setattr(nrc, "list_appointments", _fake_list)

        _diag_low_reminder_usage_sales()
        assert seen["department"] == "Sales"

        _diag_low_reminder_usage_service()
        assert seen["department"] == "Service"


# ---------------------------------------------------------------------------
# Service diagnostics
# ---------------------------------------------------------------------------

class TestDiagTechnicianOverload:
    def test_sample_too_small_returns_none(self, monkeypatch):
        util = {"technicians": [{"utilization_pct": 150.0, "overloaded": True, "assumed_capacity_hours": 8}]}
        monkeypatch.setattr(nrc, "get_technician_utilization", lambda: util)
        assert _diag_technician_overload() is None

    def test_healthy_utilization_returns_none(self, monkeypatch):
        util = {"technicians": [
            {"utilization_pct": 50.0, "overloaded": False, "assumed_capacity_hours": 8},
            {"utilization_pct": 60.0, "overloaded": False, "assumed_capacity_hours": 8},
        ]}
        monkeypatch.setattr(nrc, "get_technician_utilization", lambda: util)
        assert _diag_technician_overload() is None

    def test_high_average_utilization_triggers(self, monkeypatch):
        util = {"technicians": [
            {"utilization_pct": 130.0, "overloaded": True, "assumed_capacity_hours": 8},
            {"utilization_pct": 110.0, "overloaded": True, "assumed_capacity_hours": 8},
        ]}
        monkeypatch.setattr(nrc, "get_technician_utilization", lambda: util)
        result = _diag_technician_overload()
        assert result["key"] == "technician_overcapacity"
        assert result["supporting_data"]["technician_count"] == 2

    def test_half_or_more_overloaded_triggers_even_with_ok_average(self, monkeypatch):
        util = {"technicians": [
            {"utilization_pct": 40.0, "overloaded": False, "assumed_capacity_hours": 8},
            {"utilization_pct": 40.0, "overloaded": False, "assumed_capacity_hours": 8},
            {"utilization_pct": 105.0, "overloaded": True, "assumed_capacity_hours": 8},
        ]}
        # avg = (40+40+105)/3 = 61.67 (not > 100), but 1 of 3 overloaded (>= max(1, 3//2)=1) -> triggers
        monkeypatch.setattr(nrc, "get_technician_utilization", lambda: util)
        assert _diag_technician_overload() is not None


class TestDiagLowDviCompletion:
    def _fake_stage_of(self, entity):
        return entity.attributes.get("_test_stage", "Follow-Up")

    def test_sample_too_small_returns_none(self, monkeypatch):
        monkeypatch.setattr(nrc, "_stage_of", self._fake_stage_of)
        entities = [
            _FakeEntity(f"SRV-{i}", SERVICE_RECORD, {"_test_stage": "Repair", "dvi": {"status": "completed"}})
            for i in range(3)
        ]
        monkeypatch.setattr(nrc, "ledger", _FakeLedger(entities))
        assert _diag_low_dvi_completion() is None

    def test_non_live_records_excluded_from_denominator(self, monkeypatch):
        monkeypatch.setattr(nrc, "_stage_of", self._fake_stage_of)
        live_low_dvi = [
            _FakeEntity(f"SRV-live-{i}", SERVICE_RECORD, {"_test_stage": "Repair", "dvi": {}})
            for i in range(5)
        ]
        follow_up = [
            _FakeEntity(f"SRV-fu-{i}", SERVICE_RECORD, {"_test_stage": "Follow-Up", "dvi": {"status": "completed"}})
            for i in range(20)
        ]
        monkeypatch.setattr(nrc, "ledger", _FakeLedger(live_low_dvi + follow_up))

        result = _diag_low_dvi_completion()
        # Only the 5 live records count -- the 20 Follow-Up (historical) records
        # are correctly excluded even though they'd make the pct look great.
        assert result["supporting_data"]["live_ro_count"] == 5
        assert result["supporting_data"]["pct_completed"] == 0.0

    def test_non_service_record_entities_are_ignored(self, monkeypatch):
        monkeypatch.setattr(nrc, "_stage_of", self._fake_stage_of)
        entities = [
            _FakeEntity(f"SRV-{i}", SERVICE_RECORD, {"_test_stage": "Repair", "dvi": {}})
            for i in range(5)
        ] + [
            _FakeEntity(f"VEH-{i}", "VEHICLE", {"_test_stage": "Repair"})
            for i in range(20)
        ]
        monkeypatch.setattr(nrc, "ledger", _FakeLedger(entities))
        result = _diag_low_dvi_completion()
        assert result["supporting_data"]["live_ro_count"] == 5

    def test_low_completion_pct_triggers(self, monkeypatch):
        monkeypatch.setattr(nrc, "_stage_of", self._fake_stage_of)
        entities = (
            [_FakeEntity(f"SRV-c-{i}", SERVICE_RECORD, {"_test_stage": "Repair", "dvi": {"status": "completed"}}) for i in range(1)]
            + [_FakeEntity(f"SRV-p-{i}", SERVICE_RECORD, {"_test_stage": "Repair", "dvi": {"status": "in_progress"}}) for i in range(1)]
            + [_FakeEntity(f"SRV-n-{i}", SERVICE_RECORD, {"_test_stage": "Repair", "dvi": {}}) for i in range(4)]
        )
        monkeypatch.setattr(nrc, "ledger", _FakeLedger(entities))
        result = _diag_low_dvi_completion()
        assert result["key"] == "low_dvi_completion"
        assert result["supporting_data"]["live_ro_count"] == 6
        assert result["supporting_data"]["started_count"] == 2
        assert result["supporting_data"]["completed_count"] == 1
        assert result["supporting_data"]["pct_completed"] == round(100 * 1 / 6, 1)

    def test_healthy_completion_pct_returns_none(self, monkeypatch):
        monkeypatch.setattr(nrc, "_stage_of", self._fake_stage_of)
        entities = [
            _FakeEntity(f"SRV-c-{i}", SERVICE_RECORD, {"_test_stage": "Repair", "dvi": {"status": "completed"}})
            for i in range(5)
        ]
        monkeypatch.setattr(nrc, "ledger", _FakeLedger(entities))
        assert _diag_low_dvi_completion() is None


class TestDiagStalledRos:
    def test_zero_count_returns_none(self, monkeypatch):
        monkeypatch.setattr(nrc, "get_stalled_ros", lambda: {"count": 0, "hours_threshold": 9})
        assert _diag_stalled_ros() is None

    def test_positive_count_triggers(self, monkeypatch):
        monkeypatch.setattr(nrc, "get_stalled_ros", lambda: {"count": 3, "hours_threshold": 9})
        result = _diag_stalled_ros()
        assert result["key"] == "stalled_repair_orders"
        assert result["supporting_data"] == {"stalled_count": 3, "hours_threshold": 9}


# ---------------------------------------------------------------------------
# Parts / F&I diagnostics (deferred imports)
# ---------------------------------------------------------------------------

class TestDiagPartsUnderstocked:
    def test_zero_count_returns_none(self, monkeypatch):
        monkeypatch.setattr("core.parts_desk.get_inventory_recommendations", lambda limit=1000: {"count": 0})
        assert _diag_parts_understocked() is None

    def test_positive_count_triggers(self, monkeypatch):
        monkeypatch.setattr("core.parts_desk.get_inventory_recommendations", lambda limit=1000: {"count": 19})
        result = _diag_parts_understocked()
        assert result["key"] == "understocked_fast_moving_parts"
        assert result["supporting_data"]["understocked_part_count"] == 19


class TestDiagFiMenuNotPresented:
    def test_empty_list_returns_none(self, monkeypatch):
        monkeypatch.setattr("core.fi_products.list_deals_needing_fi_menu", lambda limit=1000: [])
        assert _diag_fi_menu_not_presented() is None

    def test_non_empty_list_triggers(self, monkeypatch):
        monkeypatch.setattr("core.fi_products.list_deals_needing_fi_menu", lambda limit=1000: [{"deal_id": "DEAL-1"}, {"deal_id": "DEAL-2"}])
        result = _diag_fi_menu_not_presented()
        assert result["key"] == "fi_menu_not_presented"
        assert result["supporting_data"]["deals_missing_menu"] == 2


# ---------------------------------------------------------------------------
# BHPH / collections diagnostics (deferred imports + fake ledger)
# ---------------------------------------------------------------------------

class TestDiagUnworkedDelinquentAccounts:
    def test_sample_too_small_returns_none(self, monkeypatch):
        monkeypatch.setattr("core.collections.get_collection_queue", lambda: {"loans": [{"loan_id": f"FIN-{i}"} for i in range(3)]})
        monkeypatch.setattr(nrc, "ledger", _FakeLedger([]))
        assert _diag_unworked_delinquent_accounts() is None

    def test_high_unworked_pct_triggers(self, monkeypatch):
        loans = [{"loan_id": f"FIN-{i}"} for i in range(6)]
        monkeypatch.setattr("core.collections.get_collection_queue", lambda: {"loans": loans})
        # 3 have no collection_stage (unworked), 3 have one (worked) -> 50% == threshold, triggers
        entities = (
            [_FakeEntity(f"FIN-{i}", FINANCE_CONTRACT, {}) for i in range(3)]
            + [_FakeEntity(f"FIN-{i}", FINANCE_CONTRACT, {"collection_stage": "friendly_reminder"}) for i in range(3, 6)]
        )
        monkeypatch.setattr(nrc, "ledger", _FakeLedger(entities))
        result = _diag_unworked_delinquent_accounts()
        assert result["key"] == "unworked_delinquent_accounts"
        assert result["supporting_data"]["unworked_count"] == 3
        assert result["supporting_data"]["pct_unworked"] == 50.0

    def test_low_unworked_pct_returns_none(self, monkeypatch):
        loans = [{"loan_id": f"FIN-{i}"} for i in range(6)]
        monkeypatch.setattr("core.collections.get_collection_queue", lambda: {"loans": loans})
        entities = [_FakeEntity(f"FIN-{i}", FINANCE_CONTRACT, {"collection_stage": "demand_notice"}) for i in range(6)]
        monkeypatch.setattr(nrc, "ledger", _FakeLedger(entities))
        assert _diag_unworked_delinquent_accounts() is None

    def test_loan_missing_from_ledger_is_not_counted_as_unworked(self, monkeypatch):
        loans = [{"loan_id": f"FIN-{i}"} for i in range(6)]
        monkeypatch.setattr("core.collections.get_collection_queue", lambda: {"loans": loans})
        # Every loan is genuinely missing from the ledger (never persisted /
        # a stale queue reference) -- the `if loan and ...` guard means these
        # are NOT counted toward unworked at all.
        monkeypatch.setattr(nrc, "ledger", _FakeLedger([]))
        result = _diag_unworked_delinquent_accounts()
        assert result is None


class TestDiagBrokenPromises:
    def test_sample_too_small_returns_none(self, monkeypatch):
        monkeypatch.setattr("core.collections.get_collection_queue", lambda: {"loans": [{"loan_id": f"FIN-{i}"} for i in range(2)]})
        monkeypatch.setattr("core.collections._broken_promises_count", lambda loan_id: 1)
        assert _diag_broken_promises() is None

    def test_zero_broken_promises_returns_none(self, monkeypatch):
        loans = [{"loan_id": f"FIN-{i}"} for i in range(5)]
        monkeypatch.setattr("core.collections.get_collection_queue", lambda: {"loans": loans})
        monkeypatch.setattr("core.collections._broken_promises_count", lambda loan_id: 0)
        assert _diag_broken_promises() is None

    def test_positive_broken_promises_triggers(self, monkeypatch):
        loans = [{"loan_id": f"FIN-{i}"} for i in range(5)]
        monkeypatch.setattr("core.collections.get_collection_queue", lambda: {"loans": loans})
        monkeypatch.setattr("core.collections._broken_promises_count", lambda loan_id: 1 if loan_id in ("FIN-0", "FIN-1") else 0)
        result = _diag_broken_promises()
        assert result["key"] == "broken_promises_to_pay"
        assert result["supporting_data"]["broken_promise_loan_count"] == 2
        assert result["supporting_data"]["delinquent_loan_count"] == 5


# ---------------------------------------------------------------------------
# get_root_causes() -- the (department, kpi_key) -> catalog dispatch
# ---------------------------------------------------------------------------

def _fake_diag_returns(payload):
    return lambda: payload


class TestGetRootCauses:
    def test_executive_department_gets_the_special_rollup_note(self):
        result = get_root_causes("executive", "total_gross_profit_contribution_pct", kpi_label="Total Gross Profit Contribution")
        assert result["causes"] == []
        assert result["diagnostics_available"] is False
        assert "Total Gross Profit Contribution" in result["note"]
        assert "Sales/Service/Parts/F&I" in result["note"]

    def test_unmapped_department_kpi_pair_gets_honest_no_diagnostic_note(self, monkeypatch):
        monkeypatch.setattr(nrc, "_ROOT_CAUSE_MAP", {})
        result = get_root_causes("sales", "some_kpi_with_no_mapping")
        assert result == {"causes": [], "diagnostics_available": False, "note": _NO_DIAGNOSTIC_NOTE}

    def test_mapped_pair_with_empty_checks_list_gets_no_diagnostic_note(self, monkeypatch):
        monkeypatch.setattr(nrc, "_ROOT_CAUSE_MAP", {("sales", "avg_sale_price"): []})
        result = get_root_causes("sales", "avg_sale_price")
        assert result["diagnostics_available"] is False
        assert result["note"] == _NO_DIAGNOSTIC_NOTE

    def test_mapped_pair_with_all_diagnostics_clean_gets_clean_check_note(self, monkeypatch):
        monkeypatch.setattr(nrc, "_ROOT_CAUSE_MAP", {
            ("sales", "close_rate"): [_fake_diag_returns(None), _fake_diag_returns(None)],
        })
        result = get_root_causes("sales", "close_rate")
        assert result["causes"] == []
        assert result["diagnostics_available"] is True
        assert result["note"] == _CLEAN_CHECK_NOTE

    def test_mapped_pair_with_real_findings_populates_causes(self, monkeypatch):
        finding_a = {"key": "slow_lead_response", "label": "Slow Lead Response", "finding": "...", "basis": "real"}
        finding_b = {"key": "untouched_lead_backlog", "label": "Untouched Lead Backlog", "finding": "...", "basis": "real"}
        monkeypatch.setattr(nrc, "_ROOT_CAUSE_MAP", {
            ("sales", "close_rate"): [_fake_diag_returns(finding_a), _fake_diag_returns(None), _fake_diag_returns(finding_b)],
        })
        result = get_root_causes("sales", "close_rate")
        assert result["causes"] == [finding_a, finding_b]
        assert result["diagnostics_available"] is True
        assert result["note"] is None
