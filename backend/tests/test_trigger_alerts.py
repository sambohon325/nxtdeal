"""
Tests for core/trigger_alerts.py / core/trigger_alerts_api.py -- the AutoAlert /
automotiveMastermind-style Timeline of individually actionable signals (session 84):
5 real scan functions (lease_maturity, service_win_back, equity_mining, recall_open,
conquest_match), a real dedup-on-rescan mechanism, dismiss/promote actions (the
Marketing -> Sales handoff), and trigger_alerts_api.py's own ADMIN/MARKETING/SALES
"can act" gate.

This suite also regression-locks the real customer_id resolution fix made earlier in
this codebase's history (see core/workflow_tab_data.py's _customer_id_by_raw_key()
docstring): FinanceContract.CustomerID is a raw CSV business key, not a resolved
graph CUST- id, and marketing_database_mining() -- which _scan_equity_mining() reuses
directly -- must resolve it by matching against a real Customer's own CustomerID
attribute before creating an alert. TestScanEquityMining's fixtures deliberately give
the Customer entity an `id` that is DIFFERENT from its `CustomerID` attribute, and the
FinanceContract's `CustomerID` attribute is set to the Customer's real CustomerID
value (not its graph id) -- exactly mirroring the real-world CSV-import shape this bug
was found against.

Persistence is patched to a no-op in three separate modules, matching each function's
own real save_graph() call site: core.trigger_alerts itself (run_scan/dismiss_alert/
promote_alert), core.lead_intake (create_lead, called from promote_alert's
Customer-typed path), and core.lead_assignment (assign_lead, called from
promote_alert when assign_to_employee_id is given).

Run from backend/ with `pytest`.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import TRIGGER_ALERT, CUSTOMER, LEAD, VEHICLE, FINANCE_CONTRACT, SERVICE_RECORD, RECALL
from core.relationship_types import GENERATED_LEAD
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import trigger_alerts as trigger_alerts_mod
from core import lead_intake as lead_intake_mod
from core import lead_assignment as lead_assignment_mod

from core.trigger_alerts import (
    ALERT_TYPES,
    _scan_lease_maturity,
    _scan_service_win_back,
    _scan_equity_mining,
    _scan_recall_open,
    _scan_conquest_match,
    run_scan,
    get_alert,
    list_alerts,
    dismiss_alert,
    promote_alert,
)

from core import trigger_alerts_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(trigger_alerts_mod, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lead_intake_mod, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lead_assignment_mod, "save_graph", lambda filepath: None)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _today():
    return datetime.now(timezone.utc).date()


def _customer(customer_id, first="Jane", last="Doe", customer_id_attr=None, **extra):
    attrs = {
        "FirstName": first,
        "LastName": last,
        "Phone": "555-1000",
        "Email": f"{first.lower()}@example.com",
        "City": "Springfield",
        "State": "IL",
        "CustomerID": customer_id_attr if customer_id_attr is not None else customer_id,
    }
    attrs.update(extra)
    entity = Entity(id=customer_id, entity_type=CUSTOMER, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _vehicle(vehicle_id, make="Ford", model="F-150", year="2022", vin=None, **extra):
    attrs = {"Make": make, "Model": model, "Year": year, "VIN": vin or f"VIN{vehicle_id}"}
    attrs.update(extra)
    entity = Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _owns(customer_id, vehicle_id):
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=vehicle_id, relationship_type="OWNS"))


def _finance_contract(contract_id, contract_date=None, term_months=60, customer_id_attr=None, **extra):
    attrs = {
        "ContractDate": (contract_date or _today()).isoformat(),
        "TermMonths": term_months,
        "CustomerID": customer_id_attr,
    }
    attrs.update(extra)
    entity = Entity(id=contract_id, entity_type=FINANCE_CONTRACT, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _financed_by(customer_id, contract_id):
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=contract_id, relationship_type="FINANCED_BY"))


def _service_record(record_id, service_date, **extra):
    attrs = {"ServiceDate": service_date.isoformat() if hasattr(service_date, "isoformat") else service_date}
    attrs.update(extra)
    entity = Entity(id=record_id, entity_type=SERVICE_RECORD, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _authorized(customer_id, record_id):
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=record_id, relationship_type="AUTHORIZED"))


def _recall(recall_id, make="Ford", model="F-150", open_=True, description="Airbag inflator"):
    entity = Entity(
        id=recall_id,
        entity_type=RECALL,
        attributes={"make": make, "model": model, "open": open_, "description": description},
    )
    ledger.add_entity(entity)
    return entity


def _lead(lead_id, first="Sam", last="Prospect", pipeline_state="NEW", **extra):
    attrs = {"FirstName": first, "LastName": last, "PipelineState": pipeline_state, "LeadID": lead_id}
    attrs.update(extra)
    entity = Entity(id=lead_id, entity_type=LEAD, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _interested_in(lead_id, vehicle_id):
    ledger.add_relationship(Relationship(source_id=lead_id, target_id=vehicle_id, relationship_type="INTERESTED_IN"))


# ---------------------------------------------------------------------------
# ALERT_TYPES
# ---------------------------------------------------------------------------

class TestAlertTypes:

    def test_alert_types_covers_all_five_scanners(self):
        assert set(ALERT_TYPES.keys()) == {
            "lease_maturity", "service_win_back", "equity_mining", "recall_open", "conquest_match",
        }


# ---------------------------------------------------------------------------
# _scan_lease_maturity
# ---------------------------------------------------------------------------

class TestScanLeaseMaturity:

    def test_creates_alert_when_maturity_is_within_horizon(self):
        # 60 month term, contracted 58 months ago (in days) -> matures soon
        contract_date = _today() - timedelta(days=58 * 30)
        cust = _customer("CUST-01")
        contract = _finance_contract("FIN-01", contract_date=contract_date, term_months=60)
        _financed_by(cust.id, contract.id)

        created = _scan_lease_maturity(horizon_days=90)

        assert len(created) == 1
        alert = created[0]
        assert alert.attributes["alert_type"] == "lease_maturity"
        assert alert.attributes["target_entity_type"] == CUSTOMER
        assert alert.attributes["target_entity_id"] == cust.id
        assert alert.attributes["source_reference"] == contract.id
        assert alert.attributes["basis"] == "ledger"
        assert alert.attributes["status"] == "new"

    def test_no_alert_when_maturity_is_far_out(self):
        contract_date = _today()
        cust = _customer("CUST-01")
        contract = _finance_contract("FIN-01", contract_date=contract_date, term_months=60)
        _financed_by(cust.id, contract.id)

        created = _scan_lease_maturity(horizon_days=90)

        assert created == []

    def test_no_alert_when_maturity_already_passed(self):
        contract_date = _today() - timedelta(days=61 * 30)
        cust = _customer("CUST-01")
        contract = _finance_contract("FIN-01", contract_date=contract_date, term_months=60)
        _financed_by(cust.id, contract.id)

        created = _scan_lease_maturity(horizon_days=90)

        assert created == []

    def test_urgency_high_within_30_days(self):
        # term matures in ~20 days
        contract_date = _today() - timedelta(days=int(60 * 30 - 20))
        cust = _customer("CUST-01")
        contract = _finance_contract("FIN-01", contract_date=contract_date, term_months=60)
        _financed_by(cust.id, contract.id)

        created = _scan_lease_maturity(horizon_days=90)

        assert len(created) == 1
        assert created[0].attributes["urgency"] == "high"

    def test_missing_term_months_is_skipped(self):
        cust = _customer("CUST-01")
        contract = _finance_contract("FIN-01", contract_date=_today(), term_months=None)
        _financed_by(cust.id, contract.id)

        created = _scan_lease_maturity(horizon_days=90)

        assert created == []

    def test_non_finance_contract_target_of_financed_by_is_ignored(self):
        cust = _customer("CUST-01")
        # a FINANCED_BY relationship pointing at something that isn't a FinanceContract
        not_a_contract = _vehicle("VEH-99")
        _financed_by(cust.id, not_a_contract.id)

        created = _scan_lease_maturity(horizon_days=90)

        assert created == []


# ---------------------------------------------------------------------------
# _scan_service_win_back
# ---------------------------------------------------------------------------

class TestScanServiceWinBack:

    def test_never_serviced_gets_high_urgency_alert(self):
        cust = _customer("CUST-01")

        created = _scan_service_win_back(months_threshold=6)

        assert len(created) == 1
        alert = created[0]
        assert alert.attributes["alert_type"] == "service_win_back"
        assert alert.attributes["urgency"] == "high"
        assert "Never serviced" in alert.attributes["headline"]
        assert alert.attributes["source_reference"] == "service_history"

    def test_recent_service_produces_no_alert(self):
        cust = _customer("CUST-01")
        record = _service_record("SR-01", _today() - timedelta(days=10))
        _authorized(cust.id, record.id)

        created = _scan_service_win_back(months_threshold=6)

        assert created == []

    def test_old_service_over_a_year_gets_high_urgency(self):
        cust = _customer("CUST-01")
        record = _service_record("SR-01", _today() - timedelta(days=400))
        _authorized(cust.id, record.id)

        created = _scan_service_win_back(months_threshold=6)

        assert len(created) == 1
        assert created[0].attributes["urgency"] == "high"

    def test_old_service_under_a_year_gets_medium_urgency(self):
        cust = _customer("CUST-01")
        record = _service_record("SR-01", _today() - timedelta(days=210))
        _authorized(cust.id, record.id)

        created = _scan_service_win_back(months_threshold=6)

        assert len(created) == 1
        assert created[0].attributes["urgency"] == "medium"

    def test_uses_the_most_recent_of_multiple_service_records(self):
        cust = _customer("CUST-01")
        old_record = _service_record("SR-01", _today() - timedelta(days=400))
        recent_record = _service_record("SR-02", _today() - timedelta(days=5))
        _authorized(cust.id, old_record.id)
        _authorized(cust.id, recent_record.id)

        created = _scan_service_win_back(months_threshold=6)

        # the recent record is within the cutoff -> no alert
        assert created == []


# ---------------------------------------------------------------------------
# _scan_equity_mining -- regression-locks the real customer_id resolution fix
# ---------------------------------------------------------------------------

class TestScanEquityMining:

    def test_resolves_raw_csv_customer_id_to_the_real_graph_customer(self):
        """Regression test for the real bug: FinanceContract.CustomerID is a raw CSV
        business key (e.g. "C4077"), not the graph's own CUST- id. The Customer
        entity's graph id is deliberately different from its CustomerID attribute
        here, matching the real-world shape the bug was found against."""

        cust = _customer("CUST-01", customer_id_attr="C4077")
        # term 60% elapsed -> qualifies for marketing_database_mining (>= 50%)
        contract_date = _today() - timedelta(days=int(60 * 30 * 0.65))
        _finance_contract("FIN-01", contract_date=contract_date, term_months=60, customer_id_attr="C4077", AmountFinanced=20000)

        created = _scan_equity_mining()

        assert len(created) == 1
        alert = created[0]
        assert alert.attributes["alert_type"] == "equity_mining"
        assert alert.attributes["target_entity_type"] == CUSTOMER
        # correctly resolved to the real graph id, not the raw "C4077" key
        assert alert.attributes["target_entity_id"] == "CUST-01"
        assert alert.attributes["basis"] == "heuristic"
        assert "HEURISTIC" in alert.attributes["notes"]

    def test_unresolvable_raw_customer_id_creates_no_alert(self):
        """No real Customer anywhere has this CustomerID -- marketing_database_mining()
        falls back to returning the raw key verbatim, which _scan_equity_mining()
        correctly can't resolve to a real Customer entity, so no alert is created."""

        contract_date = _today() - timedelta(days=int(60 * 30 * 0.65))
        _finance_contract("FIN-01", contract_date=contract_date, term_months=60, customer_id_attr="C-UNKNOWN", AmountFinanced=20000)

        created = _scan_equity_mining()

        assert created == []

    def test_urgency_scales_with_pct_term_elapsed(self):
        cust = _customer("CUST-01", customer_id_attr="C1")
        # 80% elapsed -> high urgency
        contract_date = _today() - timedelta(days=int(60 * 30 * 0.80))
        _finance_contract("FIN-01", contract_date=contract_date, term_months=60, customer_id_attr="C1", AmountFinanced=15000)

        created = _scan_equity_mining()

        assert len(created) == 1
        assert created[0].attributes["urgency"] == "high"

    def test_low_pct_elapsed_below_threshold_is_excluded_upstream(self):
        cust = _customer("CUST-01", customer_id_attr="C1")
        # only 20% elapsed -- marketing_database_mining only includes >= 50%
        contract_date = _today() - timedelta(days=int(60 * 30 * 0.20))
        _finance_contract("FIN-01", contract_date=contract_date, term_months=60, customer_id_attr="C1", AmountFinanced=15000)

        created = _scan_equity_mining()

        assert created == []


