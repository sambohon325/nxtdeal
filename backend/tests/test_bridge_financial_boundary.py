"""Imported financial facts must not enter native execution/posting workflows."""
from copy import deepcopy
from core import dealer_bridge as b
from core.dealeros import ledger
from core.entities import Entity
from core.payments import _all_payments
from core.loan_servicing import _all_loans, _get_loan
from core.loan_accounting import _approved_payments, post_payment_to_ledger
from tests.test_dealer_bridge import A, B, setup, imported, isolated  # noqa: F401


def test_imported_approved_payment_is_not_postable_or_counted_as_native_cash():
    system, customer_mapping = setup(); imported(mapping=customer_mapping)
    account_mapping = b.propose_mapping(A, system, "LoanAccount", "accounts", {
        "customer_id": {"source": "customer", "transform": "external_id", "object_type": "customers"},
        "balance": {"source": "balance", "transform": "text"}, "currency": {"source": "currency", "transform": "text"}})["id"]
    b.approve_mapping(B, account_mapping)
    imported("external_id,modified_at,customer,balance,currency\na1,2026-01-01T00:00:00Z,1,100,USD\n", account_mapping)
    payment_mapping = b.propose_mapping(A, system, "Payment", "payments", {
        "account_id": {"source": "account", "transform": "external_id", "object_type": "accounts"},
        **{field: {"source": field, "transform": "text"} for field in ("paid_at", "amount", "currency", "status")}})["id"]
    b.approve_mapping(B, payment_mapping)
    imported("external_id,modified_at,account,paid_at,amount,currency,status\np1,2026-01-02T00:00:00Z,a1,2026-01-02T00:00:00Z,10,USD,approved\n", payment_mapping)
    payment = next(e for e in ledger.get_all().values() if e.entity_type == "ImportedPayment")
    before = deepcopy(payment.attributes)
    assert payment.attributes["canonical_kind"] == "Payment"
    assert _all_payments() == [] and _approved_payments() == []
    assert "error" in post_payment_to_ledger(payment.id, B["employee_id"])
    assert payment.attributes == before


def test_imported_finance_contract_stays_out_of_native_servicing():
    system, customer_mapping = setup(); imported(mapping=customer_mapping)
    mapping = b.propose_mapping(A, system, "FinanceContract", "contracts", {
        "lender_name": {"source": "lender", "transform": "text"}, "status": {"source": "status", "transform": "text"}})["id"]
    b.approve_mapping(B, mapping)
    imported("external_id,modified_at,lender,status\nf1,2026-01-01T00:00:00Z,Example,active\n", mapping)
    contract = next(e for e in ledger.get_all().values() if e.entity_type == "ImportedFinanceContract")
    assert contract.attributes["canonical_kind"] == "FinanceContract"
    assert _all_loans() == [] and _get_loan(contract.id) is None
    imported("external_id,modified_at,lender,status\nf1,2026-01-02T00:00:00Z,Example,closed\n", mapping)
    assert contract.attributes["status"] == "closed"
    account_mapping = b.propose_mapping(A, system, "LoanAccount", "accounts", {
        "customer_id": {"source": "customer", "transform": "external_id", "object_type": "customers"},
        "contract_id": {"source": "contract", "transform": "external_id", "object_type": "contracts"},
        "balance": {"source": "balance", "transform": "text"}, "currency": {"source": "currency", "transform": "text"}})["id"]
    b.approve_mapping(B, account_mapping)
    imported("external_id,modified_at,customer,contract,balance,currency\na1,2026-01-02T00:00:00Z,1,f1,100,USD\n", account_mapping)
    account = next(e for e in ledger.get_all().values() if e.entity_type == "LoanAccount")
    assert account.attributes["contract_id"] == contract.id


def test_native_payment_behavior_remains_available():
    native = Entity("NATIVE-PAYMENT", "Payment", {"status": "approved", "amount": 10, "payment_date": "2026-01-02"})
    ledger.add_entity(native)
    assert _all_payments() == [native] and _approved_payments() == [native]


def test_imported_contract_stage_deal_cannot_enter_native_funding():
    from core.deals import _all_deals, get_deal, fund_deal, add_scenario
    system, _ = setup()
    mapping = b.propose_mapping(A, system, "Deal", "deals", {
        field: {"source": field, "transform": "text"} for field in ("status", "amount", "currency")})["id"]
    b.approve_mapping(B, mapping)
    imported("external_id,modified_at,status,amount,currency\nd1,2026-10-01T00:00:00Z,contract,10000,USD\n", mapping)
    deal = next(entity for entity in ledger.entities.values() if entity.entity_type == "ImportedDeal")
    before = deepcopy(deal.attributes)
    assert deal.attributes["canonical_kind"] == "Deal" and _all_deals() == [] and get_deal(deal.id) is None
    assert "error" in fund_deal(deal.id)
    assert "error" in add_scenario(deal.id, "Should not run", 10000, 1000, 24)
    assert deal.attributes == before
    assert not any(entity.entity_type == "FinanceContract" for entity in ledger.entities.values())
    imported("external_id,modified_at,status,amount,currency\nd1,2026-10-02T00:00:00Z,funded,10000,USD\n", mapping)
    assert deal.attributes["status"] == "funded" and _all_deals() == []


def test_imported_active_campaign_is_not_a_native_campaign_activation():
    from core.campaigns import _all_campaigns, get_campaign, activate_campaign
    system, _ = setup()
    mapping = b.propose_mapping(A, system, "Campaign", "campaigns", {
        field: {"source": field, "transform": "text"} for field in ("name", "status")})["id"]
    b.approve_mapping(B, mapping)
    imported("external_id,modified_at,name,status\nc1,2026-10-01T00:00:00Z,Source campaign,active\n", mapping)
    campaign = next(entity for entity in ledger.entities.values() if entity.entity_type == "ImportedCampaign")
    before = deepcopy(campaign.attributes)
    assert campaign.attributes["canonical_kind"] == "Campaign" and _all_campaigns() == []
    assert get_campaign(campaign.id) is None and activate_campaign(campaign.id) is None
    assert campaign.attributes == before
    ledger.add_entity(Entity("native-campaign", "Campaign", {"name": "Native draft", "status": "draft"}))
    assert get_campaign("native-campaign") is not None
