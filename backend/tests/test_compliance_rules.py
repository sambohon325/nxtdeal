"""
Tests for core/compliance_rules.py — the federal compliance rule catalog (session 38)
that core/compliance.py's evaluate()/enforce_gate() run every gated action against
(deal funding, financing decline, campaign activation, connection creation, asset/website
publish). Each RULE_CATALOG entry carries a real statutory citation and a check(entity)
that returns None when compliant or a short violation string when not.

This module was load-bearing but had zero committed coverage — this file is that coverage,
added per BUILD_QUEUE.md's "convert tests incrementally as modules get touched" standing
item. compliance_rules.py is almost entirely pure logic (the only external dependency is a
lazy `from core.dealeros import ledger` inside the two checks that resolve a linked entity),
so everything here either constructs Entity objects directly or seeds the ledger — fully
deterministic, seed-independent, and free of the FUSE-truncated *_menu/api.app import chain,
so it collects and runs GREEN in the sandbox. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, CAMPAIGN, DEAL, ASSET, WEBSITE, CONNECTION

from core.compliance_rules import (
    RULE_CATALOG,
    NOT_LEGAL_ADVICE_NOTICE,
    all_rules,
    rules_for_action,
    _mentions_rate_or_percentage,
    _check_reg_z_disclosure,
    _check_red_flags_identity,
    _check_ofac_screening,
    _check_ecoa_adverse_action,
    _check_can_spam_tcpa_consent,
    _check_glba_safeguards_encryption,
    _check_advertising_disclosure_asset,
    _check_advertising_disclosure_website,
)


@pytest.fixture(autouse=True)
def clean_ledger():
    """Every test starts from an empty ledger and leaves it empty — the singleton is
    shared process-wide (see core/ledger.py's reset() docstring)."""

    ledger.reset()
    yield
    ledger.reset()


def _deal(**attrs):
    return Entity(id="DEAL-00001", entity_type=DEAL, attributes=attrs)


def _customer(customer_id="CUST-00001", **attrs):
    return Entity(id=customer_id, entity_type=CUSTOMER, attributes=attrs)


def _full_customer(customer_id="CUST-00001"):
    return _customer(
        customer_id,
        FirstName="Jane",
        LastName="Doe",
        Address="123 Main St",
        City="Austin",
        State="TX",
        Zip="78701",
        Phone="512-555-0100",
    )


# ---------------------------------------------------------------------------
# Catalog structure + dispatch (all_rules / rules_for_action / RULE_CATALOG)
# ---------------------------------------------------------------------------

def test_all_rules_returns_eight_rules():
    rules = all_rules()
    assert isinstance(rules, list)
    assert len(rules) == 8


def test_all_rules_returns_a_copy():
    rules = all_rules()
    rules.append({"id": "bogus"})
    assert len(all_rules()) == 8  # mutating the returned list must not corrupt the catalog


def test_every_rule_has_required_keys_and_callable_check():
    for rule in RULE_CATALOG:
        for key in ("id", "law", "citation", "category", "severity", "applies_to", "check"):
            assert key in rule, f"{rule.get('id')} missing {key}"
        assert isinstance(rule["applies_to"], list) and rule["applies_to"]
        assert callable(rule["check"])


def test_rule_ids_are_unique():
    ids = [r["id"] for r in RULE_CATALOG]
    assert len(ids) == len(set(ids))


def test_severity_is_high_or_medium_only():
    assert all(r["severity"] in ("high", "medium") for r in RULE_CATALOG)


def test_categories_are_within_documented_set():
    allowed = {"lending", "credit", "identity", "marketing", "data_security", "advertising"}
    assert all(r["category"] in allowed for r in RULE_CATALOG)


def test_rules_for_action_deal_fund_returns_three_funding_rules():
    ids = {r["id"] for r in rules_for_action("deal_fund")}
    assert ids == {"reg_z_disclosure", "red_flags_identity", "ofac_screening"}


def test_rules_for_action_maps_each_action_to_its_rules():
    expected = {
        "deal_decline": {"ecoa_adverse_action"},
        "campaign_activate": {"can_spam_tcpa_consent"},
        "connection_create": {"glba_safeguards_encryption"},
        "asset_approve": {"advertising_disclosure_asset"},
        "website_publish": {"advertising_disclosure_website"},
    }
    for action, ids in expected.items():
        assert {r["id"] for r in rules_for_action(action)} == ids


def test_rules_for_action_unknown_action_returns_empty():
    assert rules_for_action("not_a_real_action") == []


def test_not_legal_advice_notice_is_present_and_hedged():
    assert "starting compliance framework" in NOT_LEGAL_ADVICE_NOTICE
    assert "not a substitute" in NOT_LEGAL_ADVICE_NOTICE


# ---------------------------------------------------------------------------
# Reg Z disclosure (deal funding)
# ---------------------------------------------------------------------------

def _valid_contract(**overrides):
    contract = {
        "apr": 5.9,
        "amount_financed": 25000,
        "monthly_payment": 450,
        "term_months": 60,
        "disclosures": ["Truth in Lending disclosure text"],
    }
    contract.update(overrides)
    return contract


def test_reg_z_no_contract_flags():
    result = _check_reg_z_disclosure(_deal())
    assert result is not None and "No contract on file" in result


def test_reg_z_missing_field_names_the_field():
    result = _check_reg_z_disclosure(_deal(contract=_valid_contract(apr=None)))
    assert result is not None and "apr" in result


def test_reg_z_zero_value_counts_as_missing():
    # a 0 in a required field is treated as unpopulated (None, "", 0)
    result = _check_reg_z_disclosure(_deal(contract=_valid_contract(monthly_payment=0)))
    assert result is not None and "monthly_payment" in result


def test_reg_z_missing_disclosures_flags():
    result = _check_reg_z_disclosure(_deal(contract=_valid_contract(disclosures=[])))
    assert result is not None and "disclosure statements" in result


def test_reg_z_fully_populated_contract_passes():
    assert _check_reg_z_disclosure(_deal(contract=_valid_contract())) is None


# ---------------------------------------------------------------------------
# Red Flags identity (deal funding, ledger-backed)
# ---------------------------------------------------------------------------

def test_red_flags_no_customer_id_flags():
    result = _check_red_flags_identity(_deal())
    assert result is not None and "No linked customer record" in result


def test_red_flags_customer_not_found_flags():
    result = _check_red_flags_identity(_deal(customer_id="CUST-99999"))
    assert result is not None and "No linked customer record" in result


def test_red_flags_linked_entity_wrong_type_flags():
    ledger.add_entity(Entity(id="CUST-00001", entity_type=DEAL, attributes={}))
    result = _check_red_flags_identity(_deal(customer_id="CUST-00001"))
    assert result is not None and "No linked customer record" in result


def test_red_flags_missing_identity_field_named():
    cust = _full_customer()
    del cust.attributes["Zip"]
    ledger.add_entity(cust)
    result = _check_red_flags_identity(_deal(customer_id="CUST-00001"))
    assert result is not None and "Zip" in result


def test_red_flags_no_contact_method_flags():
    cust = _full_customer()
    del cust.attributes["Phone"]  # no Phone and no Email
    ledger.add_entity(cust)
    result = _check_red_flags_identity(_deal(customer_id="CUST-00001"))
    assert result is not None and "no phone or email" in result


def test_red_flags_email_alone_satisfies_contact_requirement():
    cust = _full_customer()
    del cust.attributes["Phone"]
    cust.attributes["Email"] = "jane@example.com"
    ledger.add_entity(cust)
    assert _check_red_flags_identity(_deal(customer_id="CUST-00001")) is None


def test_red_flags_complete_customer_passes():
    ledger.add_entity(_full_customer())
    assert _check_red_flags_identity(_deal(customer_id="CUST-00001")) is None


# ---------------------------------------------------------------------------
# OFAC / SDN screening (deal funding)
# ---------------------------------------------------------------------------

def test_ofac_no_screening_flags():
    result = _check_ofac_screening(_deal())
    assert result is not None and "No OFAC/SDN screening" in result


def test_ofac_screened_false_flags():
    result = _check_ofac_screening(_deal(ofac_screening={"screened": False}))
    assert result is not None and "No OFAC/SDN screening" in result


def test_ofac_screened_but_not_cleared_flags():
    result = _check_ofac_screening(_deal(ofac_screening={"screened": True, "cleared": False}))
    assert result is not None and "did NOT clear" in result


def test_ofac_screened_and_cleared_passes():
    assert _check_ofac_screening(_deal(ofac_screening={"screened": True, "cleared": True})) is None


# ---------------------------------------------------------------------------
# ECOA adverse action (deal decline)
# ---------------------------------------------------------------------------

def test_ecoa_not_declined_is_not_applicable():
    assert _check_ecoa_adverse_action(_deal(financing_status="approved")) is None
    assert _check_ecoa_adverse_action(_deal()) is None


def test_ecoa_declined_without_reason_flags():
    result = _check_ecoa_adverse_action(_deal(financing_status="declined"))
    assert result is not None and "no documented reason" in result


def test_ecoa_declined_with_reason_passes():
    deal = _deal(financing_status="declined", financing_notes="Insufficient credit history")
    assert _check_ecoa_adverse_action(deal) is None


# ---------------------------------------------------------------------------
# CAN-SPAM / TCPA consent (campaign activation, ledger-backed)
# ---------------------------------------------------------------------------

def _campaign(audience_ids):
    return Entity(id="CAMP-00001", entity_type=CAMPAIGN, attributes={"audience_ids": audience_ids})


def test_can_spam_no_audience_passes():
    assert _check_can_spam_tcpa_consent(_campaign([])) is None


def test_can_spam_all_clear_passes():
    ledger.add_entity(_customer("CUST-00001", DoNotContact=False))
    ledger.add_entity(_customer("CUST-00002"))
    assert _check_can_spam_tcpa_consent(_campaign(["CUST-00001", "CUST-00002"])) is None


def test_can_spam_flags_do_not_contact_member():
    ledger.add_entity(_customer("CUST-00001", DoNotContact=True))
    ledger.add_entity(_customer("CUST-00002"))
    result = _check_can_spam_tcpa_consent(_campaign(["CUST-00001", "CUST-00002"]))
    assert result is not None and "1 audience member" in result


def test_can_spam_counts_all_flagged_members():
    ledger.add_entity(_customer("CUST-00001", DoNotContact=True))
    ledger.add_entity(_customer("CUST-00002", DoNotContact="true"))
    result = _check_can_spam_tcpa_consent(_campaign(["CUST-00001", "CUST-00002"]))
    assert result is not None and "2 audience member" in result


@pytest.mark.parametrize("flag", [True, "true", "True", "1", 1])
def test_can_spam_recognizes_truthy_do_not_contact_variants(flag):
    ledger.add_entity(_customer("CUST-00001", DoNotContact=flag))
    result = _check_can_spam_tcpa_consent(_campaign(["CUST-00001"]))
    assert result is not None


def test_can_spam_skips_missing_audience_entities():
    # an id with no entity in the ledger is skipped (continue), not treated as a violation
    assert _check_can_spam_tcpa_consent(_campaign(["CUST-DOESNOTEXIST"])) is None


# ---------------------------------------------------------------------------
# GLBA Safeguards encryption (connection creation)
# ---------------------------------------------------------------------------

def _connection(**attrs):
    return Entity(id="CONN-00001", entity_type=CONNECTION, attributes=attrs)


def test_glba_non_api_connection_is_not_applicable():
    assert _check_glba_safeguards_encryption(_connection(connection_type="csv")) is None
    assert _check_glba_safeguards_encryption(_connection()) is None


def test_glba_https_endpoint_passes():
    conn = _connection(connection_type="api", endpoint_url="https://crm.example.com/api")
    assert _check_glba_safeguards_encryption(conn) is None


def test_glba_http_endpoint_flags():
    conn = _connection(connection_type="api", endpoint_url="http://crm.example.com/api")
    result = _check_glba_safeguards_encryption(conn)
    assert result is not None and "HTTPS" in result


def test_glba_http_endpoint_with_leading_whitespace_and_case_flags():
    conn = _connection(connection_type="api", endpoint_url="  HTTP://crm.example.com")
    assert _check_glba_safeguards_encryption(conn) is not None


def test_glba_api_with_empty_endpoint_does_not_flag_encryption():
    # empty endpoint doesn't start with http:// so the encryption rule stays silent
    assert _check_glba_safeguards_encryption(_connection(connection_type="api", endpoint_url="")) is None


# ---------------------------------------------------------------------------
# Rate-mention heuristic + advertising disclosure (asset / website)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["2.9% APR", "0% financing", "as low as 3.49%", "great APR here", "apr special"])
def test_rate_mention_heuristic_detects_rates(text):
    assert _mentions_rate_or_percentage(text) is True


@pytest.mark.parametrize("text", ["", "Big summer sale", "Best trucks in town", None])
def test_rate_mention_heuristic_ignores_non_rate_text(text):
    assert _mentions_rate_or_percentage(text) is False


def _asset(fields):
    return Entity(id="ASSET-00001", entity_type=ASSET, attributes={"fields": fields})


def test_asset_rate_without_disclaimer_flags():
    result = _check_advertising_disclosure_asset(_asset({"headline": "2.9% APR available"}))
    assert result is not None and "no disclaimer" in result


def test_asset_rate_with_disclaimer_passes():
    asset = _asset({"headline": "2.9% APR available", "disclaimer": "For well-qualified buyers. Terms apply."})
    assert _check_advertising_disclosure_asset(asset) is None


def test_asset_blank_disclaimer_still_flags():
    asset = _asset({"headline": "2.9% APR available", "disclaimer": "   "})
    assert _check_advertising_disclosure_asset(asset) is not None


def test_asset_no_rate_mention_passes():
    assert _check_advertising_disclosure_asset(_asset({"headline": "Huge inventory clearance"})) is None


def _website(pages):
    return Entity(id="WEB-00001", entity_type=WEBSITE, attributes={"pages": pages})


def test_website_rate_page_without_disclaimer_block_flags_that_page():
    pages = {
        "specials": {"sections": [{"section_key": "hero", "fields": {"headline": "0% APR for 60 months"}}]},
    }
    result = _check_advertising_disclosure_website(_website(pages))
    assert result is not None and "specials" in result


def test_website_rate_page_with_disclaimer_block_passes():
    pages = {
        "specials": {"sections": [
            {"section_key": "hero", "fields": {"headline": "0% APR for 60 months"}},
            {"section_key": "text_block", "fields": {"body": "Offer for well-qualified buyers only; see dealer for terms."}},
        ]},
    }
    assert _check_advertising_disclosure_website(_website(pages)) is None


def test_website_disclaimer_block_must_have_real_body():
    # a text_block with a <=20 char body doesn't count as a disclaimer
    pages = {
        "specials": {"sections": [
            {"section_key": "hero", "fields": {"headline": "0% APR"}},
            {"section_key": "text_block", "fields": {"body": "short"}},
        ]},
    }
    assert _check_advertising_disclosure_website(_website(pages)) is not None


def test_website_page_without_rate_mention_passes():
    pages = {"home": {"sections": [{"section_key": "hero", "fields": {"headline": "Welcome"}}]}}
    assert _check_advertising_disclosure_website(_website(pages)) is None


def test_website_only_offending_pages_are_listed():
    pages = {
        "home": {"sections": [{"section_key": "hero", "fields": {"headline": "Welcome"}}]},
        "specials": {"sections": [{"section_key": "hero", "fields": {"headline": "1.9% APR"}}]},
    }
    result = _check_advertising_disclosure_website(_website(pages))
    assert result is not None and "specials" in result and "home" not in result