# ---------------------------------------------------------------------------
# _scan_recall_open
# ---------------------------------------------------------------------------

class TestScanRecallOpen:

    def test_creates_alert_when_owned_vehicle_matches_open_recall(self):
        cust = _customer("CUST-01")
        vehicle = _vehicle("VEH-01", make="Ford", model="F-150", year="2021")
        _owns(cust.id, vehicle.id)
        recall = _recall("REC-01", make="Ford", model="F-150", open_=True)

        created = _scan_recall_open()

        assert len(created) == 1
        alert = created[0]
        assert alert.attributes["alert_type"] == "recall_open"
        assert alert.attributes["urgency"] == "high"
        assert alert.attributes["source_reference"] == recall.id
        assert alert.attributes["vehicle_id"] == vehicle.id

    def test_no_open_recalls_at_all_short_circuits_with_no_alerts(self):
        cust = _customer("CUST-01")
        vehicle = _vehicle("VEH-01", make="Ford", model="F-150")
        _owns(cust.id, vehicle.id)
        _recall("REC-01", make="Ford", model="F-150", open_=False)

        created = _scan_recall_open()

        assert created == []

    def test_no_match_when_make_model_differ(self):
        cust = _customer("CUST-01")
        vehicle = _vehicle("VEH-01", make="Toyota", model="Camry")
        _owns(cust.id, vehicle.id)
        _recall("REC-01", make="Ford", model="F-150", open_=True)

        created = _scan_recall_open()

        assert created == []

    def test_case_insensitive_make_model_match(self):
        cust = _customer("CUST-01")
        vehicle = _vehicle("VEH-01", make="FORD", model="f-150")
        _owns(cust.id, vehicle.id)
        _recall("REC-01", make="ford", model="F-150", open_=True)

        created = _scan_recall_open()

        assert len(created) == 1

    def test_customer_with_no_vehicles_produces_no_alert(self):
        _customer("CUST-01")
        _recall("REC-01", make="Ford", model="F-150", open_=True)

        created = _scan_recall_open()

        assert created == []


