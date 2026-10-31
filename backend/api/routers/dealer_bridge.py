"""Dealer bridge API: no credentials, tenant IDs or executable mapping code in bodies."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from api.deps import _authenticate, _bearer_token
from core.auth import verify_token, is_mfa_challenge_token
from core import dealer_bridge as bridge

router = APIRouter(prefix="/dealer-bridge", tags=["Dealer Data Bridge"])

def admin(authorization: str | None = Header(None)):
    actor, error = _authenticate(authorization)
    if error:
        raise HTTPException(401, "Authenticated administrator required")
    session = verify_token(_bearer_token(authorization))
    actor = {**actor, "bridge_principal": "session" if session and not is_mfa_challenge_token(session) else "api"}
    try:
        bridge.authorize(actor)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return actor

def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except bridge.bridge_storage.PersistenceUnavailable as exc:
        raise HTTPException(503, "Bridge storage is unavailable. Check storage, reload the current state and review it before retrying.") from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except bridge.bridge_storage.PersistenceConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")
class System(Strict):
    vendor: str
    name: str = Field(min_length=1, max_length=120)
class HealthCheck(Strict):
    pass
class OnboardingDetails(Strict):
    product_version: str = Field(max_length=120)
    deployment: Literal["unknown", "cloud", "on_premise", "hosted", "file_only"]
    record_types: list[str] = Field(max_length=100)
    evidence: dict[str, Literal["unknown", "requested", "available", "not_applicable"]]
class OnboardingUpdate(Strict):
    revision: int = Field(ge=0, strict=True)
    details: OnboardingDetails
class Mapping(Strict):
    system_id: str
    kind: str
    object_type: str = Field(min_length=1, max_length=120)
    fields: dict[str, dict[str, str | dict[str, str]]]
    source_columns: dict[str, str] | None = None
class ExpectedTotal(Strict):
    field: str
    currency: str = Field(pattern="^[A-Za-z]{3}$")
    amount: str = Field(min_length=1, max_length=64)
class ExpectedImport(Strict):
    row_count: int | None = Field(default=None, ge=0, le=1000, strict=True)
    totals: list[ExpectedTotal] = Field(default_factory=list, max_length=30)
    balanced_journals: bool = Field(default=False, strict=True)
class Import(Strict):
    file_format: Literal["csv", "tsv", "json"] = "csv"
    mapping_id: str
    content: str = Field(max_length=1_000_000)
    expectations: ExpectedImport | None = None
class MappingTest(Strict):
    file_format: Literal["csv", "tsv", "json"] = "csv"
    content: str = Field(max_length=1_000_000)
    expectations: ExpectedImport | None = None
class Write(Strict):
    system_id: str
    target_id: str
    changes: dict = Field(max_length=50)
class FileDiscovery(Strict):
    file_format: Literal["csv", "tsv", "json"] = "csv"
    kind: str
    content: str = Field(max_length=1_000_000)
class SchemaDiscovery(Strict):
    kind: str
    object_type: str = Field(min_length=1, max_length=120)
class LineageLookup(Strict):
    system_id: str
    object_type: str = Field(min_length=1, max_length=120)
    external_id: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=25, ge=1, le=100, strict=True)
    before_event_id: str | None = Field(default=None, min_length=68, max_length=68)

@router.post("/lineage")
def source_lineage(body: LineageLookup, actor=Depends(admin)):
    from core.bridge_lineage import lookup
    return call(lookup, actor, body.system_id, body.object_type, body.external_id, body.limit, body.before_event_id)

@router.post("/systems/{system_id}/discover-schema")
def discover_schema(system_id: str, body: SchemaDiscovery, actor=Depends(admin)):
    from core.bridge_discovery import discover_bound_schema
    return call(discover_bound_schema, actor, system_id, body.kind, body.object_type)

@router.post("/systems/{system_id}/health-check")
def check_health(system_id: str, body: HealthCheck, actor=Depends(admin)):
    from core.bridge_health import check
    return call(check, actor, system_id)

@router.get("/systems/{system_id}/onboarding")
def onboarding(system_id: str, actor=Depends(admin)):
    from core.bridge_onboarding import read
    return call(read, actor, system_id)

@router.post("/systems/{system_id}/onboarding")
def update_onboarding(system_id: str, body: OnboardingUpdate, actor=Depends(admin)):
    from core.bridge_onboarding import update
    return call(update, actor, system_id, body.revision, body.details.model_dump())

@router.post("/systems/{system_id}/discover-file")
def discover_file(system_id: str, body: FileDiscovery, actor=Depends(admin)):
    from core.bridge_discovery import discover_file as inspect
    return call(inspect, actor, system_id, body.kind, body.content, body.file_format)

@router.get("/system-map")
def system_map(actor=Depends(admin)):
    return call(bridge.system_map, actor)

@router.get("/review-queue")
def review_queue(system_id: str | None = Query(None,min_length=1,max_length=120),
                 status: Literal["pending","all","staged","validated","blocked","activated","cancelled"] = "pending",
                 kind: Literal["all","snapshot","event"] = "all", limit: int = Query(25,ge=1,le=100),
                 before_id: str | None = Query(None,min_length=1,max_length=120), actor=Depends(admin)):
    from core.bridge_review_queue import read
    return call(read,actor,system_id,status,kind,limit,before_id)
@router.get("/systems/{system_id}/import-order")
def import_order(system_id: str, actor=Depends(admin)):
    from core.bridge_plan import import_order as plan
    return call(plan, actor, system_id)
@router.post("/systems")
def connect(body: System, actor=Depends(admin)):
    return call(bridge.connect, actor, body.vendor, body.name)
@router.post("/mappings")
def mapping(body: Mapping, actor=Depends(admin)):
    return call(bridge.propose_mapping, actor, body.system_id, body.kind, body.object_type, body.fields, body.source_columns)
@router.post("/mappings/{mapping_id}/approve")
def approve(mapping_id: str, actor=Depends(admin)):
    return call(bridge.approve_mapping, actor, mapping_id)
@router.post("/mappings/{mapping_id}/test")
def test_mapping(mapping_id: str, body: MappingTest, actor=Depends(admin)):
    return call(bridge.simulate_mapping, actor, mapping_id, body.content, body.expectations.model_dump() if body.expectations else None, body.file_format)
@router.post("/imports")
def stage(body: Import, actor=Depends(admin)):
    return call(bridge.stage, actor, body.mapping_id, body.content, body.expectations.model_dump() if body.expectations else None, body.file_format)
@router.post("/imports/{job_id}/validate")
def validate(job_id: str, actor=Depends(admin)):
    return {"rows": call(bridge.validate, actor, job_id)}
@router.post("/imports/{job_id}/activate")
def activate(job_id: str, actor=Depends(admin)):
    return call(bridge.activate, actor, job_id)
@router.get("/chrono/observations")
def observations(actor=Depends(admin)):
    return {"observations": call(bridge.chrono_observations, actor)}
@router.post("/write-proposals")
def writes(body: Write, actor=Depends(admin)):
    return call(bridge.propose_write, actor, body.system_id, body.target_id, body.changes)

@router.post("/migrations/v1")
def migrate(actor=Depends(admin)):
    from core.dealer_bridge_migrations import migrate as run_migration
    return call(run_migration, actor)


class IdentityReview(Strict):
    row: int = Field(ge=1, le=1000, strict=True)
    target_id: str
    review_token: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=8, max_length=500)

@router.post("/imports/{job_id}/identity-review")
def identity_review(job_id: str, body: IdentityReview, actor=Depends(admin)):
    return call(bridge.resolve_identity, actor, job_id, body.row, body.target_id, body.review_token, body.reason)


class Reason(Strict):
    reason: str = Field(min_length=8, max_length=500)

class PayloadCleanup(Reason):
    review_token: str = Field(min_length=64, max_length=64)

@router.get("/imports/{job_id}/payload-cleanup")
def payload_cleanup_preview(job_id: str, actor=Depends(admin)):
    from core.bridge_retention import preview
    return call(preview, actor, job_id)

@router.post("/imports/{job_id}/payload-cleanup")
def payload_cleanup(job_id: str, body: PayloadCleanup, actor=Depends(admin)):
    from core.bridge_retention import cleanup
    return call(cleanup, actor, job_id, body.review_token, body.reason)
class SeparateIdentityReview(Reason):
    row: int = Field(ge=1, le=1000, strict=True)
    candidate_tokens: dict[str, str] = Field(min_length=1, max_length=1000)
class WithdrawIdentityReview(Reason):
    row: int = Field(ge=1, le=1000, strict=True)

@router.post("/imports/{job_id}/identity-withdraw")
def identity_withdraw(job_id: str, body: WithdrawIdentityReview, actor=Depends(admin)):
    return call(bridge.withdraw_identity_review, actor, job_id, body.row, body.reason)

@router.post("/imports/{job_id}/identity-separate")
def identity_separate(job_id: str, body: SeparateIdentityReview, actor=Depends(admin)):
    return call(bridge.keep_identity_separate, actor, job_id, body.row, body.candidate_tokens, body.reason)

class PauseSystem(Reason):
    paused: bool = Field(strict=True)

@router.post("/systems/{system_id}/pause")
def pause_system(system_id: str, body: PauseSystem, actor=Depends(admin)):
    return call(bridge.set_system_paused, actor, system_id, body.paused, body.reason)

@router.post("/mappings/{mapping_id}/revoke")
def revoke_mapping(mapping_id: str, body: Reason, actor=Depends(admin)):
    return call(bridge.revoke_mapping, actor, mapping_id, body.reason)

@router.post("/imports/{job_id}/cancel")
def cancel_import(job_id: str, body: Reason, actor=Depends(admin)):
    return call(bridge.cancel_import, actor, job_id, body.reason)

@router.get("/imports/{job_id}/report")
def import_report(job_id: str, actor=Depends(admin)):
    return call(bridge.import_report, actor, job_id)


class SyncConfiguration(Strict):
    mapping_id: str
    enabled: bool = Field(default=False, strict=True)
    interval_seconds: int = Field(default=300, ge=60, le=86400, strict=True)
    mode: Literal["sync", "history"] = "sync"
    require_balanced_journals: bool | None = Field(default=None, strict=True)
    reviewed_binding_revision: str | None = Field(default=None, min_length=1, max_length=120)
    reviewed_binding_environment: Literal["unspecified", "synthetic", "local_file", "sandbox", "production"] | None = None
class MappingTransitionPreview(Strict):
    mapping_id: str
class MappingTransition(Reason):
    mapping_id: str
    review_token: str = Field(min_length=64, max_length=64)

@router.post("/sync/{state_id}/mapping-transition/preview")
def preview_sync_mapping(state_id: str, body: MappingTransitionPreview, actor=Depends(admin)):
    from core import bridge_sync
    return call(bridge_sync.transition_preview, actor, state_id, body.mapping_id)

@router.post("/sync/{state_id}/mapping-transition")
def transition_sync_mapping(state_id: str, body: MappingTransition, actor=Depends(admin)):
    from core import bridge_sync
    return call(bridge_sync.transition_mapping, actor, state_id, body.mapping_id, body.review_token, body.reason)

@router.get("/sync")
def sync_states(actor=Depends(admin)):
    from core import bridge_sync
    return {"states": call(bridge_sync.states, actor)}

@router.post("/sync")
def configure_sync(body: SyncConfiguration, actor=Depends(admin)):
    from core import bridge_sync
    return call(bridge_sync.configure, actor, body.mapping_id, body.enabled, body.interval_seconds, body.mode, body.require_balanced_journals, reviewed_binding_revision=body.reviewed_binding_revision, reviewed_binding_environment=body.reviewed_binding_environment)

@router.post("/sync/{state_id}/run")
def run_sync(state_id: str, actor=Depends(admin)):
    from core import bridge_sync
    return call(bridge_sync.run_once, actor, state_id)

@router.post("/sync/{state_id}/retry")
def retry_sync(state_id: str, body: Reason, actor=Depends(admin)):
    from core import bridge_sync
    return call(bridge_sync.retry, actor, state_id, body.reason)


class ChronoPolicy(Strict):
    enabled: bool = Field(strict=True)
    sink_name: str | None = Field(default=None, max_length=120)
    sink_revision: str | None = Field(default=None, max_length=120)
class DeliveryBatch(Strict):
    limit: int = Field(default=50, ge=1, le=100, strict=True)

@router.get("/chrono/status")
def chrono_status(actor=Depends(admin)):
    from core import bridge_chrono
    return call(bridge_chrono.status, actor)

@router.get("/chrono/receipts")
def chrono_receipts(actor=Depends(admin)):
    from core import bridge_chrono
    return {"receipts": call(bridge_chrono.receipts, actor)}

@router.get("/chrono/receipt-queue")
def chrono_receipt_queue(status: Literal["unacknowledged", "all", "blocked", "retrying", "in_flight", "delivered"] = "unacknowledged",
                         limit: int = Query(25, ge=1, le=100),
                         before_id: str | None = Query(None, min_length=1, max_length=120), actor=Depends(admin)):
    from core import bridge_chrono_review
    return call(bridge_chrono_review.read, actor, status, limit, before_id)


@router.post("/chrono/policy")
def chrono_policy(body: ChronoPolicy, actor=Depends(admin)):
    from core import bridge_chrono
    return call(bridge_chrono.configure, actor, body.enabled, body.sink_name, body.sink_revision)

@router.post("/chrono/deliver")
def chrono_deliver(body: DeliveryBatch, actor=Depends(admin)):
    from core import bridge_chrono
    return call(bridge_chrono.deliver_once, actor, body.limit)

class ChronoRetry(Reason):
    receipt_id: str | None = Field(None, min_length=1, max_length=120)


@router.post("/chrono/observations/{event_id}/retry")
def chrono_retry(event_id: str, body: ChronoRetry, actor=Depends(admin)):
    from core import bridge_chrono
    return call(bridge_chrono.retry, actor, event_id, body.reason, body.receipt_id)


class ADFDiscovery(Strict):
    content: str = Field(min_length=1, max_length=1_000_000)


@router.post("/systems/{system_id}/discover-adf")
def discover_adf(system_id: str, body: ADFDiscovery, actor=Depends(admin)):
    from core.bridge_discovery import discover_adf as inspect
    return call(inspect, actor, system_id, body.content)


class EventProfile(Strict):
    system_id: str
    id_source: str = Field(min_length=1, max_length=120)
    fields: dict[str, dict[str, str]]


@router.get("/systems/{system_id}/event-profiles")
def event_profiles(system_id: str, actor=Depends(admin)):
    from core.bridge_event_profiles import list_profiles
    return {"profiles": call(list_profiles, actor, system_id)}


@router.post("/event-profiles")
def propose_event_profile(body: EventProfile, actor=Depends(admin)):
    from core.bridge_event_profiles import propose
    return call(propose, actor, body.system_id, body.id_source, body.fields)


@router.post("/event-profiles/{profile_id}/approve")
def approve_event_profile(profile_id: str, actor=Depends(admin)):
    from core.bridge_event_profiles import approve
    return call(approve, actor, profile_id)


@router.post("/event-profiles/{profile_id}/revoke")
def revoke_event_profile(profile_id: str, body: Reason, actor=Depends(admin)):
    from core.bridge_event_profiles import revoke
    return call(revoke, actor, profile_id, body.reason)


@router.post("/event-profiles/{profile_id}/test")
def test_event_profile(profile_id: str, body: ADFDiscovery, actor=Depends(admin)):
    from core.bridge_event_profiles import simulate
    return call(simulate, actor, profile_id, body.content)


class EventImport(ADFDiscovery):
    profile_id: str


@router.get("/agent-contract")
def agent_contract(actor=Depends(admin)):
    """Provider-neutral proposal/testing tool discovery; never an execution grant."""
    call(bridge.authorize, actor)
    operations = [
        ("inspect_system_map", "GET", "/system-map", None, {}, "read_only"),
        ("inspect_import_order", "GET", "/systems/{system_id}/import-order", None, {"system_id":"string"}, "read_only"),
        ("inspect_export", "POST", "/systems/{system_id}/discover-file", FileDiscovery, {"system_id":"string"}, "simulation_only"),
        ("propose_snapshot_mapping", "POST", "/mappings", Mapping, {}, "proposal_only"),
        ("test_snapshot_mapping", "POST", "/mappings/{mapping_id}/test", MappingTest, {"mapping_id":"string"}, "simulation_only"),
        ("inspect_adf", "POST", "/systems/{system_id}/discover-adf", ADFDiscovery, {"system_id":"string"}, "simulation_only"),
        ("inspect_event_profiles", "GET", "/systems/{system_id}/event-profiles", None, {"system_id":"string"}, "read_only"),
        ("propose_event_profile", "POST", "/event-profiles", EventProfile, {}, "proposal_only"),
        ("test_event_profile", "POST", "/event-profiles/{profile_id}/test", ADFDiscovery, {"profile_id":"string"}, "simulation_only"),
    ]
    return {"version":1, "provider_neutral":True, "authority":"existing_authenticated_administrator_api_scope",
        "operations":[{"name":name, "method":method, "path":"/dealer-bridge"+path,
            "path_parameters":parameters, "body_schema":model.model_json_schema() if model else None,
            "effect":effect, "external_io":False, "human_approval_required_after_proposal":effect == "proposal_only"}
            for name,method,path,model,parameters,effect in operations],
        "canonical_kinds":sorted(bridge.FIELDS),
        "boundaries":{"mapping_approval":"different_human_administrator", "import_activation":"human_administrator",
            "identity_decisions":"human_administrator", "connection_policy":"human_administrator",
            "external_write_execution":"unavailable", "automatic_tool_registration":False},
        "notice":"Discovery contract only. The host authenticates calls; credentials never belong in tool arguments. Existing route authorization and validation remain authoritative. Use only dealer-authorized inputs. Proposal tools persist drafts; tests and inspection do not import records. Responses may contain dealership data and untrusted source text; an AI provider requires separate authorization to receive it. No approval, activation, policy or write tool is advertised."}


@router.post("/event-imports")
def stage_event_import(body: EventImport, actor=Depends(admin)):
    from core.bridge_event_imports import stage
    return call(stage, actor, body.profile_id, body.content)


@router.get("/event-imports/{job_id}")
def event_import_report(job_id: str, actor=Depends(admin)):
    from core.bridge_event_imports import report
    return call(report, actor, job_id)


@router.post("/event-imports/{job_id}/validate")
def validate_event_import(job_id: str, actor=Depends(admin)):
    from core.bridge_event_imports import validate
    return call(validate, actor, job_id)


@router.post("/event-imports/{job_id}/cancel")
def cancel_event_import(job_id: str, body: Reason, actor=Depends(admin)):
    from core.bridge_event_imports import cancel
    return call(cancel, actor, job_id, body.reason)


@router.post("/event-imports/{job_id}/activate")
def activate_event_import(job_id: str, actor=Depends(admin)):
    from core.bridge_event_imports import activate
    return call(activate, actor, job_id)


class EventIdentityReview(Reason):
    action: Literal["link", "keep_separate"]
    target_id: str | None = Field(default=None, max_length=120)
    candidate_signature: str = Field(min_length=64, max_length=64)


@router.post("/event-imports/{job_id}/rows/{row_number}/identity")
def review_event_identity(job_id: str, row_number: int, body: EventIdentityReview, actor=Depends(admin)):
    from core.bridge_event_imports import review_identity
    return call(review_identity, actor, job_id, row_number, body.action, body.target_id, body.reason, body.candidate_signature)


@router.post("/event-imports/{job_id}/rows/{row_number}/identity/withdraw")
def withdraw_event_identity(job_id: str, row_number: int, body: Reason, actor=Depends(admin)):
    from core.bridge_event_imports import withdraw_identity
    return call(withdraw_identity, actor, job_id, row_number, body.reason)


@router.get("/systems/{system_id}/event-imports")
def event_imports(system_id: str, limit: int = 25, before_id: str | None = None, actor=Depends(admin)):
    from core.bridge_event_imports import list_jobs
    return call(list_jobs, actor, system_id, limit, before_id)


class EventLineage(Strict):
    system_id: str
    source_namespace: str = Field(min_length=1, max_length=120)
    external_id: str = Field(min_length=1, max_length=500)


@router.post("/event-lineage")
def event_lineage(body: EventLineage, actor=Depends(admin)):
    from core.bridge_event_imports import lineage
    return call(lineage, actor, body.system_id, body.source_namespace, body.external_id)


class SyncRecovery(Reason):
    review_token: str = Field(min_length=64, max_length=64)


@router.get("/sync/{state_id}/replay-preview")
def preview_sync_replay(state_id: str, actor=Depends(admin)):
    from core import bridge_sync_recovery
    return call(bridge_sync_recovery.preview, actor, state_id)


@router.post("/sync/{state_id}/replay")
def replay_sync(state_id: str, body: SyncRecovery, actor=Depends(admin)):
    from core import bridge_sync_recovery
    return call(bridge_sync_recovery.replay, actor, state_id, body.review_token, body.reason)


class ExportPreflight(Strict):
    file_format: Literal["csv", "tsv", "json"] = "csv"
    content: str = Field(max_length=1_000_000)


@router.post("/mappings/{mapping_id}/preflight")
def preflight_export(mapping_id: str, body: ExportPreflight, actor=Depends(admin)):
    from core.bridge_preflight import inspect
    return call(inspect, actor, mapping_id, body.content, body.file_format)


@router.get("/systems/{system_id}/activity")
def system_activity(system_id: str, limit: int = 25, before_id: str | None = None, actor=Depends(admin)):
    from core.bridge_activity import read
    return call(read, actor, system_id, limit, before_id)


@router.get("/event-imports/{job_id}/payload-cleanup")
def event_payload_cleanup_preview(job_id: str, actor=Depends(admin)):
    from core.bridge_event_retention import preview
    return call(preview, actor, job_id)


@router.post("/event-imports/{job_id}/payload-cleanup")
def event_payload_cleanup(job_id: str, body: PayloadCleanup, actor=Depends(admin)):
    from core.bridge_event_retention import cleanup
    return call(cleanup, actor, job_id, body.review_token, body.reason)


@router.get("/event-observations/{event_id}")
def event_observation_lineage(event_id: str, actor=Depends(admin)):
    from core.bridge_event_imports import observation_lineage
    return call(observation_lineage, actor, event_id)


@router.get("/systems/{system_id}/discover-objects")
def discover_objects(system_id: str, actor=Depends(admin)):
    from core.bridge_discovery import discover_bound_objects
    return call(discover_bound_objects, actor, system_id)


@router.get("/sync/{state_id}/snapshot-restart-preview")
def preview_snapshot_restart(state_id: str, actor=Depends(admin)):
    from core import bridge_snapshot_restart
    return call(bridge_snapshot_restart.preview, actor, state_id)


@router.post("/sync/{state_id}/snapshot-restart")
def restart_snapshot(state_id: str, body: SyncRecovery, actor=Depends(admin)):
    from core import bridge_snapshot_restart
    return call(bridge_snapshot_restart.restart, actor, state_id, body.review_token, body.reason)


class InboundPolicy(Strict):
    enabled: bool = Field(strict=True)
    revision: str | None = Field(default=None, min_length=1, max_length=120)
    review_token: str | None = Field(default=None, min_length=64, max_length=64)


@router.get("/systems/{system_id}/inbound")
def inbound_status(system_id: str, actor=Depends(admin)):
    from core import bridge_inbound
    return call(bridge_inbound.status, actor, system_id)


@router.post("/inbound/{endpoint_id}/policy")
def configure_inbound(endpoint_id: str, body: InboundPolicy, actor=Depends(admin)):
    from core import bridge_inbound
    return call(bridge_inbound.configure, actor, endpoint_id, body.enabled, body.revision, body.review_token)


from api.routers.bridge_inbound import router as inbound_delivery_router
router.include_router(inbound_delivery_router)
