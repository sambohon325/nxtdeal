"""
NXTDeal Hub (session 50) -- the internal app NXTDeal employees/developers use to launch
new dealerships on NXTDeal and see how the network as a whole is doing.

Run from within hub/ (matches how backend/api/app.py is run from within backend/):
    cd hub && python -m uvicorn app:app --reload --port 9000

Auth (real per-employee login, 2026-07-23): Hub staff log in via
POST /hub/auth/login (username/password) and get a signed Bearer session token
(hub_core/auth.py's issue_token, the vendored copy of the backend's own token
scheme). Every admin-gated route depends on require_hub_admin, which requires a
valid Bearer token whose role is ADMIN -- the single role all Hub staff share.
Credentials are PBKDF2-hashed (hub_core/auth.py's CredentialStore) and persisted to
hub/storage/hub_credentials.json (hub_core/hub_credentials_storage.py). The first
admin is env-seeded on startup from HUB_ADMIN_USERNAME/HUB_ADMIN_PASSWORD (see the
lifespan bootstrap below), created with must_change_password=True.

The old single shared-secret header (X-NXTDeal-Hub-Key / NXTDEAL_HUB_KEY) survives
ONLY as an env-gated break-glass: it is accepted by require_hub_admin exclusively
when HUB_BREAK_GLASS is armed (off by default). A normal production Hub runs on
employee logins alone. See _check_hub_key/require_hub_admin below.
"""

import hmac
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from hub_core.cors_policy import HUB_WEB_ORIGINS, LEGACY_HUB_ORIGIN_REGEX
from pydantic import BaseModel, Field
from typing import Optional

from hub_core.dealer_storage import save_dealers, load_dealers
from hub_core.dealers_api import (
    create_dealer_api,
    adopt_dealer_api,
    list_dealers_api,
    get_dealer_api,
    update_dealer_status_api,
    update_dealer_api_base_url_api,
    get_dealer_management_overview_api,
    update_dealer_profile_api,
    update_dealer_subscription_api,
    update_dealer_version_api,
    resolve_dealer_api,
    DEALERS_PATH
)
from hub_core.infra_provisioning_api import (
    provision_dealer_api,
    provision_status_api,
    provisioning_config_api
)
from hub_core.infra_provisioning_storage import (
    load_provisioning,
    PROVISIONING_PATH
)
from hub_core.demo_leads_api import (
    signup_api as demo_lead_signup_api,
    login_api as demo_lead_login_api,
    request_reset_api as demo_lead_request_reset_api,
    reset_password_api as demo_lead_reset_password_api,
    list_leads_api as demo_lead_list_api,
    config_api as demo_lead_config_api
)
from hub_core.demo_leads_storage import (
    load_demo_accounts,
    DEMO_ACCOUNTS_PATH
)
from hub_core.network_aggregator import network_overview
from hub_core.network_collector import collect_network_snapshots
from hub_core.network_snapshot_storage import save_network_snapshots, load_network_snapshots
from hub_core.network_analytics import compute_network_analytics
from hub_core.server_health import get_server_health_overview
from hub_core.noc import get_noc_status_board
from hub_core.dealer_modules_api import (
    get_module_catalog_api,
    get_dealer_modules_api,
    set_dealer_module_api,
    DEALER_MODULES_PATH,
)
from hub_core.dealer_modules_storage import save_dealer_modules, load_dealer_modules
from hub_core.feature_flags_api import (
    list_feature_flag_scopes_api,
    list_feature_flag_overrides_api,
    create_feature_flag_override_api,
    delete_feature_flag_override_api,
    resolve_feature_flag_api,
    FEATURE_FLAGS_PATH,
)
from hub_core.feature_flags_storage import save_feature_flags, load_feature_flags
from hub_core.dealer_onboarding_api import (
    get_onboarding_catalog_api,
    list_onboarding_summaries_api,
    get_dealer_onboarding_api,
    recheck_dealer_onboarding_api,
    set_dealer_onboarding_step_api,
    DEALER_ONBOARDING_PATH,
)
from hub_core.dealer_onboarding_storage import save_dealer_onboarding, load_dealer_onboarding
from hub_core.dealer_migration_api import (
    get_migration_catalog_api,
    list_migration_summaries_api,
    get_dealer_migration_api,
    set_dealer_migration_source_api,
    set_dealer_readiness_api,
    DEALER_MIGRATIONS_PATH,
)
from hub_core.dealer_migration_storage import save_dealer_migrations, load_dealer_migrations
from hub_core.dealer_integrations_api import (
    get_integrations_catalog_api,
    get_dealer_integrations_api,
    add_dealer_integration_api,
    update_dealer_integration_api,
    remove_dealer_integration_api,
    DEALER_INTEGRATIONS_PATH,
)
from hub_core.dealer_integrations_storage import save_dealer_integrations, load_dealer_integrations
from hub_core.dealer_ai_management_api import (
    get_ai_area_catalog_api,
    get_dealer_ai_management_api,
    recheck_dealer_ai_management_api,
    DEALER_AI_SNAPSHOTS_PATH,
)
from hub_core.dealer_ai_management_storage import save_dealer_ai_snapshots, load_dealer_ai_snapshots
from hub_core.dealer_network_membership_api import (
    get_network_membership_catalog_api,
    get_dealer_network_membership_api,
    set_dealer_network_tier_api,
    recheck_dealer_pipeline_connectivity_api,
)
from hub_core.dealer_network_membership_storage import load_dealer_network_membership
from hub_core.dealer_support_api import (
    get_dealer_support_status_api,
    recheck_dealer_support_snapshot_api,
)
from hub_core.dealer_support_storage import load_dealer_support
from hub_core.hub_audit_api import get_audit_catalog_api, list_audit_events_api, get_dealer_audit_summary_api
from hub_core.hub_audit_storage import load_hub_audit_log
from hub_core.dealer_contacts_api import (
    get_users_catalog_api,
    get_dealer_users_api,
    add_dealer_contact_api,
    remove_dealer_contact_api,
)
from hub_core.dealer_contacts_storage import load_dealer_contacts
from hub_core.hub_platform_metrics import record_request as record_hub_platform_metrics_request
from hub_core.infra_overview import get_infra_overview
from hub_core.platform_status import get_platform_status_board
from hub_core.infra_services import (
    get_services_overview,
    get_dealer_platform_metrics,
    recheck_dealer_platform_metrics,
)
from hub_core.clusters import get_clusters_overview
from hub_core.tenant_storage_metrics import recheck_dealer_storage
from hub_core.databases import (
    get_databases_overview,
    get_dealer_databases,
)
from hub_core.hub_storage_status import get_storage_overview
from hub_core.dealer_backups_api import (
    get_backups_overview_api,
    get_dealer_backups_api,
    log_dealer_backup_api,
    DEALER_BACKUPS_LOG_PATH,
)
from hub_core.dealer_backups_storage import load_dealer_backups_log
from hub_core.disaster_recovery import get_disaster_recovery_status
from hub_core.infra_ai import (
    get_ai_infrastructure_overview,
    recheck_all_dealer_ai_infrastructure,
)
from hub_core.infra_network_health import (
    get_network_health_overview,
    run_privacy_audit,
)
from hub_core.infra_messaging import get_messaging_overview
from hub_core.infra_security import get_security_overview
from hub_core.infra_monitoring import get_monitoring_overview
from hub_core.network_connect_api import (
    get_connector_catalog_api,
    get_migration_readiness_catalog_api,
    get_kpi_catalog_api,
    signup_network_connect_account_api,
    get_network_connect_account_api,
    set_connected_system_api,
    set_tier_api,
    set_status_api,
    set_migration_readiness_api,
    get_network_connect_account_admin_api,
    list_network_connect_accounts_api,
    get_network_connect_overview_api,
    convert_account_to_dealer_api,
    submit_kpi_snapshot_api,
    get_benchmark_api,
    NETWORK_CONNECT_ACCOUNTS_PATH,
)
from hub_core.network_connect_storage import load_network_connect_accounts
from hub_core.dealer_ai_kill_switch_api import (
    get_dealer_kill_switch_status_api,
    push_dealer_kill_switch_api,
    get_dealer_kill_switch_history_api,
    get_all_kill_switch_history_api,
    DEALER_AI_KILL_SWITCH_ACTIONS_PATH,
)
from hub_core.dealer_ai_kill_switch_storage import load_dealer_ai_kill_switch_actions
from hub_core.code_auditor_api import (
    get_code_audit_catalog_api,
    get_code_audit_overview_api,
    run_code_audit_scan_api,
    list_code_audit_findings_api,
    get_code_audit_finding_api,
    list_code_audit_runs_api,
    get_code_audit_run_api,
    approve_code_audit_finding_api,
    reject_code_audit_finding_api,
    resolve_code_audit_finding_api,
    dismiss_code_audit_finding_api,
    CODE_AUDIT_FINDINGS_PATH,
    CODE_AUDIT_RUNS_PATH,
)
from hub_core.code_auditor_storage import load_code_audit_findings, load_code_audit_runs
from hub_core.code_auditor_scheduler import (
    start as start_code_auditor_scheduler,
    stop as stop_code_auditor_scheduler,
    get_scheduler_status as get_code_auditor_scheduler_status,
)
from hub_core.secrets import get_secret, warn_on_dev_fallbacks
from hub_core.secrets_api import get_secrets_posture_api
from hub_core.auth import (
    credential_store,
    issue_token,
    verify_token,
)
from hub_core.hub_credentials_storage import (
    save_hub_credentials,
    load_hub_credentials,
)