# ---------------------------------------------------------------------------
# _scan_conquest_match
# ---------------------------------------------------------------------------

class TestScanConquestMatch:

    def test_creates_alert_for_new_lead_interested_in_a_vehicle(self):
        lead = _lead("LEAD-01", pipeline_state="NEW")
        vehicle = _vehicle("VEH-01")
        _interested_in(lead.id, vehicle.id)

        created = _scan_conquest_match()

        assert len(created) == 1
        alert = created[0]
        assert alert.attributes["alert_type"] == "conquest_match"
        assert alert.attributes["target_entity_type"] == LEAD
        assert alert.attributes["target_entity_id"] == lead.id
        assert alert.attributes["urgency"] == "medium"
        assert alert.attributes["vehicle_id"] == vehicle.id

    def test_creates_alert_for_contacted_lead_too(self):
        lead = _lead("LEAD-01", pipeline_state="CONTACTED")
        vehicle = _vehicle("VEH-01")
        _interested_in(lead.id, vehicle.id)

        created = _scan_conquest_match()

        assert len(created) == 1

    def test_lead_past_contacted_stage_is_excluded(self):
        lead = _lead("LEAD-01", pipeline_state="APPOINTMENT_SET")
        vehicle = _vehicle("VEH-01")
        _interested_in(lead.id, vehicle.id)

        created = _scan_conquest_match()

        assert created == []

    def test_lead_with_no_interested_in_relationship_produces_no_alert(self):
        _lead("LEAD-01", pipeline_state="NEW")

        created = _scan_conquest_match()

        assert created == []


