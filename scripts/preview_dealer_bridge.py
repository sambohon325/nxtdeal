"""Disposable loopback-only Dealer Bridge QA backend with synthetic records.

Usage: python scripts/preview_dealer_bridge.py --port 8303
Login: BRIDGE-QA-A / Bridge-QA-Only-2026! (or BRIDGE-QA-B for second approval).
Never use this server or its credentials as a production deployment.
"""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile


def create_preview(*, legacy_pending=False, event_batch=False, journal_collection=False, snapshot_restart=False, inbound_gateway=False, recovery_review=False, chrono_review=False, binding_review=False, relationship_review=False):
    # This function owns a fresh directory; it never reads a real tenant's files.
    directory = Path(tempfile.mkdtemp(prefix="nxtdeal-bridge-qa-data-"))
    os.environ["DEALEROS_STORAGE_DIR"] = str(directory)
    os.environ["DEALEROS_AUTH_SECRET"] = secrets.token_hex(32)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from core.auth import credential_store
    from core.auth_api import login
    from core import dealer_bridge as bridge, bridge_runtime, bridge_sync, bridge_chrono
    from core.bridge_contracts import SourceRecord, SyncPage
    from core.dealeros import ledger
    from core.entities import Entity
    from chrono.delivery import DeliveryReceipt
    from api.routers.dealer_bridge import router

    for employee in ("BRIDGE-QA-A", "BRIDGE-QA-B"):
        credential_store.set_credential(employee, "Bridge-QA-Only-2026!", "ADMIN", must_change_password=False)
    a = {"employee_id": "BRIDGE-QA-A", "role": "ADMIN", "bridge_principal": "session"}
    b = {"employee_id": "BRIDGE-QA-B", "role": "ADMIN", "bridge_principal": "session"}
    ledger.add_entity(Entity("QA-CUSTOMER", "Customer", {"FirstName": "Existing QA customer", "Email": "qa.customer@example.invalid"}))
    system = bridge.connect(a, "CSV", "Synthetic QA file source")["id"]
    mapping = bridge.propose_mapping(a, system, "Customer", "customers", {
        "first_name": {"source": "name", "transform": "text"}, "email": {"source": "email", "transform": "lower"}})["id"]
    bridge.approve_mapping(b, mapping)
    replacement = bridge.propose_mapping(a, system, "Customer", "customers", {
        "first_name": {"source": "name", "transform": "text"}, "email": {"source": "email", "transform": "lower"}})["id"]
    bridge.approve_mapping(b, replacement)
    job = bridge.stage(a, mapping, "external_id,modified_at,name,email\nqa-new,2026-10-03T12:00:00Z,New QA customer,new.customer@example.invalid\nqa-existing,2026-10-03T12:00:00Z,Existing source name,qa.customer@example.invalid\n", {"row_count": 2})["id"]
    bridge.validate(a, job)
    bridge.connect(a, "Frazer", "Frazer profile - awaiting authorized sample")

    class SyntheticReadConnector:
        capabilities = frozenset({"sync", "schema", "history", "health", "discover"})
        def discover(self):
            return ["customers"]
        def health(self):
            return {"status": "ready"}
        def schema(self, object_type):
            return ["external_id", "modified_at", "name", "email"]
        def sync(self, object_type, cursor):
            if cursor:
                return SyncPage((), cursor, True)
            return SyncPage((SourceRecord("customers", "qa-collected", "2026-10-03T13:00:00Z", {
                "name": "Synthetic collected customer", "email": "collector@example.invalid"}),), "qa-complete", True)
        def history(self, object_type, cursor):
            if cursor:
                return SyncPage((), cursor, True)
            return SyncPage((SourceRecord("customers", "qa-collected", "2026-09-01T13:00:00Z", {
                "name": "Earlier synthetic customer", "email": "collector@example.invalid"}),), "qa-history-complete", True)
    bridge_runtime.bind(system, SyntheticReadConnector(), revision="synthetic-qa-v1", objects=["customers"], environment="synthetic")
    bridge_sync.configure(a, mapping, False, 300)
    journal_mapping = bridge.propose_mapping(a, system, "JournalEntry", "journal_lines", {
        field: {"source": field, "transform": "text"}
        for field in ("account_code", "journal_id", "entry_side", "amount", "currency", "occurred_at")})["id"]
    bridge.approve_mapping(b, journal_mapping)
    account_mapping = bridge.propose_mapping(a, system, "LoanAccount", "accounts", {
        "customer_id": {"source": "customer", "transform": "external_id", "object_type": "customers"},
        "balance": {"source": "balance", "transform": "decimal"},
        "currency": {"source": "currency", "transform": "text"}})["id"]
    bridge.approve_mapping(b, account_mapping)
    payment_mapping = bridge.propose_mapping(a, system, "Payment", "payments", {
        "account_id": {"source": "account", "transform": "external_id", "object_type": "accounts"},
        **{field: {"source": field, "transform": "text"} for field in ("amount", "currency", "paid_at")}})["id"]
    bridge.approve_mapping(b, payment_mapping)
    update_seed = bridge.stage(a, mapping,
        "external_id,modified_at,name,email\nqa-update,2026-10-01T12:00:00Z,Original source customer,update@example.invalid\n")["id"]
    bridge.validate(a, update_seed)
    bridge.activate(b, update_seed)
    # Synthetic native-field edit demonstrates that review exposes divergent aliases.
    with bridge.mutation(b):
        target = next(entity for entity in ledger.get_all().values()
                      if entity.entity_type == "Customer" and entity.attributes.get("email") == "update@example.invalid")
        bridge.bridge_storage.touch(target.id)
        target.attributes["FirstName"] = "Edited in NXTDeal"

    if legacy_pending:
        # Optional synthetic legacy checkpoint, never a production graph edit.
        sync_state = bridge_sync.configure(a, mapping, False, 300)["id"]
        pending_job = bridge_sync.run_once(a, sync_state)["job_id"]
        bridge.validate(a, pending_job)
        bridge.activate(b, pending_job)
        with bridge.mutation(b):
            pending = bridge.get(pending_job, "BridgeJob")
            pending.pop("collection_page")
            receipt = pending["activation_receipt"]
            receipt.pop("collection_page")
            receipt["checksum"] = bridge.digest({key: value for key, value in receipt.items() if key != "checksum"})

    if event_batch:
        from core import bridge_event_profiles as event_profiles, bridge_event_imports as event_imports
        profile = event_profiles.propose(a, system, "QA Provider", {
            "first_name": {"source": "name_full", "transform": "text"},
            "email": {"source": "email", "transform": "lower"}})["id"]
        event_profiles.approve(b, profile)
        content = ('<adf><prospect><id source="QA Provider">qa-event-retention</id>'
                   '<requestdate>2026-10-04T10:00:00-05:00</requestdate><customer><contact>'
                   '<name part="full">Synthetic event lead</name><email>qa.event@example.invalid</email>'
                   '</contact></customer></prospect></adf>')
        event_job = event_imports.stage(a, profile, content)["id"]
        event_imports.validate(a, event_job)
        event_imports.activate(b, event_job)

    if journal_collection:
        class JournalQaConnector(SyntheticReadConnector):
            def discover(self): return ["customers", "journal_lines"]
            def schema(self, object_type):
                if object_type == "journal_lines":
                    return ["external_id", "modified_at", "account_code", "journal_id", "entry_side", "amount", "currency", "occurred_at"]
                return super().schema(object_type)
            def sync(self, object_type, cursor):
                if object_type != "journal_lines": return super().sync(object_type, cursor)
                if cursor: return SyncPage((), cursor, True)
                return SyncPage(tuple(SourceRecord("journal_lines", f"qa-journal-{side}", "2026-10-04T12:00:00Z", {
                    "account_code": account, "journal_id": "qa-complete-journal", "entry_side": side,
                    "amount": "10.00", "currency": "USD", "occurred_at": "2026-10-04T12:00:00Z"})
                    for side, account in (("debit", "1000"), ("credit", "2000"))), "qa-journal-complete", True)
            def history(self, object_type, cursor):
                return self.sync(object_type, cursor) if object_type == "journal_lines" else super().history(object_type, cursor)
        bridge_runtime.bind(system, JournalQaConnector(), revision="synthetic-qa-journal-v1", objects=["customers", "journal_lines"], environment="synthetic")
        bridge_sync.configure(a, mapping, False, 300, reviewed_binding_revision="synthetic-qa-journal-v1", reviewed_binding_environment="synthetic")
        bridge_sync.configure(a, journal_mapping, False, 300)

    if snapshot_restart:
        from core.bridge_adapters.export_file_paged import PagedExportFileConnector
        paged_system = bridge.connect(a, "CSV", "Synthetic replacement snapshot")["id"]
        paged_mapping = bridge.propose_mapping(a, paged_system, "Customer", "customers", {
            "first_name": {"source": "name", "transform": "text"},
            "email": {"source": "email", "transform": "lower"}})["id"]
        bridge.approve_mapping(b, paged_mapping)
        snapshot = directory / "synthetic-paged-customers.csv"
        header = "external_id,modified_at,name,email\n"
        rows = [f"paged-{index},2026-10-04T12:00:00Z,Synthetic page {index},paged{index}@example.invalid\n" for index in range(4)]
        snapshot.write_text(header + "".join(rows[:3]), encoding="utf-8", newline="")
        bridge_runtime.bind(paged_system, PagedExportFileConnector(snapshot, object_type="customers", page_size=2),
            revision="synthetic-paged-v1", objects=["customers"], environment="synthetic")
        paged_state = bridge_sync.configure(a, paged_mapping, False, 300)["id"]
        paged_job = bridge_sync.run_once(a, paged_state)["job_id"]
        bridge.validate(a, paged_job); bridge.activate(b, paged_job)
        bridge_sync.run_once(b, paged_state)
        snapshot.write_text(header + "".join(rows), encoding="utf-8", newline="")
        bridge_sync.run_once(b, paged_state)

    if recovery_review:
        recovery_job = bridge.stage(a, account_mapping,
            "external_id,modified_at,customer,balance,currency\nqa-dependent,2026-10-04T12:00:00Z,qa-parent-not-imported,1000.00,USD\n")["id"]
        bridge.validate(a, recovery_job)

    if inbound_gateway or recovery_review:
        from datetime import datetime, timedelta, timezone
        from core import bridge_inbound, bridge_event_profiles
        from core.bridge_credentials import CredentialBroker
        from core.bridge_adapters.adf_gateway import ADFGatewayVerifier
        gateway_system = bridge.connect(a, "CSV", "Synthetic signed ADF gateway")["id"]
        gateway_profile = bridge_event_profiles.propose(a, gateway_system, "QA Provider", {
            "first_name": {"source": "name_full", "transform": "text"}})["id"]
        bridge_event_profiles.approve(b, gateway_profile)
        class QaGatewaySecrets:
            def read(self, reference): return {"hmac_key": "synthetic-preview-key-no-production-use-0123456789"}
        broker = CredentialBroker()
        broker.grant(gateway_system, provider=QaGatewaySecrets(), reference="qa/gateway", account_ref="qa-gateway",
            environment="synthetic", objects=["adf_prospects"], expires_at=datetime.now(timezone.utc) + timedelta(hours=4))
        verifier = ADFGatewayVerifier(broker=broker, system_id=gateway_system, secret_reference="qa/gateway", account_ref="qa-gateway", environment="synthetic")
        endpoint = "synthetic_preview_gateway_0123456789"
        bridge_inbound.bind(endpoint, profile_id=gateway_profile, revision="synthetic-gateway-v1", environment="synthetic", verifier=verifier)
        bridge_inbound.configure(b, endpoint, True, "synthetic-gateway-v1")
        import hashlib, hmac
        from core.bridge_adapters.adf_gateway import signing_bytes
        body = ('<adf><prospect><id source="QA Provider">qa-signed-event</id>'
            '<requestdate>2026-10-04T12:00:00Z</requestdate><customer><contact>'
            '<name part="full">Synthetic signed lead</name></contact></customer></prospect></adf>').encode()
        signed_at, delivery_id = str(int(datetime.now(timezone.utc).timestamp())), "qa-delivery-1"
        signature = hmac.new(QaGatewaySecrets().read("qa/gateway")["hmac_key"].encode(), signing_bytes(endpoint, delivery_id, signed_at, body), hashlib.sha256).hexdigest()
        bridge_inbound.receive(endpoint, delivery_id, signed_at, signature, body)
        if recovery_review:
            former = "BRIDGE-QA-FORMER"
            credential_store.set_credential(former, "Bridge-QA-Only-2026!", "ADMIN", must_change_password=False)
            bridge_inbound.configure({**b, "employee_id": former}, endpoint, True, "synthetic-gateway-v1")
            credential_store.set_role(former, "SALES")


    class LocalQaSink:
        supports_idempotency = True
        fail_for_qa = False
        def deliver(self, *, workspace_id, events):
            if self.fail_for_qa: raise ValueError("Synthetic receipt review failure")
            path = directory / "synthetic_sink_receipts.json"
            existing = set(json.loads(path.read_text()) if path.exists() else [])
            existing.update(event.event_id for event in events)
            temporary = directory / "synthetic_sink_receipts.tmp"
            temporary.write_text(json.dumps(sorted(existing)), encoding="utf-8")
            os.replace(temporary, path)
            return DeliveryReceipt(tuple(event.event_id for event in events))
    local_sink = LocalQaSink()
    bridge_chrono.bind_sink("Local QA sink - no external service", "synthetic-qa-v1", local_sink)
    if chrono_review:
        content = "external_id,modified_at,name,email\n" + "".join(
            f"qa-delivery-{index},2026-10-04T12:00:00Z,Synthetic delivery {index},delivery-{index}@example.invalid\n" for index in range(28))
        delivery_job = bridge.stage(a, mapping, content)["id"]
        bridge.validate(a, delivery_job); bridge.activate(b, delivery_job)
        bridge_chrono.configure(b, True, "Local QA sink - no external service", "synthetic-qa-v1")
        local_sink.fail_for_qa = True
        bridge_chrono.deliver_once(b, limit=100)
        local_sink.fail_for_qa = False
    if relationship_review:
        related_system = bridge.connect(a, "CSV", "Synthetic borrower relationship review")["id"]
        def related_record(kind, object_type, external_id, values, activate=True):
            fields = {field: {"source": field, "transform": "text"} for field in values}
            related_mapping = bridge.propose_mapping(a, related_system, kind, object_type, fields)["id"]
            bridge.approve_mapping(b, related_mapping)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["external_id", "modified_at", *values])
            writer.writeheader()
            writer.writerow({"external_id": external_id, "modified_at": "2026-10-04T12:00:00Z", **values})
            related_job = bridge.stage(a, related_mapping, output.getvalue())["id"]
            bridge.validate(a, related_job)
            if not activate: return related_job
            bridge.activate(b, related_job)
            key = "BRX-" + bridge.digest([ledger.tenant.workspace_id, related_system, object_type, external_id])
            return bridge.get(key, "BridgeExternalID")["target_id"]
        primary = related_record("Customer", "customers", "qa-primary", {"first_name": "Synthetic contract borrower"})
        account_customer = related_record("Customer", "customers", "qa-account-customer", {"first_name": "Synthetic account borrower"})
        contract = related_record("FinanceContract", "contracts", "qa-contract", {"customer_id": primary, "currency": "USD", "principal": "1000.00"})
        related_record("LoanAccount", "accounts", "qa-account", {"customer_id": account_customer, "contract_id": contract, "currency": "USD", "balance": "1000.00"}, activate=False)
    if binding_review:
        current = bridge_runtime.binding(system)
        bridge_sync.configure(a, mapping, True, 300, reviewed_binding_revision=current.revision, reviewed_binding_environment=current.environment)
        bridge_runtime.bind(system, current.adapter, revision="synthetic-reviewed-replacement-v2", objects=current.objects, environment=current.environment)
    app = FastAPI(title="Disposable Dealer Bridge QA - synthetic data only")
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3303", "http://localhost:3303"], allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])
    app.include_router(router)
    class Login(BaseModel):
        employee_id: str
        password: str
    @app.post("/auth/login")
    def qa_login(body: Login):
        return login(body.employee_id, body.password, "127.0.0.1")
    @app.get("/qa-info")
    def info():
        return {"synthetic_only": True, "production_data_loaded": False}
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8303)
    parser.add_argument("--legacy-pending", action="store_true", help="Seed a synthetic legacy pending checkpoint for recovery QA")
    parser.add_argument("--event-batch", action="store_true", help="Seed a synthetic activated event batch for review QA")
    parser.add_argument("--journal-collection", action="store_true", help="Enable a synthetic complete-journal reader for policy QA")
    parser.add_argument("--snapshot-restart", action="store_true", help="Seed an unfinished changed local snapshot for restart QA")
    parser.add_argument("--inbound-gateway", action="store_true", help="Seed an enabled synthetic signed gateway for policy UI QA")
    parser.add_argument("--recovery-review", action="store_true", help="Seed missing parent references and expired administrator authority in synthetic QA")
    parser.add_argument("--chrono-review", action="store_true", help="Seed blocked synthetic delivery receipts for paginated recovery QA")
    parser.add_argument("--relationship-review", action="store_true", help="Seed a synthetic loan/contract customer difference for human review")
    parser.add_argument("--binding-review", action="store_true", help="Seed a changed synthetic connector requiring explicit revision review")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a non-privileged loopback port")
    import uvicorn
    uvicorn.run(create_preview(legacy_pending=args.legacy_pending, event_batch=args.event_batch, journal_collection=args.journal_collection, snapshot_restart=args.snapshot_restart, inbound_gateway=args.inbound_gateway, recovery_review=args.recovery_review, chrono_review=args.chrono_review, binding_review=args.binding_review, relationship_review=args.relationship_review), host="127.0.0.1", port=args.port)