_HUB_KEY_ENV_VAR = "NXTDEAL_HUB_KEY"
_DEV_FALLBACK_KEY = "dev-only-insecure-hub-key-change-me"


def _check_hub_key(x_nxtdeal_hub_key: Optional[str]):

    # Reads through hub_core/secrets.py's real chokepoint (Task #13, 2026-07-20)
    # rather than os.environ directly, so a production Hub deployment still running
    # on this dev fallback is centrally, automatically detectable
    # (hub_core.secrets.get_secrets_posture()) instead of only discoverable by
    # reading this module's own source.
    expected = get_secret(_HUB_KEY_ENV_VAR, _DEV_FALLBACK_KEY)

    # Constant-time compare so the secret can't be recovered by timing the response, and never
    # accept the public dev fallback as a real credential (a Hub still on it is a misconfig, not
    # an auth path). get_secrets_posture() still surfaces the fallback centrally.
    if expected == _DEV_FALLBACK_KEY or not hmac.compare_digest(x_nxtdeal_hub_key or "", expected):
        raise HTTPException(status_code=401, detail="invalid or missing X-NXTDeal-Hub-Key")


# ---------------------------------------------------------------------------
# Real per-employee Hub login (2026-07-23) -- replaces the single shared-secret
# X-NXTDeal-Hub-Key gate above as the normal way Hub staff authenticate. The
# shared key survives ONLY as an env-gated break-glass (HUB_BREAK_GLASS), off by
# default. See hub_core/auth.py (vendored CredentialStore/token primitives) and
# hub_core/hub_credentials_storage.py (persistence). Mirrors the Bearer-token +
# ADMIN-role shape backend/api/deps.py established for the tenant-side backend.
# ---------------------------------------------------------------------------

_ADMIN_ROLE = "ADMIN"

_BREAK_GLASS_ENV_VAR = "HUB_BREAK_GLASS"
_HUB_ADMIN_USERNAME_ENV_VAR = "HUB_ADMIN_USERNAME"
_HUB_ADMIN_PASSWORD_ENV_VAR = "HUB_ADMIN_PASSWORD"

# Own file under hub/storage/, same "own concern, own file" convention as every
# other Hub sub-registry (dealers.json, network_snapshots.json, ...).
HUB_CREDENTIALS_PATH = "storage/hub_credentials.json"


def _bearer_token(authorization):
    """Pulls the token out of an `Authorization: Bearer <token>` header. Mirrors
    backend/api/deps.py's _bearer_token() -- returns None on a missing/malformed
    header. Tokens ride the Authorization header (not a query param) so they don't
    leak into server/proxy access logs."""

    if not authorization:
        return None

    parts = authorization.split(" ", 1)

    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


def _break_glass_enabled():
    """Whether the old shared-key break-glass path is armed. Off by default -- a
    real production Hub runs on employee logins alone. Read through the same
    secrets chokepoint as every other Hub secret; any common truthy spelling counts."""

    value = get_secret(_BREAK_GLASS_ENV_VAR, None)

    return bool(value) and value.strip().lower() in ("1", "true", "yes", "on")


def require_hub_admin(
    authorization: Optional[str] = Header(default=None),
    x_nxtdeal_hub_key: Optional[str] = Header(default=None),
):
    """The Hub's admin gate, as a FastAPI dependency. Normal path: a valid,
    unexpired Bearer session token whose role is ADMIN (every Hub staff member is
    ADMIN -- single role by decision). Break-glass path: ONLY when HUB_BREAK_GLASS
    is armed, the legacy X-NXTDeal-Hub-Key shared secret is also accepted, granting
    a synthetic break-glass admin. Off by default. Raises 401 otherwise. Returns the
    token payload (or the synthetic break-glass identity) so a route can `admin:
    dict = Depends(require_hub_admin)` and know who's calling."""

    token = _bearer_token(authorization)

    if token:
        payload = verify_token(token)

        if payload and payload.get("role") == _ADMIN_ROLE:
            return payload

    if _break_glass_enabled():
        # Reuses _check_hub_key -- it either returns (key matched) or raises 401.
        _check_hub_key(x_nxtdeal_hub_key)

        return {
            "employee_id": "break-glass",
            "role": _ADMIN_ROLE,
            "break_glass": True,
        }

    raise HTTPException(status_code=401, detail="admin authentication required")


# The Code Auditor's real, scheduled background scan (2026-07-19) -- Sam:
# "and have a scheduled run / analysis." Same modern FastAPI lifespan=
# context manager convention backend/api/app.py already established for
# its own two schedulers (hub_core/bot_scheduler.py/hub_core/compliance_scheduler.py)
# rather than the deprecated @app.on_event("startup"/"shutdown") pair --
# everything before the `yield` runs on startup, everything after runs on
# shutdown. See hub_core/code_auditor_scheduler.py for what the tick does and
# its documented single-process/in-memory limitations. This is the first
# background scheduler on the Hub side of this codebase.
@asynccontextmanager
async def lifespan(app: FastAPI):

    # hub_core/secrets.py Task #13, 2026-07-20 -- same real, loud, impossible-to-miss
    # stderr warning backend/api/app.py's own lifespan() prints on boot, mirrored
    # here for the Hub's own three secrets (NXTDEAL_HUB_KEY/DEALEROS_NETWORK_KEY/
    # DEALEROS_AUTH_SECRET).
    warn_on_dev_fallbacks()

    # Real per-employee Hub login bootstrap (2026-07-23). Load any persisted Hub
    # credentials, then env-seed the first admin: if HUB_ADMIN_USERNAME +
    # HUB_ADMIN_PASSWORD are both set, ensure that ADMIN credential exists.
    #
    # Idempotency choice (the SAFE option): seed ONLY when the username doesn't
    # already exist. We deliberately do NOT re-upsert on every boot -- doing so
    # would reset the password back to the env value and flip must_change_password
    # back to True on every restart, silently undoing an admin who has since
    # changed their own password. First creation sets must_change_password=True so
    # the seeded admin is forced to set a real password on first login.
    load_hub_credentials(HUB_CREDENTIALS_PATH)

    _admin_username = get_secret(_HUB_ADMIN_USERNAME_ENV_VAR, None)
    _admin_password = get_secret(_HUB_ADMIN_PASSWORD_ENV_VAR, None)

    if _admin_username and _admin_password:
        if credential_store.get_record(_admin_username) is None:
            credential_store.set_credential(
                _admin_username,
                _admin_password,
                role=_ADMIN_ROLE,
                must_change_password=True,
                created_by="env_bootstrap",
            )
            save_hub_credentials(HUB_CREDENTIALS_PATH)

    start_code_auditor_scheduler()

    yield

    stop_code_auditor_scheduler()


app = FastAPI(lifespan=lifespan)