# ---------------------------------------------------------------------------
# run_scan() -- composition + dedup on rescan
# ---------------------------------------------------------------------------

class TestRunScan:

    def test_runs_all_five_scanners_and_returns_combined_list(self):
        cust = _customer("CUST-01")
        # trip service_win_back (never serviced) -- the only signal set up here
        created = run_scan()

        assert len(created) == 1
        assert created[0].attributes["alert_type"] == "service_win_back"

    def test_rescan_does_not_duplicate_an_already_new_alert(self):
        _customer("CUST-01")

        first = run_scan()
        second = run_scan()

        assert len(first) == 1
        assert second == []
        assert len([a for a in list_alerts() if a.attributes["alert_type"] == "service_win_back"]) == 1

    def test_dismissed_alert_key_can_be_reflagged_by_a_fresh_scan(self):
        _customer("CUST-01")

        first = run_scan()
        assert len(first) == 1

        dismiss_alert(first[0].id, "EMP-01")

        second = run_scan()

        # the dismissed alert's own key is a closed decision, but the real underlying
        # signal (never serviced) still holds -- a fresh scan re-flags it
        assert len(second) == 1
        assert second[0].id != first[0].id

    def test_promoted_alert_key_can_be_reflagged_by_a_fresh_scan(self):
        _customer("CUST-01")

        first = run_scan()
        assert len(first) == 1

        promote_alert(first[0].id, "EMP-01")

        second = run_scan()

        assert len(second) == 1
        assert second[0].id != first[0].id

    def test_no_signals_at_all_returns_empty_list(self):
        created = run_scan()
        assert created == []


