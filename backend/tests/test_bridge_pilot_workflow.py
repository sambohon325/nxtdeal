"""Synthetic cross-stack pilot through HTTP, durable reload and local temporal delivery.

No fixture claims to be a vendor schema and no provider/network adapter is used.
"""
import csv
import io
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import router, admin
from core import dealer_bridge as b, bridge_chrono as outbox
from core.dealeros import ledger, registry
from core.storage import save_graph, load_graph
from core.payments import _all_payments
from core.loan_servicing import _all_loans
from core.entity_types import GL_ENTRY, BANK_TRANSACTION, REPOSSESSION_CASE
from chrono.delivery import DeliveryReceipt
from tests.test_dealer_bridge import A, B, API, isolated  # noqa: F401


def csv_export(columns, rows, modified="2026-10-02T12:00:00Z"):
    stream = io.StringIO(); writer = csv.writer(stream)
    writer.writerow(["external_id", "modified_at", *columns])
    for external_id, values in rows:
        writer.writerow([external_id, modified, *values])
    return stream.getvalue()


def test_independent_dms_crm_accounting_pilot_survives_restart_without_native_posting(tmp_path, monkeypatch):
    path = str(tmp_path / "synthetic-pilot.json")
    monkeypatch.setattr(b, "GRAPH_PATH", path)
    monkeypatch.setattr(b, "save_graph", save_graph)
    monkeypatch.setattr(registry, "vehicle_vins", {})
    monkeypatch.setattr(outbox, "_BINDING", None)
    monkeypatch.setattr(outbox.credential_store, "get_record", lambda _: {"role": "ADMIN"})
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    actor = API
    app.dependency_overrides[admin] = lambda: actor

    def call(endpoint, body=None, human=False):
        nonlocal actor
        actor = B if human else API
        response = client.get("/dealer-bridge" + endpoint) if body is None else client.post("/dealer-bridge" + endpoint, json=body)
        assert response.status_code == 200, response.text
        return response.json()

    def mapping(system, kind, source, columns, overrides=None):
        fields = {column: {"source": column, "transform": "text"} for column in columns}
        fields.update(overrides or {})
        value = call("/mappings", {"system_id": system, "kind": kind, "object_type": source, "fields": fields})["id"]
        call(f"/mappings/{value}/approve", {}, human=True)
        return value

    jobs = []
    def activate(mapping_id, columns, rows, *, expected=None, modified="2026-10-02T12:00:00Z"):
        body = {"mapping_id": mapping_id, "content": csv_export(columns, rows, modified)}
        if expected is not None: body["expectations"] = expected
        job = call("/imports", body)["id"]
        preview = call(f"/imports/{job}/validate", {})["rows"]
        assert all(row["status"] != "quarantined" for row in preview), preview
        call(f"/imports/{job}/activate", {}, human=True)
        jobs.append(job)
        return job

    def ref(source):
        return {"source": source, "transform": "external_id", "object_type": source}

    dms = call("/systems", {"vendor": "Frazer", "name": "Synthetic BHPH pilot"})["id"]
    crm = call("/systems", {"vendor": "Other CRM", "name": "Synthetic adjacent CRM"})["id"]
    accounting = call("/systems", {"vendor": "Other accounting/ERP", "name": "Synthetic accounting"})["id"]
    customer_map = mapping(dms, "Customer", "customers", ["first_name", "email"])
    customer_job = activate(customer_map, ["first_name", "email"], [("c1", ["Original customer", "pilot@example.invalid"])])
    vehicle_map = mapping(dms, "Vehicle", "vehicles", ["vin", "year", "price", "currency"])
    activate(vehicle_map, ["vin", "year", "price", "currency"], [("v1", ["1HGCM82633A004352", "2020", "15000.00", "USD"])])
    contract_map = mapping(dms, "FinanceContract", "contracts", ["principal", "currency", "status"],
        {"customer_id": ref("customers"), "vehicle_id": ref("vehicles")})
    activate(contract_map, ["customers", "vehicles", "principal", "currency", "status"], [("f1", ["c1", "v1", "10000.00", "USD", "active"])])
    account_map = mapping(dms, "LoanAccount", "accounts", ["balance", "currency"],
        {"customer_id": ref("customers"), "contract_id": ref("contracts"),
         "status": {"source": "account_state", "transform": "lookup", "values": {"A": "active"}}})
    account_job = activate(account_map, ["customers", "contracts", "balance", "currency", "account_state"],
        [("a1", ["c1", "f1", "9500.00", "USD", "A"])],
        expected={"row_count": 1, "totals": [{"field": "balance", "currency": "USD", "amount": "9500.00"}]})
    payment_columns = ["amount", "currency", "paid_at", "status", "principal_amount", "interest_amount", "fee_amount"]
    payment_map = mapping(dms, "Payment", "payments", payment_columns, {"account_id": ref("accounts")})
    activate(payment_map, ["accounts", *payment_columns],
        [("p1", ["a1", "500.00", "USD", "2026-10-01T12:00:00Z", "approved", "450.00", "40.00", "10.00"])],
        expected={"row_count": 1, "totals": [{"field": "amount", "currency": "USD", "amount": "500.00"}]})

    # Source schedules, reversals and collection/repo statuses remain observations.
    schedule_columns = ["due_at", "amount", "currency", "principal_amount", "interest_amount", "fee_amount", "status"]
    schedule_map = mapping(dms, "PaymentSchedule", "schedule", schedule_columns, {"account_id": ref("accounts")})
    activate(schedule_map, ["accounts", *schedule_columns], [
        ("s1", ["a1", "2026-11-01T12:00:00Z", "500.00", "USD", "450.00", "40.00", "10.00", "scheduled"]),
        ("s2", ["a1", "2026-12-01T12:00:00Z", "500.00", "USD", "455.00", "35.00", "10.00", "scheduled"])],
        expected={"row_count": 2, "totals": [{"field": "amount", "currency": "USD", "amount": "1000.00"}]})
    reversal_map = mapping(dms, "Payment", "payment_reversals", payment_columns,
        {"account_id": ref("accounts"), "reverses_payment_id": ref("payments")})
    reversal_columns = ["accounts", "payments", *payment_columns]
    reversal_rows = [("r1", ["a1", "p1", "-500.00", "USD", "2026-10-02T10:00:00Z", "reversed", "-450.00", "-40.00", "-10.00"])]
    reversal_job = activate(reversal_map, reversal_columns, reversal_rows,
        expected={"row_count": 1, "totals": [{"field": "amount", "currency": "USD", "amount": "-500.00"}]})
    activate(reversal_map, reversal_columns, reversal_rows)  # Replay must not reverse native money.
    collection_columns = ["status", "days_past_due", "past_due_amount", "currency", "next_action_at"]
    collection_map = mapping(dms, "CollectionCase", "collections", collection_columns, {"account_id": ref("accounts")})
    activate(collection_map, ["accounts", *collection_columns],
        [("case1", ["a1", "repossession_referral", "65", "1000.00", "USD", "2026-10-03T12:00:00Z"])])
    repo_map = mapping(dms, "Repossession", "repossessions", ["status", "occurred_at"],
        {"account_id": ref("accounts"), "vehicle_id": ref("vehicles")})
    activate(repo_map, ["accounts", "vehicles", "status", "occurred_at"],
        [("repo1", ["a1", "v1", "assigned", "2026-10-02T11:00:00Z"])])

    # Separate CRM identity must be explicitly linked and preserves current values.
    crm_map = mapping(crm, "Customer", "contacts", ["first_name", "email"])
    crm_job = call("/imports", {"mapping_id": crm_map, "content": csv_export(["first_name", "email"],
        [("crm1", ["Different CRM label", "pilot@example.invalid"])])})["id"]
    candidate = call(f"/imports/{crm_job}/validate", {})["rows"][0]["candidate_records"][0]
    call(f"/imports/{crm_job}/identity-review", {"row": 1, "target_id": candidate["id"],
        "review_token": candidate["review_token"], "reason": "Synthetic pilot verifies same customer across systems"}, human=True)
    call(f"/imports/{crm_job}/validate", {})
    call(f"/imports/{crm_job}/activate", {}, human=True); jobs.append(crm_job)
    assert ledger.get_entity(candidate["id"]).attributes["first_name"] == "Original customer"

    # A second accounting namespace imports chart accounts before journal lines.
    chart_map = mapping(accounting, "AccountingAccount", "chart", ["name", "account_code", "currency"])
    activate(chart_map, ["name", "account_code", "currency"], [("cash", ["Cash", "1000", "USD"]), ("receivable", ["Receivable", "1200", "USD"])])
    journal_map = mapping(accounting, "JournalEntry", "journal", ["account_code", "journal_id", "entry_side", "amount", "currency", "occurred_at"],
        {"ledger_account_id": ref("chart")})
    activate(journal_map, ["chart", "account_code", "journal_id", "entry_side", "amount", "currency", "occurred_at"],
        [("j1", ["cash", "1000", "journal-1", "debit", "500.00", "USD", "2026-10-01T12:00:00Z"]),
         ("j2", ["receivable", "1200", "journal-1", "credit", "500.00", "USD", "2026-10-01T12:00:00Z"])],
        expected={"row_count": 2, "balanced_journals": True, "totals": [{"field": "amount", "currency": "USD", "amount": "1000.00"}]})

    # Older history is retained, then replay is idempotent; native finances stay empty.
    activate(customer_map, ["first_name", "email"], [("c1", ["Older source name", "pilot@example.invalid"])], modified="2026-09-01T12:00:00Z")
    activate(customer_map, ["first_name", "email"], [("c1", ["Original customer", "pilot@example.invalid"])])
    before = call("/chrono/observations")["observations"]
    receipts = {job: call(f"/imports/{job}/report")["activation_receipt"] for job in jobs}
    assert len(before) == 16 and _all_payments() == [] and _all_loans() == []
    assert not any(entity.entity_type in {GL_ENTRY, BANK_TRANSACTION, REPOSSESSION_CASE} for entity in ledger.entities.values())
    assert receipts[account_job]["reconciliation"]["status"] == "matched"
    assert receipts[reversal_job]["reconciliation"]["status"] == "matched"
    account_history = call("/lineage", {"system_id": dms, "object_type": "accounts", "external_id": "a1"})
    assert account_history["current_values"]["balance"] == "9500.00"  # Payments never infer a new source balance.
    reversal_history = call("/lineage", {"system_id": dms, "object_type": "payment_reversals", "external_id": "r1"})
    original_history = call("/lineage", {"system_id": dms, "object_type": "payments", "external_id": "p1"})
    assert reversal_history["current_values"]["reverses_payment_id"] == original_history["canonical_id"]
    assert reversal_history["total_observations"] == 1
    assert len(receipts[crm_job]["identity_review_ids"]) == 1
    assert receipts[customer_job]["staged_principal"] == "api"
    ledger.reset(); load_graph(path)
    assert {job: call(f"/imports/{job}/report")["activation_receipt"] for job in jobs} == receipts
    assert registry.find_vehicle("1HGCM82633A004352") is not None
    lineage = call("/lineage", {"system_id": dms, "object_type": "customers", "external_id": "c1"})
    assert lineage["total_observations"] == 2 and lineage["current_values"]["first_name"] == "Original customer"

    class LocalSink:
        supports_idempotency = True
        def __init__(self): self.accepted = set()
        def deliver(self, *, workspace_id, events):
            assert workspace_id == ledger.tenant.workspace_id
            self.accepted.update(event.event_id for event in events)
            return DeliveryReceipt(tuple(event.event_id for event in events))
    sink = LocalSink(); outbox.bind_sink("Synthetic local sink", "pilot-v1", sink)
    call("/chrono/policy", {"enabled": True, "sink_name": "Synthetic local sink", "sink_revision": "pilot-v1"}, human=True)
    assert call("/chrono/deliver", {"limit": 100}, human=True)["delivered"] == len(before)
    ledger.reset(); load_graph(path)
    assert call("/chrono/deliver", {"limit": 100}, human=True)["status"] == "idle"
    assert len(sink.accepted) == len(before)
    assert [dict(value, delivery_status="pending") for value in call("/chrono/observations")["observations"]] == before
    assert call("/system-map")["writeback"] == "disabled"
