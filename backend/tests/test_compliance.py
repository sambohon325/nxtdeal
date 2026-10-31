"""
Tests for the compliance agent (core/compliance_rules.py, core/compliance.py,
core/compliance_api.py, core/compliance_scheduler.py) -- session 38. Run from
backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import date

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import (
    DEAL, CAMPAIGN, ASSET, WEBSITE, CONNECTION, CUSTOMER, EMPLOYEE
)
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING

from core.auth import credential_store

from core import compliance
from core import compliance_api
from core import compliance_scheduler


TODAY = date.today().isoformat()


@pytest.fixture(autouse=True)
def fresh_state():

    ledger.reset()
    credential_store.reset()

    yield

    ledger.reset()
    credential_store.reset()


def _complete_customer(customer_id="CUST-00001"):

    ledger.add_entity(Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={
            "FirstName": "Jane",
            "LastName": "Doe",
            "Address": "123 Main St",
            "City": "Springfield",
            "State": "IL",
            "Zip": "62701",
            "Phone": "555-1234",
        },
    ))

    return customer_id


def _funded_deal(deal_id="DEAL-00001", customer_id="CUST-00001", complete_contract=True):

    contract = {
        "apr": 5.9,
        "amount_financed": 25000,
        "monthly_payment": 450,
        "term_months": 60,
        "disclosures": ["Standard TILA disclosure."],
    } if complete_contract else {}

    ledger.add_entity(Entity(
        id=deal_id,
        entity_type=DEAL,
        attributes={
            "customer_id": customer_id,
            "status": "contract",
            "contract": contract,
            "financing_status": "approved",
            "ofac_screening": {"screened": True, "cleared": True, "screened_by": "TEST-REVIEWER"},
        },
    ))

    return ledger.get_entity(deal_id)


# ---------------------------------------------------------------------------
# Rule checks
# ---------------------------------------------------------------------------

def test_reg_z_passes_on_complete_contract():

    _complete_customer()
    deal = _funded_deal()

    result = compliance.evaluate("deal_fund", deal)

    assert result["passed"] is True
    assert result["violations"] == []


def test_reg_z_fails_on_missing_contract():

    _complete_customer()
    deal = _funded_deal(complete_contract=False)

    result = compliance.evaluate("deal_fund", deal)

    assert result["passed"] is False
    assert any(v["rule_id"] == "reg_z_disclosure" for v in result["violations"])


def test_red_flags_fails_on_incomplete_customer():

    ledger.add_entity(Entity(
        id="CUST-00002",
        entity_type=CUSTOMER,
        attributes={"FirstName": "Incomplete"},
    ))

    deal = _funded_deal(deal_id="DEAL-00002", customer_id="CUST-00002")

    result = compliance.evaluate("deal_fund", deal)

    assert result["passed"] is False
    assert any(v["rule_id"] == "red_flags_identity" for v in result["violations"])


def test_ecoa_fails_on_undocumented_decline():

    deal = Entity(
        id="DEAL-00003",
        entity_type=DEAL,
        attributes={"financing_status": "declined", "financing_notes": None},
    )

    result = compliance.evaluate("deal_decline", deal)

    assert result["passed"] is False
    assert result["violations"][0]["rule_id"] == "ecoa_adverse_action"


def test_ecoa_passes_with_documented_reason():

    deal = Entity(
        id="DEAL-00004",
        entity_type=DEAL,
        attributes={"financing_status": "declined", "financing_notes": "Insufficient income"},
    )

    result = compliance.evaluate("deal_decline", deal)

    assert result["passed"] is True


def test_can_spam_flags_do_not_contact_member():

    ledger.add_entity(Entity(
        id="CUST-00003",
        entity_type=CUSTOMER,
        attributes={"DoNotContact": True},
    ))

    campaign = Entity(
        id="CAMP-00001",
        entity_type=CAMPAIGN,
        attributes={"audience_ids": ["CUST-00003"]},
    )

    result = compliance.evaluate("campaign_activate", campaign)

    assert result["passed"] is False
    assert result["violations"][0]["rule_id"] == "can_spam_tcpa_consent"


def test_can_spam_passes_with_no_opt_outs():

    ledger.add_entity(Entity(id="CUST-00004", entity_type=CUSTOMER, attributes={}))

    campaign = Entity(
        id="CAMP-00002",
        entity_type=CAMPAIGN,
        attributes={"audience_ids": ["CUST-00004"]},
    )

    result = compliance.evaluate("campaign_activate", campaign)

    assert result["passed"] is True


def test_glba_flags_unencrypted_api_endpoint():

    connection = Entity(
        id="CONN-00001",
        entity_type=CONNECTION,
        attributes={"connection_type": "api", "endpoint_url": "http://insecure.example.com"},
    )

    result = compliance.evaluate("connection_create", connection)

    assert result["passed"] is False
    assert result["violations"][0]["rule_id"] == "glba_safeguards_encryption"


def test_glba_passes_with_https_endpoint():

    connection = Entity(
        id="CONN-00002",
        entity_type=CONNECTION,
        attributes={"connection_type": "api", "endpoint_url": "https://secure.example.com"},
    )

    result = compliance.evaluate("connection_create", connection)

    assert result["passed"] is True


def test_advertising_disclosure_asset_requires_disclaimer_on_rate_mention():

    asset = Entity(
        id="ASSET-00001",
        entity_type=ASSET,
        attributes={"fields": {"offer_title": "0.9% APR financing available!"}},
    )

    result = compliance.evaluate("asset_approve", asset)

    assert result["passed"] is False
    assert result["violations"][0]["rule_id"] == "advertising_disclosure_asset"


def test_advertising_disclosure_asset_passes_with_disclaimer():

    asset = Entity(
        id="ASSET-00002",
        entity_type=ASSET,
        attributes={"fields": {"offer_title": "0.9% APR", "disclaimer": "See dealer for full terms and conditions."}},
    )

    result = compliance.evaluate("asset_approve", asset)

    assert result["passed"] is True


def test_advertising_disclosure_website_flags_page_without_disclaimer():

    website = Entity(
        id="SITE-00001",
        entity_type=WEBSITE,
        attributes={
            "pages": {
                "home": {"sections": [{"section_key": "hero_banner", "fields": {"headline": "1.9% APR this month!"}}]},
            }
        },
    )

    result = compliance.evaluate("website_publish", website)

    assert result["passed"] is False
    assert result["violations"][0]["rule_id"] == "advertising_disclosure_website"


# ---------------------------------------------------------------------------
# enforce_gate / alerts / notification
# ---------------------------------------------------------------------------

def test_enforce_gate_blocks_and_creates_alert():

    ledger.add_entity(Entity(
        id="CUST-00005",
        entity_type=CUSTOMER,
        attributes={"FirstName": "Incomplete"},
    ))

    deal = _funded_deal(deal_id="DEAL-00005", customer_id="CUST-00005")

    gate = compliance.enforce_gate("deal_fund", deal)

    assert gate["blocked"] is True
    assert gate["alert_id"]

    alerts = compliance.list_alerts(status="open")
    assert len(alerts) == 1
    assert alerts[0].attributes["entity_id"] == "DEAL-00005"


def test_enforce_gate_passes_clean_deal():

    _complete_customer()
    deal = _funded_deal()

    gate = compliance.enforce_gate("deal_fund", deal)

    assert gate["blocked"] is False
    assert compliance.list_alerts() == []


def test_alert_notifies_admin_operations_and_manager_tier():

    credential_store.set_credential("EMP-ADMIN1", "pw", ADMIN)
    credential_store.set_credential("EMP-SALES1", "pw", SALES)

    ledger.add_entity(Entity(
        id="EMP-SALES1",
        entity_type=EMPLOYEE,
        attributes={"Title": "Sales Manager"},
    ))

    ledger.add_entity(Entity(
        id="CUST-00006",
        entity_type=CUSTOMER,
        attributes={"FirstName": "Incomplete"},
    ))

    deal = _funded_deal(deal_id="DEAL-00006", customer_id="CUST-00006")

    gate = compliance.enforce_gate("deal_fund", deal)

    alert = compliance.get_alert(gate["alert_id"])

    assert "EMP-ADMIN1" in alert.attributes["notified_employee_ids"]
    assert "EMP-SALES1" in alert.attributes["notified_employee_ids"]


def test_resolve_alert():

    ledger.add_entity(Entity(id="CUST-00007", entity_type=CUSTOMER, attributes={"FirstName": "X"}))
    deal = _funded_deal(deal_id="DEAL-00007", customer_id="CUST-00007")

    gate = compliance.enforce_gate("deal_fund", deal)

    resolved = compliance.resolve_alert(gate["alert_id"], "EMP-0001", "Fixed the customer record")

    assert resolved.attributes["status"] == "resolved"
    assert resolved.attributes["resolved_by"] == "EMP-0001"


def test_override_alert_requires_notes():

    ledger.add_entity(Entity(id="CUST-00008", entity_type=CUSTOMER, attributes={"FirstName": "X"}))
    deal = _funded_deal(deal_id="DEAL-00008", customer_id="CUST-00008")

    gate = compliance.enforce_gate("deal_fund", deal)

    result = compliance.override_alert(gate["alert_id"], "EMP-ADMIN", "")

    assert "error" in result


def test_override_alert_with_notes():

    ledger.add_entity(Entity(id="CUST-00009", entity_type=CUSTOMER, attributes={"FirstName": "X"}))
    deal = _funded_deal(deal_id="DEAL-00009", customer_id="CUST-00009")

    gate = compliance.enforce_gate("deal_fund", deal)

    result = compliance.override_alert(gate["alert_id"], "EMP-ADMIN", "Manually verified identity offline")

    assert result.attributes["status"] == "overridden"


# ---------------------------------------------------------------------------
# run_full_scan
# ---------------------------------------------------------------------------

def test_run_full_scan_finds_funded_deal_violation():

    ledger.add_entity(Entity(id="CUST-00010", entity_type=CUSTOMER, attributes={"FirstName": "X"}))

    ledger.add_entity(Entity(
        id="DEAL-00010",
        entity_type=DEAL,
        attributes={
            "customer_id": "CUST-00010",
            "status": "funded",
            "contract": {},
            "financing_status": "approved",
            "ofac_screening": {"screened": True, "cleared": True, "screened_by": "TEST-REVIEWER"},
        },
    ))

    result = compliance.run_full_scan()

    assert result["new_alerts"] >= 1
    assert len(compliance.list_alerts(status="open")) >= 1


def test_run_full_scan_does_not_duplicate_open_alerts():

    ledger.add_entity(Entity(id="CUST-00011", entity_type=CUSTOMER, attributes={"FirstName": "X"}))

    ledger.add_entity(Entity(
        id="DEAL-00011",
        entity_type=DEAL,
        attributes={
            "customer_id": "CUST-00011",
            "status": "funded",
            "contract": {},
            "financing_status": "approved",
            "ofac_screening": {"screened": True, "cleared": True, "screened_by": "TEST-REVIEWER"},
        },
    ))

    first = compliance.run_full_scan()
    second = compliance.run_full_scan()

    assert first["new_alerts"] >= 1
    assert second["new_alerts"] == 0


def test_compliance_scheduler_scan_runs_without_error():

    import asyncio

    asyncio.run(compliance_scheduler._run_scan())

    assert compliance_scheduler.last_scan_result is not None
    assert "scanned_at" in compliance_scheduler.last_scan_result


# ---------------------------------------------------------------------------
# ACL (compliance_api.py)
# ---------------------------------------------------------------------------

def test_list_alerts_api_denied_for_sales():

    result = compliance_api.list_alerts_api(SALES)
    assert "error" in result


def test_list_alerts_api_allowed_for_admin_and_operations():

    for role in (ADMIN, OPERATIONS):
        result = compliance_api.list_alerts_api(role)
        assert "alerts" in result


def test_override_alert_api_denied_for_operations():

    ledger.add_entity(Entity(id="CUST-00012", entity_type=CUSTOMER, attributes={"FirstName": "X"}))
    deal = _funded_deal(deal_id="DEAL-00012", customer_id="CUST-00012")

    gate = compliance.enforce_gate("deal_fund", deal)

    result = compliance_api.override_alert_api(OPERATIONS, "EMP-OPS", gate["alert_id"], "Trying to override")

    assert "error" in result


def test_override_alert_api_allowed_for_admin():

    ledger.add_entity(Entity(id="CUST-00013", entity_type=CUSTOMER, attributes={"FirstName": "X"}))
    deal = _funded_deal(deal_id="DEAL-00013", customer_id="CUST-00013")

    gate = compliance.enforce_gate("deal_fund", deal)

    result = compliance_api.override_alert_api(ADMIN, "EMP-ADMIN", gate["alert_id"], "Verified manually")

    assert result["status"] == "overridden"


def test_list_rules_api_returns_notice():

    result = compliance_api.list_rules_api()

    assert "rules" in result
    assert len(result["rules"]) >= 6
    assert "not exhaustive" in result["notice"]