# ---------------------------------------------------------------------------
# get_alert / list_alerts
# ---------------------------------------------------------------------------

class TestGetAlert:

    def test_returns_none_for_unknown_id(self):
        assert get_alert("ALERT-DOES-NOT-EXIST") is None

    def test_returns_the_real_entity(self):
        _customer("CUST-01")
        created = run_scan()
        alert = get_alert(created[0].id)
        assert alert is not None
        assert alert.id == created[0].id

    def test_returns_none_for_a_non_trigger_alert_entity(self):
        cust = _customer("CUST-01")
        assert get_alert(cust.id) is None


class TestListAlerts:

    def test_filters_by_alert_type(self):
        cust = _customer("CUST-01")
        vehicle = _vehicle("VEH-01", make="Ford", model="F-150")
        _owns(cust.id, vehicle.id)
        _recall("REC-01", make="Ford", model="F-150", open_=True)

        run_scan()

        service_only = list_alerts(alert_type="service_win_back")
        recall_only = list_alerts(alert_type="recall_open")

        assert len(service_only) == 1
        assert len(recall_only) == 1
        assert service_only[0].attributes["alert_type"] == "service_win_back"
        assert recall_only[0].attributes["alert_type"] == "recall_open"

    def test_filters_by_status(self):
        _customer("CUST-01")
        created = run_scan()
        dismiss_alert(created[0].id, "EMP-01")

        new_only = list_alerts(status="new")
        dismissed_only = list_alerts(status="dismissed")

        assert new_only == []
        assert len(dismissed_only) == 1

    def test_filters_by_target_entity_type(self):
        lead = _lead("LEAD-01", pipeline_state="NEW")
        vehicle = _vehicle("VEH-01")
        _interested_in(lead.id, vehicle.id)
        _customer("CUST-02")

        run_scan()

        customer_targets = list_alerts(target_entity_type=CUSTOMER)
        lead_targets = list_alerts(target_entity_type=LEAD)

        assert len(customer_targets) == 1
        assert len(lead_targets) == 1

    def test_sorted_by_urgency_then_created_at(self):
        cust1 = _customer("CUST-01")
        record = _service_record("SR-01", _today() - timedelta(days=210))  # medium urgency
        _authorized(cust1.id, record.id)

        cust2 = _customer("CUST-02")  # never serviced -> high urgency

        alerts = list_alerts()
        run_scan()
        alerts = list_alerts()

        assert len(alerts) == 2
        assert alerts[0].attributes["urgency"] == "high"
        assert alerts[1].attributes["urgency"] == "medium"


