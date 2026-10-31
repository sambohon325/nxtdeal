"""Minimized runtime observations for reviewers; not security certification."""
from datetime import datetime, timezone
from core.permissions import ADMIN, OPERATIONS
from core.contracting_readiness import contracting_readiness
from core.workflow_readiness import workflow_readiness


def build_security_review(credential_records, *, demo):
    records = list(credential_records)
    enrolled = sum(record.get("mfa_enabled") is True for record in records)
    privileged = [record for record in records if record.get("role") in (ADMIN, OPERATIONS)]
    privileged_enrolled = sum(record.get("mfa_enabled") is True for record in privileged)
    return {
        "read_only": True, "production_verified": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "runtime_mode": "sample_data_only" if demo else "production_mode",
        "mfa": {
            "credential_records": len(records), "enrolled": enrolled,
            "not_enrolled": len(records) - enrolled,
            "admin_operations_records": len(privileged), "admin_operations_not_enrolled": len(privileged) - privileged_enrolled,
            "status": "no_records" if not records else "enrollment_gaps" if enrolled != len(records) else "enrollment_observed",
            "mandatory_enrollment_verified": False,
            "note": "Enrollment counts do not establish enforcement, recovery safety or complete staff coverage. Review roster ownership and offboarding separately.",
        },
        "verification_required": [
            {"control": "deployed_revision", "evidence": "Running image revision and reviewed release checks"},
            {"control": "tenant_isolation", "evidence": "Two-dealer negative access tests for records, files, sessions and agents"},
            {"control": "transport_encryption", "evidence": "Verified public and administration endpoints and certificate renewal"},
            {"control": "storage_encryption", "evidence": "Volume, database and backup encryption plus key access controls"},
            {"control": "backup_restore", "evidence": "Off-server backup coverage and a dated isolated restore exercise"},
            {"control": "incident_response", "evidence": "Named response owners, logging coverage and an exercised response plan"},
            {"control": "retention", "evidence": "Reviewed retention, legal hold and deletion procedures by data class"},
            {"control": "vendor_access", "evidence": "Scoped access rights, credential rotation and tested revocation"},
        ],
        "notice": "Runtime observations only. Missing external evidence remains unverified; a passing test or enrolled account does not establish production compliance.",
    }


def security_review_api(role):
    if role not in (ADMIN, OPERATIONS):
        return {"error": "Admin or Operations role required."}
    from core.auth import credential_store
    from core.json_graph_repository import demo_persistence_disabled
    report = build_security_review(credential_store.list_records(), demo=demo_persistence_disabled())
    report["contracting"] = contracting_readiness()
    report["workflows"] = workflow_readiness()
    return report