from hub_core.mysales_personal import router as mysales_personal_router
app.include_router(mysales_personal_router)
from hub_core.mysales_assistants import router as mysales_assistants_router
app.include_router(mysales_assistants_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=HUB_WEB_ORIGINS,
    # Session 87 -- same fix as backend/api/app.py: once a real Hub UI exists at
    # hub.dealeros.xyz (see docs/DEPLOYMENT.md), it needs to call this API from the
    # browser. Regex covers the whole *.dealeros.xyz family so it doesn't need another
    # code change per subdomain added later.
    allow_origin_regex=LEGACY_HUB_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# Sam (2026-07-16): same noindex posture as backend/api/app.py -- see that file's
# add_robots_header for the full rationale. Same env-var name/convention so one flip
# per deployment covers both the frontend and whichever backend(s) sit behind it.
_ALLOW_INDEXING = os.environ.get("DEALEROS_ALLOW_INDEXING", "").lower() == "true"


@app.middleware("http")
async def add_robots_header(request: Request, call_next):
    response = await call_next(request)
    if not _ALLOW_INDEXING:
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


# Infrastructure & Platform Operations rebuild, slice 1 (2026-07-19) -- real,
# lightweight, in-process request/error/latency instrumentation for the
# Hub's OWN routes. See hub_core/hub_platform_metrics.py's own module docstring
# for the full honesty posture (in-memory only, resets on restart, real
# route-group mapping, no fabricated infra telemetry).
import time as _hub_platform_metrics_time


@app.middleware("http")
async def track_hub_platform_metrics(request: Request, call_next):
    started = _hub_platform_metrics_time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        latency_ms = (_hub_platform_metrics_time.monotonic() - started) * 1000
        record_hub_platform_metrics_request(request.url.path, 500, latency_ms)
        raise
    latency_ms = (_hub_platform_metrics_time.monotonic() - started) * 1000
    record_hub_platform_metrics_request(request.url.path, response.status_code, latency_ms)
    return response


load_dealers(DEALERS_PATH)

load_provisioning(PROVISIONING_PATH)

load_demo_accounts(DEMO_ACCOUNTS_PATH)

# Same directory-relative convention as DEALERS_PATH above -- lives in hub/storage/,
# a SEPARATE file from dealers.json on purpose (see
# hub_core/network_snapshot_storage.py's module docstring for why that separation is part
# of the anonymization design, not just file organization).
NETWORK_SNAPSHOTS_PATH = "storage/network_snapshots.json"
load_network_snapshots(NETWORK_SNAPSHOTS_PATH)

# Dealer Management rebuild, slice 2 -- Module Management + Feature Flags. Two
# more SEPARATE files under hub/storage/, same "own concern, own file"
# convention as dealers.json/network_snapshots.json above.
load_dealer_modules(DEALER_MODULES_PATH)
load_feature_flags(FEATURE_FLAGS_PATH)

# Dealer Management rebuild, slice 3 -- Onboarding Center + Migration
# Tracking (the "Provisioning" menu item). Same "own concern, own file"
# convention as every other Hub sub-registry above.
load_dealer_onboarding(DEALER_ONBOARDING_PATH)
load_dealer_migrations(DEALER_MIGRATIONS_PATH)

# Dealer Management rebuild, slice 4 of 5 -- Integrations Center + AI
# Management (per dealer). Same "own concern, own file" convention as every
# other Hub sub-registry above.
load_dealer_integrations(DEALER_INTEGRATIONS_PATH)
load_dealer_ai_snapshots(DEALER_AI_SNAPSHOTS_PATH)

# Dealer Management rebuild, slice 5 of 5 (FINAL) -- Network Membership /
# Support Center / Audit Center / Users. Same "own concern, own file"
# convention as every other Hub sub-registry above. hub_audit.json is
# loaded FIRST among these four so every one of the retrofitted
# record_and_save() calls inside the *_api.py modules above has a correctly
# recovered id counter before any of this slice's own routes can fire.
DEALER_NETWORK_MEMBERSHIP_PATH = "storage/dealer_network_membership.json"
DEALER_SUPPORT_PATH = "storage/dealer_support.json"
HUB_AUDIT_LOG_PATH = "storage/hub_audit.json"
DEALER_CONTACTS_PATH = "storage/dealer_contacts.json"

load_hub_audit_log(HUB_AUDIT_LOG_PATH)
load_dealer_network_membership(DEALER_NETWORK_MEMBERSHIP_PATH)
load_dealer_support(DEALER_SUPPORT_PATH)
load_dealer_contacts(DEALER_CONTACTS_PATH)

# Infrastructure & Platform Operations rebuild, slice 2 of 4 -- Clusters /
# Databases / Storage / Backups / Disaster Recovery. Only Backups needs its
# own persisted file (the honest-manual backup-confirmation log) -- Clusters/
# Databases/Storage/Disaster Recovery are all pure real-time compositions
# over already-loaded state (dealer registry, server_health, and
# tenant_storage_metrics's own deliberately-NOT-persisted in-memory
# registry, see that module's own docstring for why).
load_dealer_backups_log(DEALER_BACKUPS_LOG_PATH)

# NXTDeal Network Connect (2026-07-19) -- Hub backend foundation. Own file,
# same "own concern, own file" convention as every other Hub sub-registry
# above. See hub_core/network_connect.py's own module docstring for the full
# privacy design (identified account records here vs. the completely
# separate, already-loaded anonymized network_snapshots.json pool above).
load_network_connect_accounts(NETWORK_CONNECT_ACCOUNTS_PATH)

# AI-Powered Self-Auditing Code Layer (2026-07-19) -- two separate files
# (findings/runs), same reasoning hub_core/code_auditor_storage.py's own
# docstring states: separately queried in practice, smaller recovery blast
# radius on corruption.
load_code_audit_findings(CODE_AUDIT_FINDINGS_PATH)
load_code_audit_runs(CODE_AUDIT_RUNS_PATH)

# Security-hardening pass, Task #6 (2026-07-20) -- the append-only
# emergency-push action log (hub_core/dealer_ai_kill_switch.py). Own file,
# same "own concern, own file" convention as every other Hub sub-registry
# above -- kill-switch status itself is never persisted here (always a real,
# live fetch, see that module's own docstring for why).
load_dealer_ai_kill_switch_actions(DEALER_AI_KILL_SWITCH_ACTIONS_PATH)


class CreateDealerRequest(BaseModel):
    name: str
    contact_email: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    plan_tier: str = "Standard"
    network_opt_in: bool = True


class AdoptDealerRequest(BaseModel):
    name: str
    contact_email: str
    storage_dir: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    plan_tier: str = "Standard"
    network_opt_in: bool = True
    api_base_url: Optional[str] = None


class UpdateStatusRequest(BaseModel):
    status: str


class UpdateApiBaseUrlRequest(BaseModel):
    api_base_url: str


class UpdateDealerProfileRequest(BaseModel):
    group: Optional[str] = None
    oem: Optional[str] = None
    location_count: Optional[int] = None
    industry_type: Optional[str] = None
    region: Optional[str] = None


class UpdateDealerSubscriptionRequest(BaseModel):
    plan_tier: Optional[str] = None
    active_modules: Optional[list] = None
    renewal_date: Optional[str] = None
    seat_count: Optional[int] = None


class UpdateDealerVersionRequest(BaseModel):
    current_release: Optional[str] = None
    beta_programs: Optional[list] = None


class LogDealerBackupRequest(BaseModel):
    logged_by: str
    label: Optional[str] = None
    note: Optional[str] = None


class SetDealerModuleRequest(BaseModel):
    module_key: str
    enabled: bool


class CreateFeatureFlagOverrideRequest(BaseModel):
    flag_key: str
    scope: str
    enabled: bool
    scope_target: Optional[str] = None
    note: Optional[str] = None


class SetOnboardingStepRequest(BaseModel):
    step_key: str
    complete: bool
    note: Optional[str] = None


class SetMigrationSourceRequest(BaseModel):
    migrating_from: Optional[str] = None
    other_note: Optional[str] = None


class SetReadinessRequest(BaseModel):
    category: str
    pct: float
    note: Optional[str] = None


class AddDealerIntegrationRequest(BaseModel):
    provider_key: str
    connection_health: str = "healthy"
    data_flow: str = "bidirectional"
    sync_frequency: str = "daily"
    active: bool = True
    notes: Optional[str] = None
    custom_label: Optional[str] = None


class UpdateDealerIntegrationRequest(BaseModel):
    connection_health: Optional[str] = None
    data_flow: Optional[str] = None
    sync_frequency: Optional[str] = None
    active: Optional[bool] = None
    notes: Optional[str] = None
    custom_label: Optional[str] = None


class SetNetworkTierRequest(BaseModel):
    tier: str


class AddDealerContactRequest(BaseModel):
    name: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None


class SignupNetworkConnectRequest(BaseModel):
    company_name: str
    contact_email: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None


class SetConnectedSystemRequest(BaseModel):
    category: str
    provider_key: Optional[str] = None


class GetBenchmarkRequest(BaseModel):
    pseudonym: str


class SetNetworkConnectTierRequest(BaseModel):
    tier: str


class SetNetworkConnectStatusRequest(BaseModel):
    status: str


class SetNetworkConnectReadinessRequest(BaseModel):
    category: str
    pct: float
    note: Optional[str] = None


class ConvertToDealerRequest(BaseModel):
    plan_tier: str = "Standard"


class SubmitKpiSnapshotRequest(BaseModel):
    pseudonym: str
    departments: dict


class PushKillSwitchRequest(BaseModel):
    pushed_by: str
    scope: str
    active: bool
    reason: Optional[str] = None
    department: Optional[str] = None


class RunCodeAuditScanRequest(BaseModel):
    triggered_by: str = "nxtdeal_staff"
    areas: Optional[list] = None


class ApproveCodeAuditFindingRequest(BaseModel):
    approved_by: str
    note: Optional[str] = None


class RejectCodeAuditFindingRequest(BaseModel):
    rejected_by: str
    note: Optional[str] = None


class ResolveCodeAuditFindingRequest(BaseModel):
    resolved_by: str
    note: Optional[str] = None


class DismissCodeAuditFindingRequest(BaseModel):
    dismissed_by: str
    note: str


@app.get("/")
def root():
    return {"service": "NXTDeal Hub", "dealers": len(list_dealers_api())}


# ---------------------------------------------------------------------------
# Hub staff login (2026-07-23). These three routes are intentionally NOT behind
# require_hub_admin -- login is how a staff member obtains the Bearer token that
# gets them past that gate; whoami/change-password authenticate the Bearer token
# themselves. Mirrors backend/api/app.py's /auth/login, /auth/whoami,
# /auth/change-password shapes.
# ---------------------------------------------------------------------------


class HubLoginRequest(BaseModel):
    username: str
    password: str


class HubChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@app.post("/hub/auth/login")
def hub_auth_login(request: HubLoginRequest):
    """Body {username, password}. `username` may be the seeded employee_id or an
    email on file (CredentialStore.resolve_identifier). Returns {token, role,
    must_change_password} on success, 401 on bad credentials."""

    role = credential_store.authenticate(request.username, request.password)

    if not role:
        raise HTTPException(status_code=401, detail="invalid credentials")

    employee_id = credential_store.resolve_identifier(request.username)
    token = issue_token(employee_id, role)

    record = credential_store.get_record(employee_id)
    must_change_password = bool(record and record.get("must_change_password"))

    return {
        "token": token,
        "role": role,
        "must_change_password": must_change_password,
    }


@app.get("/hub/auth/whoami")
def hub_auth_whoami(authorization: Optional[str] = Header(default=None)):
    """Bearer-token identity check. Returns {employee_id, role,
    must_change_password}, 401 on a missing/invalid/expired token."""

    token = _bearer_token(authorization)
    payload = verify_token(token) if token else None

    if not payload:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    record = credential_store.get_record(payload["employee_id"])
    must_change_password = bool(record and record.get("must_change_password"))

    return {
        "employee_id": payload["employee_id"],
        "role": payload["role"],
        "must_change_password": must_change_password,
    }


@app.post("/hub/auth/change-password")
def hub_auth_change_password(
    request: HubChangePasswordRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Bearer-authenticated self-service password change (also how a seeded admin
    completes their forced first-login change). Body {old_password, new_password}.
    Requires knowing the current password. Clears must_change_password on success."""

    token = _bearer_token(authorization)
    payload = verify_token(token) if token else None

    if not payload:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    success = credential_store.change_password(
        payload["employee_id"],
        request.old_password,
        request.new_password,
    )

    if not success:
        raise HTTPException(status_code=400, detail="current password is incorrect")

    save_hub_credentials(HUB_CREDENTIALS_PATH)

    return {"ok": True, "token": issue_token(payload["employee_id"], payload["role"])}


@app.post("/hub/dealers")
def create_dealer_route(
    request: CreateDealerRequest,
    admin: dict = Depends(require_hub_admin)
):

    result = create_dealer_api(**request.dict())

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Auto-provision-on-create: when COOLIFY_AUTO_PROVISION is set on hub-api, immediately
    # create + deploy the new dealer's stack in Coolify (attached as result["provisioning"]).
    # A provisioning error never fails the create — the dealer record still exists to retry.
    if os.environ.get("COOLIFY_AUTO_PROVISION", "").strip().lower() in ("1", "true", "yes", "on"):
        dealer_id = (result.get("dealer") or {}).get("dealer_id")
        if dealer_id:
            result["provisioning"] = provision_dealer_api(dealer_id)

    return result


@app.post("/hub/dealers/adopt")
def adopt_dealer_route(
    request: AdoptDealerRequest,
    admin: dict = Depends(require_hub_admin)
):

    result = adopt_dealer_api(**request.dict())

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


# PUBLIC (no require_hub_admin): the shared apps host apps.dealeros.xyz calls this from
# the browser at sign-in to learn which dealer backend to route a login to. Safe to be
# unauthenticated -- see resolve_dealer_api's docstring (public subdomain + name only, no
# enumeration, no data). CORS already permits the whole *.dealeros.xyz family.
@app.get("/hub/public/resolve/{identifier}")
def resolve_dealer_route(identifier: str):
    result = resolve_dealer_api(identifier)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# AI-demo leads + accounts (2026-07-25). PUBLIC sign-up/login/reset for the demo's lead-gen
# form (the demo tenant is non-persistent, so leads live here in the Hub). Sign-up verifies
# Cloudflare Turnstile when TURNSTILE_SECRET_KEY is set. Admin can list the captured leads.
# ---------------------------------------------------------------------------
class DemoSignupRequest(BaseModel):

    name: str
    email: str
    password: str
    persona: str
    position: Optional[str] = None
    dealership: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    username: Optional[str] = None
    turnstile_token: Optional[str] = None


class DemoLoginRequest(BaseModel):

    identifier: str
    password: str


class DemoForgotRequest(BaseModel):

    email: str


class DemoResetRequest(BaseModel):

    email: str
    token: str
    new_password: str


@app.get("/hub/public/demo/config")
def demo_lead_config_route():
    """Whether Turnstile is enforced (so the form knows to render the widget)."""
    return demo_lead_config_api()


@app.post("/hub/public/demo/signup")
def demo_lead_signup_route(request: DemoSignupRequest, http_request: Request):
    client_ip = http_request.client.host if http_request.client else None
    result = demo_lead_signup_api(**request.dict(), remoteip=client_ip)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/public/demo/login")
def demo_lead_login_route(request: DemoLoginRequest):
    result = demo_lead_login_api(request.identifier, request.password)
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
    return result


@app.post("/hub/public/demo/forgot")
def demo_lead_forgot_route(request: DemoForgotRequest):
    return demo_lead_request_reset_api(request.email)


@app.post("/hub/public/demo/reset")
def demo_lead_reset_route(request: DemoResetRequest):
    result = demo_lead_reset_password_api(request.email, request.token, request.new_password)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/demo/leads")
def demo_lead_list_route(admin: dict = Depends(require_hub_admin)):
    """Admin/Hub-console: every captured demo lead (profile + timestamps, no credentials)."""
    return demo_lead_list_api()


@app.get("/hub/dealers")
def list_dealers_route(admin: dict = Depends(require_hub_admin)):
    return list_dealers_api()


@app.get("/hub/dealers/{dealer_id}")
def get_dealer_route(dealer_id: str, admin: dict = Depends(require_hub_admin)):
    result = get_dealer_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/dealers/{dealer_id}/status")
def update_dealer_status_route(
    dealer_id: str,
    request: UpdateStatusRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = update_dealer_status_api(dealer_id, request.status)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/dealers/{dealer_id}/api-base-url")
def update_dealer_api_base_url_route(
    dealer_id: str,
    request: UpdateApiBaseUrlRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = update_dealer_api_base_url_api(dealer_id, request.api_base_url)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Dealer infrastructure auto-provisioning (2026-07-24) -- create + deploy a dealer's
# frontend + API in Coolify from the Hub, then record its api_base_url. Admin-gated.
# Safe when Coolify isn't configured: /provision returns a clear error and changes nothing.
# ---------------------------------------------------------------------------
@app.get("/hub/provisioning/config")
def provisioning_config_route(admin: dict = Depends(require_hub_admin)):
    """Is Coolify auto-provisioning configured on hub-api? Lists any missing COOLIFY_* env."""
    return provisioning_config_api()


@app.post("/hub/dealers/{dealer_id}/provision")
def provision_dealer_route(dealer_id: str, admin: dict = Depends(require_hub_admin)):
    """Create + deploy this dealer's frontend + API in Coolify and record its api_base_url."""
    result = provision_dealer_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/dealers/{dealer_id}/provision-status")
def provision_status_route(dealer_id: str, live: bool = False, admin: dict = Depends(require_hub_admin)):
    """The dealer's provisioning record; ?live=true also polls Coolify for each app's status."""
    return provision_status_api(dealer_id, live=live)


# ---------------------------------------------------------------------------
# Dealer Management rebuild (2026-07-19) -- Overview KPIs/lifecycle funnel, plus
# the real Dealer Record (Profile / Subscription Info / NXTDeal Version) editable
# sections. See hub_core/dealer_overview.py + hub_core/dealer_profile.py for the real
# composition/mutation logic these routes are thin wrappers over.
# ---------------------------------------------------------------------------

@app.get("/hub/dealer-management/overview")
def dealer_management_overview_route(
    admin: dict = Depends(require_hub_admin)
):
    return get_dealer_management_overview_api()


@app.post("/hub/dealers/{dealer_id}/profile")
def update_dealer_profile_route(
    dealer_id: str,
    request: UpdateDealerProfileRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = update_dealer_profile_api(dealer_id, **request.dict())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/dealers/{dealer_id}/subscription")
def update_dealer_subscription_route(
    dealer_id: str,
    request: UpdateDealerSubscriptionRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = update_dealer_subscription_api(dealer_id, **request.dict())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/dealers/{dealer_id}/version")
def update_dealer_version_route(
    dealer_id: str,
    request: UpdateDealerVersionRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = update_dealer_version_api(dealer_id, **request.dict())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/network/overview")
def network_overview_route(admin: dict = Depends(require_hub_admin)):
    return network_overview()


@app.post("/hub/network/collect")
def network_collect_route(admin: dict = Depends(require_hub_admin)):
    """Triggers one collection pass right now (pulls every opted-in dealer's
    anonymized snapshot -- see hub_core/network_collector.py) rather than waiting for a
    scheduled tick, since this Hub has no background scheduler yet (unlike the
    per-dealer backend's bot/compliance schedulers) -- deliberately simple for this
    pass, a real periodic collector is real, valuable future work."""
    result = collect_network_snapshots()
    save_network_snapshots(NETWORK_SNAPSHOTS_PATH)
    return result


@app.get("/hub/network/analytics")
def network_analytics_route(admin: dict = Depends(require_hub_admin)):
    return compute_network_analytics()


@app.get("/hub/health/overview")
def health_overview_route(admin: dict = Depends(require_hub_admin)):
    return get_server_health_overview()


# ---------------------------------------------------------------------------
# NOC (Network Operations Center) restructure -- Sam's own parallel-to-the-
# Network-department ask, closing task #8 of the Intelligence Network
# rebuild's autonomous run. One unified real-time status board (hub_core/noc.py)
# composing the same real signals the Dealers/Network/Server Health tabs
# already surface separately, plus a real transparent Alerts feed derived
# from them -- not a new monitoring engine, a real composition layer.
# ---------------------------------------------------------------------------

@app.get("/hub/noc/overview")
def noc_overview_route(admin: dict = Depends(require_hub_admin)):
    return get_noc_status_board()


# ---------------------------------------------------------------------------
# Infrastructure & Platform Operations rebuild, slice 1 of 4 -- menu shell +
# Overview + Platform Status Board + Services. Sam's rename of the old
# "Server Health" tab: this platform will eventually run thousands of
# dealer tenants, so this becomes a real, if today small-scale, "Azure
# Status Page"-style control surface (hub_core/infra_overview.py, hub_core/
# platform_status.py, hub_core/infra_services.py -- see each module's own
# docstring for the honest real-vs-not-yet-applicable reasoning, since
# fabricating CPU/node/cluster telemetry is a materially different, riskier
# kind of dishonesty than this codebase's established "simulate a real
# market/peer-data gap, disclose it" policy). Static path
# ("/hub/infra/services") registered before the dynamic
# "/hub/infra/services/{dealer_id}" path, same route-shadowing-avoidance
# convention as every other block in this file.
# ---------------------------------------------------------------------------

@app.get("/hub/infra/overview")
def infra_overview_route(admin: dict = Depends(require_hub_admin)):
    return get_infra_overview()


@app.get("/hub/infra/platform-status")
def infra_platform_status_route(admin: dict = Depends(require_hub_admin)):
    return get_platform_status_board()


@app.get("/hub/infra/services")
def infra_services_overview_route(admin: dict = Depends(require_hub_admin)):
    return get_services_overview()


@app.get("/hub/infra/services/{dealer_id}")
def infra_dealer_services_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result, error = get_dealer_platform_metrics(dealer_id)
    if error:
        raise HTTPException(status_code=404, detail=error)
    return result


@app.post("/hub/infra/services/{dealer_id}/recheck")
def infra_recheck_dealer_services_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    """Live HTTP round trip to this dealer's own new
    /network/platform-metrics-snapshot endpoint -- not run automatically on
    every GET, same reasoning as every other live tenant-fetch recheck
    action in this file (Onboarding's Network Connected, AI Management,
    Support Center)."""
    snapshot, error = recheck_dealer_platform_metrics(dealer_id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return snapshot.to_dict()


# ---------------------------------------------------------------------------
# Infrastructure & Platform Operations rebuild, slice 2 of 4 -- Clusters /
# Databases / Storage / Backups / Disaster Recovery. See hub_core/clusters.py,
# hub_core/databases.py, hub_core/hub_storage_status.py, hub_core/dealer_backups.py, and
# hub_core/disaster_recovery.py for the full real-vs-honest-gap reasoning --
# never fabricated CPU/node/replication telemetry, same standing rule as
# slice 1. Databases and Storage share ONE real live-fetch engine
# (hub_core/tenant_storage_metrics.py) -- the recheck action lives under
# /hub/infra/storage/{dealer_id}/recheck and both panels' data reflects the
# same fetch. Static paths ("/hub/infra/clusters", ".../databases",
# ".../storage", ".../backups", ".../disaster-recovery") are all registered
# before any dynamic "{dealer_id}" sibling, same route-shadowing-avoidance
# convention as every other block in this file.
# ---------------------------------------------------------------------------

@app.get("/hub/infra/clusters")
def infra_clusters_route(admin: dict = Depends(require_hub_admin)):
    return get_clusters_overview()


@app.get("/hub/infra/databases")
def infra_databases_overview_route(admin: dict = Depends(require_hub_admin)):
    return get_databases_overview()


@app.get("/hub/infra/databases/{dealer_id}")
def infra_dealer_databases_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result, error = get_dealer_databases(dealer_id)
    if error:
        raise HTTPException(status_code=404, detail=error)
    return result


@app.get("/hub/infra/storage")
def infra_storage_overview_route(admin: dict = Depends(require_hub_admin)):
    return get_storage_overview()


@app.post("/hub/infra/storage/{dealer_id}/recheck")
def infra_recheck_dealer_storage_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    """The one real live-fetch action shared by BOTH the Databases and
    Storage panels (hub_core/tenant_storage_metrics.py) -- a live HTTP round
    trip to this dealer's own /network/storage-snapshot, or, only for
    today's one co-located dev tenant, a clearly-labeled Hub-local
    filesystem read (see that module's own docstring). Not run
    automatically on every GET, same reasoning as every other live
    tenant-fetch recheck action in this file."""
    snapshot, error = recheck_dealer_storage(dealer_id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return snapshot.to_dict()


@app.get("/hub/infra/backups")
def infra_backups_overview_route(admin: dict = Depends(require_hub_admin)):
    return get_backups_overview_api()


@app.get("/hub/infra/backups/{dealer_id}")
def infra_dealer_backups_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_dealer_backups_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/infra/backups/{dealer_id}/log")
def infra_log_dealer_backup_route(
    dealer_id: str,
    request: LogDealerBackupRequest,
    admin: dict = Depends(require_hub_admin)
):
    """Real, NXTDeal-staff-maintained manual log entry -- see
    hub_core/dealer_backups.py's own module docstring for why this exists
    alongside the real, fetched observed-backups figures above."""
    result = log_dealer_backup_api(
        dealer_id,
        logged_by=request.logged_by,
        label=request.label,
        note=request.note,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/infra/disaster-recovery")
def infra_disaster_recovery_route(admin: dict = Depends(require_hub_admin)):
    return get_disaster_recovery_status()


# ---------------------------------------------------------------------------
# Infrastructure & Platform Operations rebuild, slice 3 of 4 -- AI
# Infrastructure + Network Health (with Privacy Audit). See hub_core/infra_ai.py
# and hub_core/infra_network_health.py for the full real-vs-honest-gap
# reasoning: AI Infrastructure reuses the ALREADY-REAL per-dealer AI
# snapshot data hub_core/dealer_ai_management.py already fetches (no new tenant
# route), re-grouped into Sam's own 4 named Models. Network Health composes
# real dealer_registry/network_snapshot counts plus a genuinely re-runnable
# Privacy Audit that inspects the real NetworkSnapshot schema + every
# currently-stored record against Sam's own never-collect field list.
# Static paths ("ai-infrastructure", "ai-infrastructure/recheck-all",
# "network-health", "network-health/privacy-audit") are all registered
# before the one dynamic "ai-infrastructure/{dealer_id}/recheck" sibling,
# same route-shadowing-avoidance convention as every other block in this
# file.
# ---------------------------------------------------------------------------

@app.get("/hub/infra/ai-infrastructure")
def infra_ai_overview_route(admin: dict = Depends(require_hub_admin)):
    return get_ai_infrastructure_overview()


@app.post("/hub/infra/ai-infrastructure/recheck-all")
def infra_ai_recheck_all_route(admin: dict = Depends(require_hub_admin)):
    """Bulk live re-fetch of every registered dealer's real AI feature/
    call-count snapshot -- not run automatically on every GET, same
    reasoning as every other live tenant-fetch recheck action in this
    file."""
    result = recheck_all_dealer_ai_infrastructure()
    save_dealer_ai_snapshots(DEALER_AI_SNAPSHOTS_PATH)
    return result


@app.post("/hub/infra/ai-infrastructure/{dealer_id}/recheck")
def infra_ai_recheck_dealer_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    """Reuses hub_core/dealer_ai_management_api.py's own already-real,
    already-persisting per-dealer recheck function directly -- this screen
    shows the identical underlying snapshot data, just re-grouped."""
    result = recheck_dealer_ai_management_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    save_dealer_ai_snapshots(DEALER_AI_SNAPSHOTS_PATH)
    return result


@app.get("/hub/infra/network-health")
def infra_network_health_route(admin: dict = Depends(require_hub_admin)):
    return get_network_health_overview()


@app.get("/hub/infra/network-health/privacy-audit")
def infra_privacy_audit_route(admin: dict = Depends(require_hub_admin)):
    """A real, re-runnable inspection (hub_core/infra_network_health.py's
    run_privacy_audit()) -- click again any time to re-check the current
    real schema + stored records, not a cached/static claim."""
    return run_privacy_audit()


# ---------------------------------------------------------------------------
# Infrastructure & Platform Operations rebuild, slice 4 of 4 (CLOSING) --
# Messaging + Security + Monitoring. See hub_core/infra_messaging.py,
# hub_core/infra_security.py, and hub_core/infra_monitoring.py for the full
# real-vs-honest-gap reasoning. All three deliberately reuse already-fetched
# Hub state (Messaging reuses infra_services.py's Services-panel snapshot,
# Security reuses dealer_support.py's Support Center snapshot, Monitoring
# composes noc.py/platform_status.py/infra_ai.py/infra_network_health.py
# directly) -- no new tenant route, no new Recheck action for any of the
# three. This closes out the entire 12-item Infrastructure & Platform
# Operations menu.
# ---------------------------------------------------------------------------

@app.get("/hub/infra/messaging")
def infra_messaging_route(admin: dict = Depends(require_hub_admin)):
    return get_messaging_overview()


@app.get("/hub/infra/security")
def infra_security_route(admin: dict = Depends(require_hub_admin)):
    return get_security_overview()


@app.get("/hub/infra/monitoring")
def infra_monitoring_route(admin: dict = Depends(require_hub_admin)):
    return get_monitoring_overview()


# ---------------------------------------------------------------------------
# Dealer Management rebuild, slice 2 of 5 -- Module Management + Feature
# Flags. See hub_core/dealer_modules.py + hub_core/feature_flags.py for the real
# logic; both modules' own docstrings state plainly that this is a Hub-side
# CONFIGURATION RECORD today, not a live tenant-side enforcement mechanism.
# Static paths ("catalog", "scopes", "resolve") are registered before the
# dynamic {dealer_id}/{override_id} paths on the same GET method, per this
# codebase's established route-shadowing-avoidance convention.
# ---------------------------------------------------------------------------

@app.get("/hub/dealer-management/modules/catalog")
def module_catalog_route(admin: dict = Depends(require_hub_admin)):
    return get_module_catalog_api()


@app.get("/hub/dealer-management/modules/{dealer_id}")
def get_dealer_modules_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_dealer_modules_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/dealer-management/modules/{dealer_id}")
def set_dealer_module_route(
    dealer_id: str,
    request: SetDealerModuleRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = set_dealer_module_api(dealer_id, request.module_key, request.enabled)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/dealer-management/feature-flags/scopes")
def feature_flag_scopes_route(admin: dict = Depends(require_hub_admin)):
    return list_feature_flag_scopes_api()


@app.get("/hub/dealer-management/feature-flags/resolve")
def resolve_feature_flag_route(
    flag_key: str,
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = resolve_feature_flag_api(flag_key, dealer_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/dealer-management/feature-flags")
def list_feature_flag_overrides_route(
    flag_key: Optional[str] = None,
    admin: dict = Depends(require_hub_admin)
):
    return list_feature_flag_overrides_api(flag_key)


@app.post("/hub/dealer-management/feature-flags")
def create_feature_flag_override_route(
    request: CreateFeatureFlagOverrideRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = create_feature_flag_override_api(**request.dict())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.delete("/hub/dealer-management/feature-flags/{override_id}")
def delete_feature_flag_override_route(
    override_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = delete_feature_flag_override_api(override_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Dealer Management rebuild, slice 3 of 5 -- Onboarding Center + Migration
# Tracking (the "Provisioning" menu item). See hub_core/dealer_onboarding.py +
# hub_core/dealer_migration.py for the real-automated-vs-honest-manual signal
# breakdown per step, the live /network/anonymous-snapshot reachability
# check backing "Network Connected" (never persists the pseudonym it reads),
# and the real, rule-based Go-Live Tracker thresholds. Static paths
# ("catalog", "summary") registered before the dynamic {dealer_id} paths,
# same route-shadowing-avoidance convention as every other block above.
# ---------------------------------------------------------------------------

@app.get("/hub/dealer-management/onboarding/catalog")
def onboarding_catalog_route(admin: dict = Depends(require_hub_admin)):
    return get_onboarding_catalog_api()


@app.get("/hub/dealer-management/onboarding/summary")
def onboarding_summary_route(admin: dict = Depends(require_hub_admin)):
    return list_onboarding_summaries_api()


@app.get("/hub/dealer-management/onboarding/{dealer_id}")
def get_dealer_onboarding_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_dealer_onboarding_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/dealer-management/onboarding/{dealer_id}/recheck")
def recheck_dealer_onboarding_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    """Runs the real, live checks for every "auto" onboarding step (currently
    Dealer Created + Network Connected -- see hub_core/dealer_onboarding.py) and
    persists the result. Not run automatically on every GET, since the
    Network Connected check is a real HTTP round trip to the dealer's own
    instance."""
    result = recheck_dealer_onboarding_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/dealer-management/onboarding/{dealer_id}/steps")
def set_dealer_onboarding_step_route(
    dealer_id: str,
    request: SetOnboardingStepRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = set_dealer_onboarding_step_api(
        dealer_id, request.step_key, request.complete, note=request.note
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/dealer-management/migration/catalog")
def migration_catalog_route(admin: dict = Depends(require_hub_admin)):
    return get_migration_catalog_api()


@app.get("/hub/dealer-management/migration/summary")
def migration_summary_route(admin: dict = Depends(require_hub_admin)):
    return list_migration_summaries_api()


@app.get("/hub/dealer-management/migration/{dealer_id}")
def get_dealer_migration_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_dealer_migration_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/dealer-management/migration/{dealer_id}/source")
def set_dealer_migration_source_route(
    dealer_id: str,
    request: SetMigrationSourceRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = set_dealer_migration_source_api(
        dealer_id, request.migrating_from, other_note=request.other_note
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/dealer-management/migration/{dealer_id}/readiness")
def set_dealer_readiness_route(
    dealer_id: str,
    request: SetReadinessRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = set_dealer_readiness_api(
        dealer_id, request.category, request.pct, note=request.note
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Dealer Management rebuild, slice 4 of 5 -- Integrations Center + AI
# Management (per dealer).
#
# Integrations Center (hub_core/dealer_integrations.py) is an honest, Hub-side
# MANUAL record -- Sam's named provider list (Google/Microsoft/Meta/CDK/
# DealerTrack/RouteOne/Xtime) has no real backing catalog anywhere in the
# tenant codebase, and even the closest real tenant model (backend/core/
# data_connections.py's Connection entity) carries a real endpoint_url that's
# a meaningfully riskier thing to expose under the shared network key than
# the coarse KPI-bucket precedent that key was designed around. See that
# module's own docstring for the full reasoning.
#
# AI Management (hub_core/dealer_ai_management.py) IS a real, live, on-demand
# pull from a NEW, narrowly-scoped tenant-side route --
# GET /network/ai-management-snapshot (backend/api/app.py, backend/core/
# ai_management.py's build_ai_management_network_snapshot()) -- gated by the
# SAME DEALEROS_NETWORK_KEY shared secret /network/anonymous-snapshot already
# uses, judged safe because the underlying payload is a static feature
# catalog plus 4 plain integer call-attempt counters, no endpoint URLs, no
# freeform text, no PII. See that module's own docstring for the full
# reasoning, including why this fetch is deliberately DEALER-IDENTIFIED
# (unlike the peer-benchmark pull's anonymized pseudonym model).
#
# Static paths ("catalog") registered before the dynamic {dealer_id} paths,
# same route-shadowing-avoidance convention as every block above.
# ---------------------------------------------------------------------------

@app.get("/hub/dealer-management/integrations/catalog")
def integrations_catalog_route(admin: dict = Depends(require_hub_admin)):
    return get_integrations_catalog_api()


@app.get("/hub/dealer-management/integrations/{dealer_id}")
def get_dealer_integrations_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_dealer_integrations_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/dealer-management/integrations/{dealer_id}")
def add_dealer_integration_route(
    dealer_id: str,
    request: AddDealerIntegrationRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = add_dealer_integration_api(dealer_id, **request.dict())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/dealer-management/integrations/{dealer_id}/{integration_id}")
def update_dealer_integration_route(
    dealer_id: str,
    integration_id: str,
    request: UpdateDealerIntegrationRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = update_dealer_integration_api(integration_id, **request.dict())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.delete("/hub/dealer-management/integrations/{dealer_id}/{integration_id}")
def remove_dealer_integration_route(
    dealer_id: str,
    integration_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = remove_dealer_integration_api(integration_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/hub/dealer-management/ai/catalog")
def ai_area_catalog_route(admin: dict = Depends(require_hub_admin)):
    return get_ai_area_catalog_api()


@app.get("/hub/dealer-management/ai/{dealer_id}")
def get_dealer_ai_management_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_dealer_ai_management_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/dealer-management/ai/{dealer_id}/recheck")
def recheck_dealer_ai_management_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    """Live HTTP round trip to this dealer's own /network/ai-management-snapshot
    endpoint -- not run automatically on every GET, same reasoning as the
    Onboarding Center's Network Connected recheck action."""
    result = recheck_dealer_ai_management_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Dealer Management rebuild, slice 5 of 5 (FINAL) -- Network Membership /
# Support Center / Audit Center / Users. See hub_core/dealer_network_membership.py,
# hub_core/dealer_support.py, hub_core/hub_audit.py, and hub_core/dealer_contacts.py for
# the full reasoning behind each. Static paths (catalog/summary/events) are
# registered before every dynamic /{dealer_id} sibling, same convention as
# every prior slice in this file.
# ---------------------------------------------------------------------------

@app.get("/hub/dealer-management/network/catalog")
def network_membership_catalog_route(admin: dict = Depends(require_hub_admin)):
    return get_network_membership_catalog_api()


@app.get("/hub/dealer-management/network/{dealer_id}")
def get_dealer_network_membership_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_dealer_network_membership_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/dealer-management/network/{dealer_id}/tier")
def set_dealer_network_tier_route(
    dealer_id: str,
    request: SetNetworkTierRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = set_dealer_network_tier_api(dealer_id, request.tier)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/dealer-management/network/{dealer_id}/recheck-pipeline")
def recheck_dealer_pipeline_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    """Live HTTP round trip to this dealer's own /network/anonymous-snapshot
    endpoint (reuses hub/hub_core/dealer_onboarding.py's own Network Connected
    check) -- proves the pipeline works, NOT that a snapshot was ever
    actually collected/stored. See hub_core/dealer_network_membership.py's own
    docstring for why per-dealer contribution can't honestly go further
    than this without breaking the pseudonym-anonymity boundary."""
    result = recheck_dealer_pipeline_connectivity_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/dealer-management/support/{dealer_id}")
def get_dealer_support_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_dealer_support_status_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/dealer-management/support/{dealer_id}/recheck")
def recheck_dealer_support_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    """Live HTTP round trip to this dealer's own new
    /network/operational-health-snapshot endpoint -- not run automatically
    on every GET, same reasoning as every other live tenant-fetch recheck
    action in this file."""
    result = recheck_dealer_support_snapshot_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/dealer-management/audit/catalog")
def audit_catalog_route(admin: dict = Depends(require_hub_admin)):
    return get_audit_catalog_api()


@app.get("/hub/dealer-management/audit/events")
def list_audit_events_route(
    dealer_id: Optional[str] = None,
    category: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 200,
    admin: dict = Depends(require_hub_admin)
):
    return list_audit_events_api(dealer_id=dealer_id, category=category, event_type=event_type, limit=limit)


@app.get("/hub/dealer-management/audit/dealer/{dealer_id}")
def get_dealer_audit_summary_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_dealer_audit_summary_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/hub/dealer-management/users/catalog")
def users_catalog_route(admin: dict = Depends(require_hub_admin)):
    return get_users_catalog_api()


@app.get("/hub/dealer-management/users/{dealer_id}")
def get_dealer_users_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_dealer_users_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/dealer-management/users/{dealer_id}")
def add_dealer_contact_route(
    dealer_id: str,
    request: AddDealerContactRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = add_dealer_contact_api(dealer_id, request.name, request.role, email=request.email, phone=request.phone)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.delete("/hub/dealer-management/users/contact/{contact_id}")
def remove_dealer_contact_route(
    contact_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = remove_dealer_contact_api(contact_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# NXTDeal Network Connect (2026-07-19) -- Hub backend foundation. See
# hub_core/network_connect.py's own module docstring for the full privacy
# design and hub_core/network_connect_api.py's own module docstring for the
# three separate auth shapes used below:
#
#   /network-connect/*        -- PUBLIC or self-service (account_token /
#                                 pseudonym possession only). Deliberately
#                                 NOT gated by X-NXTDeal-Hub-Key -- these are
#                                 meant to be called by a dealer/prospect's
#                                 own browser (the future extension), not
#                                 NXTDeal staff.
#   /hub/network-connect/*     -- NXTDeal-staff-only administration (tier/
#                                 status changes, migration readiness,
#                                 the admin roster, converting an account to
#                                 a real Dealer). Gated by X-NXTDeal-Hub-Key,
#                                 same as every other /hub/* route in this
#                                 file.
#
# Static paths ("connectors", "migration-readiness-catalog", "kpi-catalog",
# "signup", "kpi-snapshot", "accounts") are registered before every dynamic
# "{account_id}" sibling, same route-shadowing-avoidance convention as every
# other block in this file.
# ---------------------------------------------------------------------------

@app.get("/network-connect/connectors")
def network_connect_connectors_route():
    return get_connector_catalog_api()


@app.get("/network-connect/migration-readiness-catalog")
def network_connect_readiness_catalog_route():
    return get_migration_readiness_catalog_api()


@app.get("/network-connect/kpi-catalog")
def network_connect_kpi_catalog_route():
    return get_kpi_catalog_api()


@app.post("/network-connect/signup")
def network_connect_signup_route(request: SignupNetworkConnectRequest):
    result = signup_network_connect_account_api(
        company_name=request.company_name,
        contact_email=request.contact_email,
        contact_name=request.contact_name,
        contact_phone=request.contact_phone,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/network-connect/kpi-snapshot")
def network_connect_kpi_snapshot_route(request: SubmitKpiSnapshotRequest):
    """Anonymous by design -- no account_token, no X-NXTDeal-Hub-Key.
    Possession of the pseudonym is the only credential this needs. See
    hub_core/network_connect_api.py's submit_kpi_snapshot_api() docstring."""
    result = submit_kpi_snapshot_api(request.pseudonym, request.departments)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/network-connect/accounts/{account_id}")
def network_connect_get_account_route(
    account_id: str,
    x_network_connect_account_token: Optional[str] = Header(default=None)
):
    result = get_network_connect_account_api(account_id, x_network_connect_account_token)
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
    return result


@app.post("/network-connect/accounts/{account_id}/connected-systems")
def network_connect_set_connected_system_route(
    account_id: str,
    request: SetConnectedSystemRequest,
    x_network_connect_account_token: Optional[str] = Header(default=None)
):
    result = set_connected_system_api(
        account_id, x_network_connect_account_token, request.category, request.provider_key
    )
    if "error" in result:
        status = 401 if "invalid account_id or account_token" in result["error"] else 400
        raise HTTPException(status_code=status, detail=result["error"])
    return result


@app.post("/network-connect/accounts/{account_id}/benchmark")
def network_connect_get_benchmark_route(
    account_id: str,
    request: GetBenchmarkRequest,
    x_network_connect_account_token: Optional[str] = Header(default=None)
):
    """Requires BOTH the account_token header (tier lookup) and the
    pseudonym in the body (fetching "your own" submission) -- see
    hub_core/network_connect_api.py's get_benchmark_api() docstring for the one
    deliberate, disclosed, in-memory-only exception this makes to the
    "never joinable" rule."""
    result = get_benchmark_api(account_id, x_network_connect_account_token, request.pseudonym)
    if "error" in result:
        status = 401 if "invalid account_id or account_token" in result["error"] else 400
        raise HTTPException(status_code=status, detail=result["error"])
    return result


@app.get("/hub/network-connect/accounts")
def hub_network_connect_list_accounts_route(admin: dict = Depends(require_hub_admin)):
    return list_network_connect_accounts_api()


@app.get("/hub/network-connect/overview")
def hub_network_connect_overview_route(admin: dict = Depends(require_hub_admin)):
    return get_network_connect_overview_api()


@app.get("/hub/network-connect/accounts/{account_id}")
def hub_network_connect_get_account_route(
    account_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_network_connect_account_admin_api(account_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/network-connect/accounts/{account_id}/tier")
def hub_network_connect_set_tier_route(
    account_id: str,
    request: SetNetworkConnectTierRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = set_tier_api(account_id, request.tier)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/network-connect/accounts/{account_id}/status")
def hub_network_connect_set_status_route(
    account_id: str,
    request: SetNetworkConnectStatusRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = set_status_api(account_id, request.status)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/network-connect/accounts/{account_id}/migration-readiness")
def hub_network_connect_set_readiness_route(
    account_id: str,
    request: SetNetworkConnectReadinessRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = set_migration_readiness_api(account_id, request.category, request.pct, note=request.note)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/network-connect/accounts/{account_id}/convert-to-dealer")
def hub_network_connect_convert_route(
    account_id: str,
    request: ConvertToDealerRequest,
    admin: dict = Depends(require_hub_admin)
):
    """The real one-click "Enable Account -> Go Live" conversion Sam's own
    spec described -- see hub_core/network_connect_api.py's
    convert_account_to_dealer_api() docstring for exactly what it does and
    does not do (reuses hub_core/provisioning.py's create_dealer() verbatim,
    scaffolds a real empty tenant, no data import)."""
    result = convert_account_to_dealer_api(account_id, plan_tier=request.plan_tier)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# AI-Powered Self-Auditing Code Layer (2026-07-19). Sam's own kickoff request,
# scoped via AskUserQuestion into 3 binding decisions: (1) build this system
# first, then let it run the first sweep, rather than a manual audit pass
# first; (2) every small-issue auto-fix lands on its own dedicated git branch
# with a real commit -- nothing is ever auto-merged to main without a human;
# (3) since every dealer tenant runs the identical shared codebase
# (process-per-tenant, not per-tenant forks), "scanning deployed dealerships"
# means scanning the one shared codebase (backend/hub/frontend/extension) for
# code quality and bugs -- not per-tenant runtime health monitoring (that's
# the separate, already-built Infrastructure & Platform Ops/NOC system).
# See hub_core/code_auditor.py's own module docstring for the full severity
# ladder (small=auto-fix, medium=draft+human-approval, large=report-only) and
# the "real rules, never fake AI judgment" design principle.
# ---------------------------------------------------------------------------

@app.get("/hub/code-audit/catalog")
def hub_code_audit_catalog_route(admin: dict = Depends(require_hub_admin)):
    return get_code_audit_catalog_api()


@app.get("/hub/code-audit/overview")
def hub_code_audit_overview_route(admin: dict = Depends(require_hub_admin)):
    return get_code_audit_overview_api()


@app.get("/hub/code-audit/scheduler-status")
def hub_code_audit_scheduler_status_route(admin: dict = Depends(require_hub_admin)):
    """A real, live read of the background scan scheduler's own in-memory
    state (hub_core/code_auditor_scheduler.py) -- last automated run / next run --
    distinct from get_code_audit_overview_api(), which reports on every run
    regardless of who triggered it."""
    return get_code_auditor_scheduler_status()


@app.get("/hub/secrets/posture")
def hub_secrets_posture_route(admin: dict = Depends(require_hub_admin)):
    """hub_core/secrets.py Task #13, 2026-07-20 -- a real, per-secret report of
    whether this Hub process is currently on a configured value or an insecure dev
    fallback for NXTDEAL_HUB_KEY/DEALEROS_NETWORK_KEY/DEALEROS_AUTH_SECRET, never
    the secret values themselves."""
    return get_secrets_posture_api()


@app.post("/hub/code-audit/scan")
def hub_code_audit_scan_route(
    request: RunCodeAuditScanRequest,
    admin: dict = Depends(require_hub_admin)
):
    """Triggers a real scan -- for the one auto-fixable rule
    (missing_save_graph), this can create a real git branch + commit in the
    actual repo right now, per Sam's own decision #2. Never touches main."""
    result = run_code_audit_scan_api(triggered_by=request.triggered_by, areas=request.areas)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/code-audit/findings")
def hub_code_audit_list_findings_route(
    severity: Optional[str] = None,
    status: Optional[str] = None,
    area: Optional[str] = None,
    run_id: Optional[str] = None,
    admin: dict = Depends(require_hub_admin)
):
    result = list_code_audit_findings_api(severity=severity, status=status, area=area, run_id=run_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/code-audit/findings/{finding_id}")
def hub_code_audit_get_finding_route(
    finding_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_code_audit_finding_api(finding_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/code-audit/findings/{finding_id}/approve")
def hub_code_audit_approve_finding_route(
    finding_id: str,
    request: ApproveCodeAuditFindingRequest,
    admin: dict = Depends(require_hub_admin)
):
    """A medium-tier finding's proposed fix, approved by a real human -- this
    is what actually creates the real git branch + commit for that finding,
    same never-auto-merged-to-main guarantee as an auto-fix."""
    result = approve_code_audit_finding_api(finding_id, request.approved_by, note=request.note)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/code-audit/findings/{finding_id}/reject")
def hub_code_audit_reject_finding_route(
    finding_id: str,
    request: RejectCodeAuditFindingRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = reject_code_audit_finding_api(finding_id, request.rejected_by, note=request.note)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/code-audit/findings/{finding_id}/resolve")
def hub_code_audit_resolve_finding_route(
    finding_id: str,
    request: ResolveCodeAuditFindingRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = resolve_code_audit_finding_api(finding_id, request.resolved_by, note=request.note)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hub/code-audit/findings/{finding_id}/dismiss")
def hub_code_audit_dismiss_finding_route(
    finding_id: str,
    request: DismissCodeAuditFindingRequest,
    admin: dict = Depends(require_hub_admin)
):
    result = dismiss_code_audit_finding_api(finding_id, request.dismissed_by, note=request.note)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/code-audit/runs")
def hub_code_audit_list_runs_route(admin: dict = Depends(require_hub_admin)):
    return list_code_audit_runs_api()


@app.get("/hub/code-audit/runs/{run_id}")
def hub_code_audit_get_run_route(
    run_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_code_audit_run_api(run_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Security-hardening pass, Task #6 (2026-07-20) -- AI Kill Switch emergency-
# response console. See hub_core/dealer_ai_kill_switch.py's own module
# docstring for the full design: status is ALWAYS a real, live fetch (never
# cached, unlike hub/hub_core/dealer_ai_management.py's own recheck-and-persist
# pattern -- an incident-response tool showing stale state would be actively
# dangerous), and every push attempt (success or failure) is a permanent,
# append-only record. Static paths ("/hub/ai-kill-switch/history") are
# registered before the dynamic "{dealer_id}" siblings, same
# route-shadowing-avoidance convention as every other block in this file.
# ---------------------------------------------------------------------------


@app.get("/hub/ai-kill-switch/history")
def hub_ai_kill_switch_all_history_route(admin: dict = Depends(require_hub_admin)):
    return get_all_kill_switch_history_api()


@app.get("/hub/ai-kill-switch/{dealer_id}/status")
def hub_ai_kill_switch_status_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    """Always a real, live HTTP round trip to this dealer's own tenant
    process -- deliberately never served from a cache. See this module's own
    docstring for why."""
    result = get_dealer_kill_switch_status_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/hub/ai-kill-switch/{dealer_id}/push")
def hub_ai_kill_switch_push_route(
    dealer_id: str,
    request: PushKillSwitchRequest,
    admin: dict = Depends(require_hub_admin)
):
    """The real emergency-stop action -- a NXTDeal staffer pushing a real AI
    kill switch to a specific, reachable dealer's own tenant process,
    without needing that dealer's own employee credentials. Recorded both as
    a permanent action-log entry here and to the Hub's own centralized audit
    log (hub_core/hub_audit.py), whether the push actually succeeded or
    not."""
    result = push_dealer_kill_switch_api(
        dealer_id,
        pushed_by=request.pushed_by,
        scope=request.scope,
        active=request.active,
        reason=request.reason,
        department=request.department,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hub/ai-kill-switch/{dealer_id}/history")
def hub_ai_kill_switch_dealer_history_route(
    dealer_id: str,
    admin: dict = Depends(require_hub_admin)
):
    result = get_dealer_kill_switch_history_api(dealer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# Lab policy uses existing Hub staff auth and strict configured network transport.
from hub_core import dealership_lab_policy


class SyncLabPolicyRequest(BaseModel):
    revision: int = Field(ge=0)


@app.get('/hub/dealer-management/lab-policy/{dealer_id}')
def lab_policy_status_route(dealer_id:str,admin:dict=Depends(require_hub_admin)):
    try:return dealership_lab_policy.status(dealer_id)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc


@app.post('/hub/dealer-management/lab-policy/{dealer_id}')
def lab_policy_sync_route(dealer_id:str,request:SyncLabPolicyRequest,admin:dict=Depends(require_hub_admin)):
    try:return dealership_lab_policy.synchronize(dealer_id,request.revision,admin.get('employee_id','hub-admin'))
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