# ---------------------------------------------------------------------------
# dismiss_alert
# ---------------------------------------------------------------------------

class TestDismissAlert:

    def test_not_found_returns_error(self):
        result = dismiss_alert("ALERT-NOPE", "EMP-01")
        assert result == {"error": "Alert not found"}

    def test_happy_path_sets_all_the_right_fields(self):
        _customer("CUST-01")
        created = run_scan()
        alert_id = created[0].id

        result = dismiss_alert(alert_id, "EMP-01", notes="not interested")

        assert result.attributes["status"] == "dismissed"
        assert result.attributes["dismissed_by"] == "EMP-01"
        assert result.attributes["dismissed_at"] is not None
        assert result.attributes["dismissal_notes"] == "not interested"
        assert result.attributes["updated_at"] is not None

    def test_already_dismissed_is_rejected(self):
        _customer("CUST-01")
        created = run_scan()
        alert_id = created[0].id

        dismiss_alert(alert_id, "EMP-01")
        result = dismiss_alert(alert_id, "EMP-02")

        assert result == {"error": "Alert is already 'dismissed'"}

    def test_already_promoted_is_rejected(self):
        _customer("CUST-01")
        created = run_scan()
        alert_id = created[0].id

        promote_alert(alert_id, "EMP-01")
        result = dismiss_alert(alert_id, "EMP-02")

        assert result == {"error": "Alert is already 'promoted'"}


# ---------------------------------------------------------------------------
# promote_alert -- the Marketing -> Sales handoff
# ---------------------------------------------------------------------------

