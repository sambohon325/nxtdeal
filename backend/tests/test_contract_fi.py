"""
Tests for accepted F&I products rolling into the authoritative contract + FinanceContract
(2026-07-24). Run from backend/ with `pytest`. Closes the recon gap where generate_contract
copied amount_financed straight from the scenario, ignoring financed back-end products.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, FINANCE_CONTRACT
from core.deals import (
    create_deal, add_scenario, select_scenario, choose_in_house_financing,
    generate_contract, fund_deal, _monthly_payment,
)
from core.fi_products import present_fi_products, decide_fi_product, get_fi_menu, FI_PRODUCT_CATALOG


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    yield
    ledger.reset()


def _deal_to_financing():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"FirstName": "Pat", "LastName": "Q", "CreditScore": 720}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford", "Model": "F-150", "Year": 2024, "Price": 40000, "Cost": 34000, "VIN": "1X"}))
    deal = create_deal("CUST-1", "VEH-1", "EMP-1")
    add_scenario(deal.id, "Base", 39000, 3000, 60)  # amount_financed 36000
    select_scenario(deal.id, "scn-1")
    choose_in_house_financing(deal.id)
    return deal.id


def test_accepted_fi_rolls_into_contract():
    deal_id = _deal_to_financing()
    key = FI_PRODUCT_CATALOG[0]["key"]
    present_fi_products(deal_id, [key], "EMP-1")
    decide_fi_product(deal_id, key, "accepted")
    fi_price = get_fi_menu(deal_id)["totals"]["total_price_accepted"]
    assert fi_price > 0

    deal = generate_contract(deal_id)
    c = deal.attributes["contract"]
    assert c["base_amount_financed"] == 36000
    assert c["fi_products_financed"] == fi_price
    assert c["amount_financed"] == round(36000 + fi_price, 2)
    # payment recomputed on the larger balance -> strictly higher than the base
    assert c["monthly_payment"] == _monthly_payment(c["amount_financed"], c["apr"], c["term_months"])
    assert c["monthly_payment"] > c["base_monthly_payment"]
    assert len(c["fi_products"]) == 1 and c["fi_products"][0]["product_key"] == key


def test_finance_contract_reflects_fi():
    deal_id = _deal_to_financing()
    key = FI_PRODUCT_CATALOG[0]["key"]
    present_fi_products(deal_id, [key], "EMP-1")
    decide_fi_product(deal_id, key, "accepted")
    fi_price = get_fi_menu(deal_id)["totals"]["total_price_accepted"]
    generate_contract(deal_id)
    fund_deal(deal_id)

    fc = [e for e in ledger.get_all().values() if e.entity_type == FINANCE_CONTRACT][0]
    assert float(fc.attributes["AmountFinanced"]) == round(36000 + fi_price, 2)


def test_no_fi_leaves_contract_unchanged():
    deal_id = _deal_to_financing()
    deal = generate_contract(deal_id)
    c = deal.attributes["contract"]
    assert c["fi_products_financed"] == 0
    assert c["fi_products"] == []
    assert c["amount_financed"] == 36000  # base, unchanged (backward compatible)
    assert c["monthly_payment"] == c["base_monthly_payment"]
