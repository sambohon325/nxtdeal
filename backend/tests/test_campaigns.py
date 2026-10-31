"""
Tests for the campaign & customer-lifecycle engine (core/campaigns.py,
core/campaigns_api.py) -- session 31. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import datetime, timezone, timedelta

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import CUSTOMER, VEHICLE, SERVICE_RECORD, FINANCE_CONTRACT, LEAD
from core import campaigns
from core import campaigns_api
from core import assets_api
from core.permissions import ADMIN, MARKETING, SALES, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_audit_writes(monkeypatch):

    monkeypatch.setattr(campaigns_api, "save_audit_log", lambda filepath: None)


def _iso(d):
    return d.isoformat()


def _today():
    return datetime.now(timezone.utc).date()


def _add_customer(customer_id, first="Jane", last="Doe"):

    ledger.add_entity(Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={"CustomerID": customer_id, "FirstName": first, "LastName": last},
    ))

    return customer_id


def _add_vehicle(vehicle_id, make="Honda", model="Civic", date_sold=None):

    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"Make": make, "Model": model, "DateSold": _iso(date_sold) if date_sold else None},
    ))

    return vehicle_id


def _add_service_record(record_id, service_date):

    ledger.add_entity(Entity(
        id=record_id,
        entity_type=SERVICE_RECORD,
        attributes={"ServiceDate": _iso(service_date)},
    ))

    return record_id


def _add_finance_contract(contract_id, contract_date, term_months):

    ledger.add_entity(Entity(
        id=contract_id,
        entity_type=FINANCE_CONTRACT,
        attributes={"ContractDate": _iso(contract_date), "TermMonths": str(term_months)},
    ))

    return contract_id


def _add_lead(lead_id):

    ledger.add_entity(Entity(
        id=lead_id,
        entity_type=LEAD,
        attributes={"LeadID": lead_id},
    ))

    return lead_id


def _link(source, target, rel_type):

    ledger.add_relationship(Relationship(source_id=source, target_id=target, relationship_type=rel_type))


# --- Campaign type catalog ---


def test_list_campaign_types_returns_current_catalog():

    types = campaigns.list_campaign_types()

    assert {t["key"] for t in types} == {
        "retention",
        "inventory_ads",
        "finance_renewal",
        "accessory_accelerator",
        "general",
        "individual",
        "event_promo",
    }


def test_list_channels_returns_four_channels():

    assert set(campaigns.list_channels()) == {"email", "sms", "direct_mail", "ringless_voicemail"}


# --- Audience segmentation: retention ---


def test_retention_audience_includes_customer_never_serviced():

    _add_customer("CUST-1")

    audience = campaigns.build_audience("retention", {"months_since_service": 6})

    assert "CUST-1" in [c.id for c in audience]


def test_retention_audience_includes_customer_with_old_service_date():

    _add_customer("CUST-1")
    _add_service_record("SRV-1", _today() - timedelta(days=400))
    _link("CUST-1", "SRV-1", "AUTHORIZED")

    audience = campaigns.build_audience("retention", {"months_since_service": 6})

    assert "CUST-1" in [c.id for c in audience]


def test_retention_audience_excludes_customer_with_recent_service():

    _add_customer("CUST-1")
    _add_service_record("SRV-1", _today() - timedelta(days=10))
    _link("CUST-1", "SRV-1", "AUTHORIZED")

    audience = campaigns.build_audience("retention", {"months_since_service": 6})

    assert "CUST-1" not in [c.id for c in audience]


# --- Audience segmentation: finance_renewal ---


def test_finance_renewal_audience_includes_upcoming_maturity():

    _add_customer("CUST-1")
    # Contract 34 months ago with a 36-month term matures in ~2 months.
    _add_finance_contract("FIN-1", _today() - timedelta(days=34 * 30), 36)
    _link("CUST-1", "FIN-1", "FINANCED_BY")

    audience = campaigns.build_audience("finance_renewal", {"months_to_maturity": 3})

    assert "CUST-1" in [c.id for c in audience]


def test_finance_renewal_audience_excludes_far_future_maturity():

    _add_customer("CUST-1")
    # Brand-new 60-month contract -- nowhere near maturity.
    _add_finance_contract("FIN-1", _today(), 60)
    _link("CUST-1", "FIN-1", "FINANCED_BY")

    audience = campaigns.build_audience("finance_renewal", {"months_to_maturity": 3})

    assert "CUST-1" not in [c.id for c in audience]


def test_finance_renewal_audience_excludes_already_matured_contract():

    _add_customer("CUST-1")
    _add_finance_contract("FIN-1", _today() - timedelta(days=100 * 30), 36)
    _link("CUST-1", "FIN-1", "FINANCED_BY")

    audience = campaigns.build_audience("finance_renewal", {"months_to_maturity": 3})

    assert "CUST-1" not in [c.id for c in audience]


# --- Audience segmentation: inventory_ads ---


def test_inventory_ads_audience_filters_by_make_model():

    _add_lead("LEAD-1")
    _add_vehicle("VEH-1", make="Honda", model="Civic")
    _link("LEAD-1", "VEH-1", "INTERESTED_IN")

    _add_lead("LEAD-2")
    _add_vehicle("VEH-2", make="Ford", model="F-150")
    _link("LEAD-2", "VEH-2", "INTERESTED_IN")

    audience = campaigns.build_audience("inventory_ads", {"make": "Honda"})

    assert [l.id for l in audience] == ["LEAD-1"]


def test_inventory_ads_audience_with_no_filter_includes_all_interested_leads():

    _add_lead("LEAD-1")
    _add_vehicle("VEH-1", make="Honda", model="Civic")
    _link("LEAD-1", "VEH-1", "INTERESTED_IN")

    audience = campaigns.build_audience("inventory_ads", {})

    assert [l.id for l in audience] == ["LEAD-1"]


def test_inventory_ads_audience_targets_leads_not_customers():

    assert campaigns.audience_entity_type("inventory_ads") == LEAD
    assert campaigns.audience_entity_type("retention") == CUSTOMER


# --- Audience segmentation: accessory_accelerator ---


def test_accessory_accelerator_audience_includes_recent_buyer():

    _add_customer("CUST-1")
    _add_vehicle("VEH-1", date_sold=_today() - timedelta(days=10))
    _link("CUST-1", "VEH-1", "OWNS")

    audience = campaigns.build_audience("accessory_accelerator", {"days_since_sale": 30})

    assert "CUST-1" in [c.id for c in audience]


def test_accessory_accelerator_audience_excludes_old_buyer():

    _add_customer("CUST-1")
    _add_vehicle("VEH-1", date_sold=_today() - timedelta(days=400))
    _link("CUST-1", "VEH-1", "OWNS")

    audience = campaigns.build_audience("accessory_accelerator", {"days_since_sale": 30})

    assert "CUST-1" not in [c.id for c in audience]


# --- Audience segmentation: general ---


def test_general_audience_includes_all_customers():

    _add_customer("CUST-1")
    _add_customer("CUST-2")

    audience = campaigns.build_audience("general", {})

    assert {c.id for c in audience} == {"CUST-1", "CUST-2"}


# --- Preview ---


def test_preview_audience_returns_count_and_sample():

    _add_customer("CUST-1")

    result = campaigns_api.preview_audience_api("general", {})

    assert result["count"] == 1
    assert result["sample"][0]["id"] == "CUST-1"


def test_preview_audience_rejects_unknown_type():

    result = campaigns_api.preview_audience_api("not-a-type", {})

    assert "error" in result


# --- Create campaign ---


def test_create_campaign_rejects_unknown_type():

    result = campaigns_api.create_campaign_api("EMP-00001", "not-a-type", "Test", None, {})

    assert "error" in result


def test_create_campaign_rejects_missing_required_audience_field():

    result = campaigns_api.create_campaign_api("EMP-00001", "retention", "Test", None, {})

    assert "error" in result
    assert "months_since_service" in result["error"]


def test_create_campaign_defaults_channel_from_type():

    _add_customer("CUST-1")

    result = campaigns_api.create_campaign_api(
        "EMP-00001", "retention", "Win them back", None, {"months_since_service": 6}
    )

    assert "error" not in result
    assert result["channel"] == "email"
    assert result["status"] == "draft"
    assert result["audience_count"] == 1


def test_create_campaign_rejects_unknown_linked_asset():

    result = campaigns_api.create_campaign_api(
        "EMP-00001", "general", "Test", "email", {}, linked_asset_id="ASSET-99999"
    )

    assert "error" in result


# --- Activation lifecycle + ACL ---


def test_activate_denied_for_non_marketing_non_admin():

    created = campaigns_api.create_campaign_api("EMP-00001", "general", "Test", "email", {})

    result = campaigns_api.activate_campaign_api(SALES, "EMP-00001", created["id"])

    assert "error" in result


def test_activate_requires_draft_status():

    created = campaigns_api.create_campaign_api("EMP-00001", "general", "Test", "email", {})
    campaigns_api.activate_campaign_api(MARKETING, "EMP-00002", created["id"])

    result = campaigns_api.activate_campaign_api(MARKETING, "EMP-00002", created["id"])

    assert "error" in result


def test_activate_success_stamps_sent_count_from_audience_snapshot():

    _add_customer("CUST-1")
    _add_customer("CUST-2")

    created = campaigns_api.create_campaign_api("EMP-00001", "general", "Test", "email", {})
    assert created["audience_count"] == 2

    result = campaigns_api.activate_campaign_api(MARKETING, "EMP-00002", created["id"])

    assert result["status"] == "active"
    assert result["sent_count"] == 2
    assert result["activated_at"] is not None


def test_activate_blocked_when_linked_asset_not_approved():

    asset = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )

    created = campaigns_api.create_campaign_api(
        "EMP-00001", "general", "Test", "email", {}, linked_asset_id=asset["id"]
    )

    result = campaigns_api.activate_campaign_api(MARKETING, "EMP-00002", created["id"])

    assert "error" in result
    assert "approved" in result["error"]


def test_activate_allowed_once_linked_asset_is_approved():

    asset = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )
    assets_api.submit_asset_api(SALES, "EMP-00001", asset["id"])
    assets_api.approve_asset_api(MARKETING, "EMP-00003", asset["id"])

    created = campaigns_api.create_campaign_api(
        "EMP-00001", "general", "Test", "email", {}, linked_asset_id=asset["id"]
    )

    result = campaigns_api.activate_campaign_api(MARKETING, "EMP-00002", created["id"])

    assert result["status"] == "active"


def test_complete_requires_active_status():

    created = campaigns_api.create_campaign_api("EMP-00001", "general", "Test", "email", {})

    result = campaigns_api.complete_campaign_api(MARKETING, "EMP-00002", created["id"])

    assert "error" in result


def test_complete_success():

    created = campaigns_api.create_campaign_api("EMP-00001", "general", "Test", "email", {})
    campaigns_api.activate_campaign_api(MARKETING, "EMP-00002", created["id"])

    result = campaigns_api.complete_campaign_api(MARKETING, "EMP-00002", created["id"])

    assert result["status"] == "completed"
    assert result["completed_at"] is not None


def test_cancel_allowed_by_creator():

    created = campaigns_api.create_campaign_api("EMP-00001", "general", "Test", "email", {})

    result = campaigns_api.cancel_campaign_api(SALES, "EMP-00001", created["id"])

    assert result["status"] == "cancelled"


def test_cancel_denied_for_unrelated_non_marketing_non_admin():

    created = campaigns_api.create_campaign_api("EMP-00001", "general", "Test", "email", {})

    result = campaigns_api.cancel_campaign_api(SERVICE, "EMP-00002", created["id"])

    assert "error" in result


def test_cancel_allowed_for_admin_regardless_of_creator():

    created = campaigns_api.create_campaign_api("EMP-00001", "general", "Test", "email", {})

    result = campaigns_api.cancel_campaign_api(ADMIN, "EMP-99999", created["id"])

    assert result["status"] == "cancelled"


# --- Visibility / listing ---


def test_get_campaign_visible_to_creator():

    created = campaigns_api.create_campaign_api("EMP-00001", "general", "Test", "email", {})

    result = campaigns_api.get_campaign_api(SALES, "EMP-00001", created["id"])

    assert "error" not in result


def test_get_campaign_denied_to_unrelated_non_reviewer():

    created = campaigns_api.create_campaign_api("EMP-00001", "general", "Test", "email", {})

    result = campaigns_api.get_campaign_api(SALES, "EMP-00002", created["id"])

    assert "error" in result


def test_list_my_campaigns_only_returns_own_campaigns():

    campaigns_api.create_campaign_api("EMP-00001", "general", "Test A", "email", {})
    campaigns_api.create_campaign_api("EMP-00002", "general", "Test B", "email", {})

    mine = campaigns_api.list_my_campaigns_api("EMP-00001")

    assert len(mine) == 1
    assert mine[0]["created_by"] == "EMP-00001"


def test_pending_campaigns_denied_for_non_marketing_non_admin():

    result = campaigns_api.list_pending_campaigns_api(SALES)

    assert "error" in result


def test_pending_campaigns_allowed_for_marketing_and_admin():

    created = campaigns_api.create_campaign_api("EMP-00001", "general", "Test", "email", {})

    for role in (MARKETING, ADMIN):
        result = campaigns_api.list_pending_campaigns_api(role)
        assert isinstance(result, list)
        assert any(c["id"] == created["id"] for c in result)