class TestPromoteAlert:

    def test_not_found_returns_error(self):
        result = promote_alert("ALERT-NOPE", "EMP-01")
        assert result == {"error": "Alert not found"}

    def test_customer_typed_alert_creates_a_real_lead_with_generated_lead_relationship(self):
        cust = _customer("CUST-01", first="Pat", last="Buyer")
        created = run_scan()
        alert_id = created[0].id

        result = promote_alert(alert_id, "EMP-01")

        assert result.attributes["status"] == "promoted"
        assert result.attributes["promoted_by"] == "EMP-01"
        assert result.attributes["promoted_at"] is not None

        lead_id = result.attributes["promoted_to_lead_id"]
        assert lead_id is not None

        lead = ledger.get_entity(lead_id)
        assert lead.entity_type == LEAD
        assert lead.attributes["FirstName"] == "Pat"
        assert lead.attributes["LastName"] == "Buyer"
        assert lead.attributes["Source"] == "Trigger Alert"

        # a real GENERATED_LEAD relationship ties the new Lead back to the Customer
        gen_rels = [
            r for r in ledger.get_relationships()
            if r.relationship_type == GENERATED_LEAD and r.source_id == cust.id and r.target_id == lead_id
        ]
        assert len(gen_rels) == 1

    def test_customer_typed_alert_with_assign_to_employee_assigns_the_new_lead(self):
        _customer("CUST-01")
        created = run_scan()
        alert_id = created[0].id

        result = promote_alert(alert_id, "EMP-01", assign_to_employee_id="EMP-99")

        lead_id = result.attributes["promoted_to_lead_id"]
        assigned_rels = [
            r for r in ledger.get_relationships()
            if r.relationship_type == "ASSIGNED_TO" and r.target_id == lead_id and r.source_id == "EMP-99"
        ]
        assert len(assigned_rels) == 1

    def test_customer_not_found_returns_error(self):
        cust = _customer("CUST-01")
        created = run_scan()
        alert = created[0]

        # simulate the customer having been removed from the graph after the alert
        # was created, by pointing the alert at a bogus target id directly
        alert.attributes["target_entity_id"] = "CUST-GONE"

        result = promote_alert(alert.id, "EMP-01")

        assert result == {"error": "Customer 'CUST-GONE' not found"}

    def test_lead_typed_conquest_alert_reassigns_without_creating_a_duplicate_lead(self):
        lead = _lead("LEAD-01", pipeline_state="NEW")
        vehicle = _vehicle("VEH-01")
        _interested_in(lead.id, vehicle.id)

        created = run_scan()
        conquest_alerts = [a for a in created if a.attributes["alert_type"] == "conquest_match"]
        assert len(conquest_alerts) == 1
        alert_id = conquest_alerts[0].id

        leads_before = len([e for e in ledger.get_all().values() if e.entity_type == LEAD])

        result = promote_alert(alert_id, "EMP-01", assign_to_employee_id="EMP-99")

        leads_after = len([e for e in ledger.get_all().values() if e.entity_type == LEAD])

        assert leads_after == leads_before  # no new Lead created
        assert result.attributes["promoted_to_lead_id"] == lead.id
        assigned_rels = [
            r for r in ledger.get_relationships()
            if r.relationship_type == "ASSIGNED_TO" and r.target_id == lead.id and r.source_id == "EMP-99"
        ]
        assert len(assigned_rels) == 1

    def test_lead_not_found_returns_error(self):
        lead = _lead("LEAD-01", pipeline_state="NEW")
        vehicle = _vehicle("VEH-01")
        _interested_in(lead.id, vehicle.id)

        created = run_scan()
        alert = created[0]
        alert.attributes["target_entity_id"] = "LEAD-GONE"

        result = promote_alert(alert.id, "EMP-01")

        assert result == {"error": "Lead 'LEAD-GONE' not found"}

    def test_already_promoted_is_rejected(self):
        _customer("CUST-01")
        created = run_scan()
        alert_id = created[0].id

        promote_alert(alert_id, "EMP-01")
        result = promote_alert(alert_id, "EMP-02")

        assert result == {"error": "Alert is already 'promoted'"}

    def test_already_dismissed_is_rejected(self):
        _customer("CUST-01")
        created = run_scan()
        alert_id = created[0].id

        dismiss_alert(alert_id, "EMP-01")
        result = promote_alert(alert_id, "EMP-02")

        assert result == {"error": "Alert is already 'dismissed'"}

    def test_unknown_target_entity_type_is_rejected(self):
        _customer("CUST-01")
        created = run_scan()
        alert = created[0]
        alert.attributes["target_entity_type"] = "Vehicle"

        result = promote_alert(alert.id, "EMP-01")

        assert result == {"error": "Unknown target_entity_type 'Vehicle'"}


# ---------------------------------------------------------------------------
# trigger_alerts_api.py -- ACL layer
# ---------------------------------------------------------------------------

class TestListAlertTypesApi:

    def test_returns_the_real_catalog(self):
        assert trigger_alerts_api.list_alert_types_api() == ALERT_TYPES


class TestGetAlertFeedApi:

    def test_rescans_then_returns_serialized_alerts(self):
        _customer("CUST-01")

        feed = trigger_alerts_api.get_alert_feed_api(SALES)

        assert len(feed) == 1
        assert feed[0]["alert_type"] == "service_win_back"
        assert "id" in feed[0]

    def test_open_to_every_real_role_read_only(self):
        _customer("CUST-01")

        for role in (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            feed = trigger_alerts_api.get_alert_feed_api(role)
            assert len(feed) == 1

    def test_filters_pass_through(self):
        cust = _customer("CUST-01")
        vehicle = _vehicle("VEH-01", make="Ford", model="F-150")
        _owns(cust.id, vehicle.id)
        _recall("REC-01", make="Ford", model="F-150", open_=True)

        feed = trigger_alerts_api.get_alert_feed_api(ADMIN, alert_type="recall_open")

        assert len(feed) == 1
        assert feed[0]["alert_type"] == "recall_open"


class TestGetAlertApi:

    def test_not_found_returns_error(self):
        result = trigger_alerts_api.get_alert_api(ADMIN, "ALERT-NOPE")
        assert result == {"error": "Alert not found"}

    def test_returns_serialized_alert(self):
        _customer("CUST-01")
        created = run_scan()

        result = trigger_alerts_api.get_alert_api(ADMIN, created[0].id)

        assert result["id"] == created[0].id
        assert result["alert_type"] == "service_win_back"


class TestDismissAlertApi:

    def test_denies_a_role_outside_admin_marketing_sales(self):
        _customer("CUST-01")
        created = run_scan()

        for role in (OPERATIONS, SERVICE, FINANCE):
            result = trigger_alerts_api.dismiss_alert_api(role, "EMP-01", created[0].id)
            assert result == {"error": "Only admin/marketing/sales can dismiss a trigger alert"}

    def test_allows_admin_marketing_sales(self):
        for role in (ADMIN, MARKETING, SALES):
            ledger.reset()
            _customer("CUST-01")
            created = run_scan()

            result = trigger_alerts_api.dismiss_alert_api(role, "EMP-01", created[0].id)

            assert result["status"] == "dismissed"

    def test_propagates_a_real_not_found_error(self):
        result = trigger_alerts_api.dismiss_alert_api(ADMIN, "EMP-01", "ALERT-NOPE")
        assert result == {"error": "Alert not found"}


class TestPromoteAlertApi:

    def test_denies_a_role_outside_admin_marketing_sales(self):
        _customer("CUST-01")
        created = run_scan()

        for role in (OPERATIONS, SERVICE, FINANCE):
            result = trigger_alerts_api.promote_alert_api(role, "EMP-01", created[0].id)
            assert result == {"error": "Only admin/marketing/sales can promote a trigger alert"}

    def test_allows_admin_marketing_sales(self):
        for role in (ADMIN, MARKETING, SALES):
            ledger.reset()
            _customer("CUST-01")
            created = run_scan()

            result = trigger_alerts_api.promote_alert_api(role, "EMP-01", created[0].id)

            assert result["status"] == "promoted"
            assert result["promoted_to_lead_id"] is not None

    def test_propagates_assign_to_employee_id(self):
        _customer("CUST-01")
        created = run_scan()

        result = trigger_alerts_api.promote_alert_api(ADMIN, "EMP-01", created[0].id, assign_to_employee_id="EMP-99")

        lead_id = result["promoted_to_lead_id"]
        assigned_rels = [
            r for r in ledger.get_relationships()
            if r.relationship_type == "ASSIGNED_TO" and r.target_id == lead_id and r.source_id == "EMP-99"
        ]
        assert len(assigned_rels) == 1

    def test_propagates_a_real_not_found_error(self):
        result = trigger_alerts_api.promote_alert_api(ADMIN, "EMP-01", "ALERT-NOPE")
        assert result == {"error": "Alert not found"}
